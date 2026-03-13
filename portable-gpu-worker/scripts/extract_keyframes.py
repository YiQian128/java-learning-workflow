#!/usr/bin/env python3
"""
extract_keyframes.py - 场景切换关键帧提取
策略优先级：
  1. PySceneDetect AdaptiveDetector（AI自适应场景检测，最准确）
  2. FFmpeg scene filter（兜底，阈值场景检测）
  3. 固定间隔采样（最终兜底）
场景切换过渡帧自动去除（仅保留稳定的场景首帧）。

新增功能：词级时间戳（words.json）引导关键帧提取
  - 分析语速、停顿、关键词密度，识别"知识难点时刻"
  - 在难点时刻补充提取关键帧（若该时刻附近无场景帧）
  - 生成带 importance_signals 元数据的 frames_index.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: Path, root: Path = WORKER_ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _get_video_duration(video: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video)],
            capture_output=True, text=True, errors="replace", timeout=30,
        )
        if r.returncode == 0:
            return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def _format_time(seconds: float) -> str:
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def _extract_with_pyscenedetect(
    video: Path,
    out_dir: Path,
    quality: int,
    min_scene_len: float = 1.5,
) -> list[dict]:
    """
    使用 PySceneDetect AdaptiveDetector 进行场景检测。
    AdaptiveDetector 比固定阈值更适合教程类视频（PPT切换、代码切换）。
    仅提取每个场景的第一帧（稳定帧），过滤掉过渡帧。
    """
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import AdaptiveDetector
        from scenedetect.scene_manager import save_images
    except ImportError:
        return []

    try:
        video_obj = open_video(str(video))
        scene_manager = SceneManager()
        # AdaptiveDetector: 自适应阈值，对渐变和硬切换都有效
        # min_scene_len 过滤掉过短的"过渡场景"（通常是幻灯片切换的淡入淡出）
        scene_manager.add_detector(AdaptiveDetector(
            adaptive_threshold=3.0,   # 低值 = 更敏感
            min_scene_len=int(min_scene_len * video_obj.frame_rate),
        ))
        scene_manager.detect_scenes(video_obj, show_progress=False)
        scene_list = scene_manager.get_scene_list()
    except Exception as e:
        print(f"    PySceneDetect 检测失败: {e}", file=sys.stderr)
        return []

    if not scene_list:
        return []

    print(f"    PySceneDetect: 检测到 {len(scene_list)} 个场景")

    # 对每个场景提取第1帧（跳过过渡帧：取场景开始后 0.5s）
    records = []
    tmp_dir = out_dir / "_psd_tmp"
    tmp_dir.mkdir(exist_ok=True)

    for i, (start_tc, end_tc) in enumerate(scene_list):
        # 取场景开始时间 + 0.5s 作为稳定帧时间点（避开切换瞬间）
        ts = start_tc.get_seconds() + 0.5
        if ts >= end_tc.get_seconds():
            ts = start_tc.get_seconds()

        dst = tmp_dir / f"psd_{i:06d}.jpg"
        cmd = [
            "ffmpeg", "-ss", str(ts), "-i", str(video),
            "-frames:v", "1",
            "-vf", "scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih)",
            "-q:v", str(quality), str(dst), "-y", "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
            if dst.exists():
                records.append({"source_path": dst, "type": "scene", "timestamp_s": ts})
        except Exception:
            pass

    return records


def _extract_scene_frames_ffmpeg(
    video: Path,
    scene_dir: Path,
    scene_threshold: float,
    quality: int,
) -> list[dict]:
    """FFmpeg scene filter 兜底方案。"""
    scene_cmd = [
        "ffmpeg", "-i", str(video),
        "-vf",
        f"select=gt(scene\\,{scene_threshold}),showinfo,"
        f"scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih)",
        "-vsync", "vfr", "-q:v", str(quality),
        str(scene_dir / "scene_%08d.jpg"), "-y", "-loglevel", "level+info",
    ]
    result_obj = type("R", (), {"returncode": 1, "stderr": ""})()
    try:
        proc = subprocess.run(scene_cmd, capture_output=True, text=True, errors="replace", timeout=1800)
        result_obj = proc
    except subprocess.TimeoutExpired:
        pass

    pts_times: list[float] = []
    for m in re.finditer(r"pts_time:(\d+(?:\.\d+)?)", result_obj.stderr or ""):
        pts_times.append(float(m.group(1)))

    scene_files = sorted(scene_dir.glob("*.jpg"))
    records = []
    for i, f in enumerate(scene_files):
        ts = pts_times[i] if i < len(pts_times) else None
        records.append({"source_path": f, "type": "scene", "timestamp_s": ts})
    return records


def _extract_interval_frames(
    video: Path,
    interval_dir: Path,
    fallback_interval: int,
    quality: int,
) -> list[dict]:
    """固定间隔帧（最终兜底）。"""
    interval_cmd = [
        "ffmpeg", "-i", str(video),
        "-vf",
        f"fps=1/{fallback_interval},"
        f"scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih)",
        "-q:v", str(quality + 1),
        str(interval_dir / "interval_%08d.jpg"), "-y", "-loglevel", "error",
    ]
    try:
        subprocess.run(interval_cmd, capture_output=True, timeout=1800)
    except subprocess.TimeoutExpired:
        pass

    interval_files = sorted(interval_dir.glob("*.jpg"))
    records = []
    for i, f in enumerate(interval_files):
        ts = i * fallback_interval
        records.append({"source_path": f, "type": "interval", "timestamp_s": ts})
    return records


def _load_words_json(words_json_path: str) -> list[dict]:
    """
    加载词级时间戳 JSON 文件。
    兼容两种格式：
      A. 扁平列表：[{"start": 0.0, "end": 0.5, "word": "Java"}, ...]
      B. 分段格式：{"segments": [{"words": [...]}]} 或 [{"words": [...)}]
    统一返回扁平 word 列表。
    """
    try:
        with open(words_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"    Warning: cannot load words.json: {e}", file=sys.stderr)
        return []

    words: list[dict] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                if "word" in item and "start" in item:
                    # 格式 A：直接是 word 对象
                    words.append(item)
                elif "words" in item:
                    # 格式 B1：列表中包含 segment 对象
                    for w in item["words"]:
                        if isinstance(w, dict) and "start" in w:
                            words.append(w)
    elif isinstance(data, dict):
        if "words" in data:
            # 顶层有 words 列表
            words = [w for w in data["words"] if isinstance(w, dict) and "start" in w]
        elif "segments" in data:
            # 格式 B2：{"segments": [{"words": [...]}]}
            for seg in data.get("segments", []):
                for w in seg.get("words", []):
                    if isinstance(w, dict) and "start" in w:
                        words.append(w)

    return words


def _analyze_words_for_keyframes(
    words: list[dict],
    video_duration: float,
    gap_threshold: float = 2.0,
    slowdown_ratio: float = 0.50,
    window_seconds: float = 30.0,
) -> list[dict]:
    """
    分析词级时间戳，返回"重要时刻"列表，每项含：
      - timestamp_s: float
      - reason: str（slowdown / pause / keyword_density）
      - priority: "high" / "medium"

    识别逻辑：
      1. 长停顿（pause）：相邻词间隔 > gap_threshold 秒
      2. 语速骤降（slowdown）：某 30s 窗口的词密度 < 全局平均的 slowdown_ratio
      3. 关键词密集（keyword_density）：Java 技术关键词在 30s 窗口内出现频次异常高
    """
    if not words:
        return []

    important_moments: list[dict] = []
    added_ts: set[float] = set()

    # ── 1. 长停顿识别 ─────────────────────────────────────────────
    for i in range(1, len(words)):
        prev_end = words[i - 1].get("end", words[i - 1].get("start", 0))
        curr_start = words[i].get("start", 0)
        gap = curr_start - prev_end
        if gap >= gap_threshold:
            ts = curr_start  # 停顿结束、讲师重新开口的时间点
            important_moments.append({
                "timestamp_s": round(ts, 2),
                "reason": f"pause_{round(gap, 1)}s",
                "priority": "high" if gap >= 3.0 else "medium",
            })
            added_ts.add(round(ts, 1))

    # ── 2. 语速骤降识别 ───────────────────────────────────────────
    if len(words) > 20:
        # 全局平均词速（词/秒）
        total_duration = (words[-1].get("end", words[-1]["start"]) -
                          words[0]["start"])
        if total_duration > 0:
            global_wps = len(words) / total_duration  # words-per-second

            # 滑动窗口扫描
            win_start_idx = 0
            t = words[0]["start"]
            while t < (video_duration if video_duration > 0 else words[-1].get("end", 0)):
                t_end = t + window_seconds
                # 收集窗口内的词
                win_words = [w for w in words if t <= w["start"] < t_end]
                if len(win_words) >= 5:
                    win_duration = min(t_end, words[-1].get("end", t_end)) - t
                    if win_duration > 0:
                        win_wps = len(win_words) / win_duration
                        if win_wps < global_wps * slowdown_ratio:
                            ts = t + window_seconds / 2  # 窗口中点作为代表时刻
                            ts_key = round(ts, 0)
                            if ts_key not in added_ts:
                                important_moments.append({
                                    "timestamp_s": round(ts, 2),
                                    "reason": f"slowdown_{round(win_wps/global_wps*100)}pct",
                                    "priority": "high",
                                })
                                added_ts.add(ts_key)
                t += window_seconds / 2  # 步长 = 半窗口，形成重叠扫描

    # ── 3. Java 技术关键词密度识别 ────────────────────────────────
    java_keywords = {
        "jvm", "jre", "jdk", "class", "interface", "abstract",
        "extends", "implements", "static", "synchronized", "volatile",
        "hashmap", "hashset", "arraylist", "linkedlist",
        "thread", "runnable", "callable", "executor",
        "exception", "try", "catch", "finally", "throw",
        "stream", "lambda", "optional", "generics", "泛型",
        "继承", "多态", "封装", "接口", "抽象", "线程", "并发",
        "垃圾回收", "gc", "堆", "栈", "方法区",
    }

    # 统计每个 30s 窗口内关键词出现次数
    t = words[0]["start"] if words else 0
    max_t = words[-1].get("end", 0) if words else 0
    window_counts: list[tuple[float, int]] = []
    while t < max_t:
        t_end = t + window_seconds
        win_words = [w for w in words if t <= w["start"] < t_end]
        kw_count = sum(
            1 for w in win_words
            if any(kw in w.get("word", "").lower() for kw in java_keywords)
        )
        window_counts.append((t, kw_count))
        t += window_seconds / 2

    if window_counts:
        avg_kw = sum(c for _, c in window_counts) / len(window_counts)
        for win_t, count in window_counts:
            if count > max(avg_kw * 2.5, 5):  # 明显高于平均
                ts = win_t + window_seconds / 2
                ts_key = round(ts, 0)
                if ts_key not in added_ts:
                    important_moments.append({
                        "timestamp_s": round(ts, 2),
                        "reason": f"keyword_density_{count}_terms",
                        "priority": "medium",
                    })
                    added_ts.add(ts_key)

    # 按时间戳排序
    important_moments.sort(key=lambda x: x["timestamp_s"])
    return important_moments


def _extract_words_guided_frames(
    video: Path,
    words_json_path: str,
    out_dir: Path,
    existing_ts: set[float],
    quality: int,
    proximity_threshold: float = 10.0,
    video_duration: float = 0.0,
    gap_threshold: float = 0.6,
) -> list[dict]:
    """
    根据 words.json 分析结果，在"重要时刻"补充提取关键帧。

    规则：
      - 若该时刻附近 ±proximity_threshold 秒内已有场景帧 → 跳过（不重复）
      - 若没有 → 提取该时刻的稳定帧（+0.2s 偏移避开可能的切换瞬间）
      - 最多补充 min(high_priority_count + 5, 20) 帧

    返回补充的帧记录列表。
    """
    words = _load_words_json(words_json_path)
    if not words:
        return []

    moments = _analyze_words_for_keyframes(words, video_duration, gap_threshold=gap_threshold)
    if not moments:
        return []

    # 只在没有附近已有帧的时刻提取
    to_extract = []
    for moment in moments:
        ts = moment["timestamp_s"]
        has_nearby = any(abs(ts - ets) < proximity_threshold for ets in existing_ts)
        if not has_nearby:
            to_extract.append(moment)

    if not to_extract:
        return []

    # 限制最大补充帧数（high 优先，然后 medium）
    high_priority = [m for m in to_extract if m["priority"] == "high"]
    medium_priority = [m for m in to_extract if m["priority"] == "medium"]
    max_supplement = min(len(high_priority) + 5, 20)
    selected = (high_priority + medium_priority)[:max_supplement]

    print(f"    words.json 引导：{len(moments)} 个重要时刻，补充提取 {len(selected)} 帧")

    records = []
    wg_dir = out_dir / "_words_guided_tmp"
    wg_dir.mkdir(exist_ok=True)

    for i, moment in enumerate(selected):
        ts = moment["timestamp_s"] + 0.2  # +0.2s 避开切换瞬间
        dst = wg_dir / f"wg_{i:06d}.jpg"
        cmd = [
            "ffmpeg", "-ss", str(ts), "-i", str(video),
            "-frames:v", "1",
            "-vf", "scale=iw*min(1280/iw\\,720/ih):ih*min(1280/iw\\,720/ih)",
            "-q:v", str(quality), str(dst), "-y", "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
            if dst.exists():
                records.append({
                    "source_path": dst,
                    "type": "words_guided",
                    "timestamp_s": ts,
                    "importance_signals": {
                        "reason": moment["reason"],
                        "priority": moment["priority"],
                    }
                })
        except Exception as e:
            print(f"    Warning: words-guided frame extraction failed at {ts}s: {e}")

    return records


def extract_keyframes(
    video_path: str,
    output_dir: str,
    scene_threshold: float = 0.25,
    fallback_interval: int = 30,
    max_frames: int = 80,
    quality: int = 2,
    force_interval: bool = False,
    words_json_path: str | None = None,
    words_gap_threshold: float = 0.6,
    words_proximity: float = 10.0,
) -> int:
    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found.", file=sys.stderr)
        return 1

    video = Path(video_path)
    if not video.exists():
        print(f"ERROR: Video not found: {video_path}", file=sys.stderr)
        return 1

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = _get_video_duration(video)
    print(f"Extracting keyframes: {video.name}"
          + (f" ({_format_time(duration)})" if duration > 0 else ""))

    tmp_scene_dir = out_dir / "_scene_tmp"
    tmp_interval_dir = out_dir / "_interval_tmp"
    tmp_scene_dir.mkdir(exist_ok=True)
    tmp_interval_dir.mkdir(exist_ok=True)

    scene_records: list[dict] = []
    method_used = "interval"

    if not force_interval:
        # 策略 1：PySceneDetect（AI自适应）
        scene_records = _extract_with_pyscenedetect(video, out_dir, quality)
        if scene_records:
            method_used = "pyscenedetect"
        else:
            # 策略 2：FFmpeg scene filter
            print("    PySceneDetect 无结果，尝试 FFmpeg scene filter...")
            scene_records = _extract_scene_frames_ffmpeg(video, tmp_scene_dir, scene_threshold, quality)
            if scene_records:
                method_used = "ffmpeg_scene"

    # 策略 3：固定间隔（兜底或补充）
    interval_records = _extract_interval_frames(video, tmp_interval_dir, fallback_interval, quality)

    # 若场景检测成功，间隔帧只作补充（填补超过 60s 的空白）
    if scene_records:
        scene_ts = {r["timestamp_s"] for r in scene_records if r["timestamp_s"] is not None}
        supplementary_interval = []
        for rec in interval_records:
            ts = rec["timestamp_s"]
            # 只保留与最近场景帧相距 > 60s 的间隔帧
            if not any(abs(ts - st) < 60 for st in scene_ts if st is not None):
                rec["type"] = "interval_supplement"
                supplementary_interval.append(rec)
        all_records = scene_records + supplementary_interval
        print(f"    {method_used}: 场景帧 {len(scene_records)}，补充间隔帧 {len(supplementary_interval)}")
    else:
        all_records = interval_records
        method_used = "interval"
        print(f"    回退到固定间隔采样: {len(interval_records)} 帧")

    # ── Words.json 引导补充帧 ──────────────────────────────────────
    # 在场景检测 / 间隔采样的基础上，用语速/停顿/关键词密度识别出的"难点时刻"补充帧
    words_guided_records: list[dict] = []
    if words_json_path and Path(words_json_path).exists():
        print(f"    分析词级时间戳：{Path(words_json_path).name}")
        existing_ts_set = {
            r["timestamp_s"] for r in all_records if r["timestamp_s"] is not None
        }
        words_guided_records = _extract_words_guided_frames(
            video=video,
            words_json_path=words_json_path,
            out_dir=out_dir,
            existing_ts=existing_ts_set,
            quality=quality,
            proximity_threshold=words_proximity,
            video_duration=duration,
            gap_threshold=words_gap_threshold,
        )
        all_records = all_records + words_guided_records
        if words_guided_records:
            print(f"    words.json 补充了 {len(words_guided_records)} 帧")

    # MD5 去重
    seen_hashes: set[str] = set()
    unique_records: list[dict] = []
    for rec in all_records:
        try:
            with open(rec["source_path"], "rb") as fh:
                h = hashlib.md5(fh.read()).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                unique_records.append(rec)
        except Exception:
            pass

    # 按时间戳排序
    unique_records.sort(key=lambda x: x["timestamp_s"] if x["timestamp_s"] is not None else float("inf"))

    # 超上限时均匀抽样
    if len(unique_records) > max_frames:
        step = len(unique_records) / max_frames
        unique_records = [unique_records[int(i * step)] for i in range(max_frames)]

    # 写入最终输出目录并构建索引
    frame_index = []
    scene_idx = interval_idx = words_idx = 0
    for rec in unique_records:
        frame_type = rec["type"]
        if frame_type in ("scene", "pyscenedetect"):
            scene_idx += 1
            dst = out_dir / f"scene_{scene_idx:06d}.jpg"
        elif frame_type == "words_guided":
            words_idx += 1
            dst = out_dir / f"words_{words_idx:06d}.jpg"
        else:
            interval_idx += 1
            dst = out_dir / f"interval_{interval_idx:06d}.jpg"
        try:
            shutil.copy2(rec["source_path"], dst)
            entry: dict = {"filename": dst.name, "type": frame_type}
            if rec["timestamp_s"] is not None:
                entry["timestamp_s"] = round(rec["timestamp_s"], 3)
                entry["time_str"] = _format_time(rec["timestamp_s"])
            # words_guided 帧额外保存重要性信号
            if frame_type == "words_guided" and rec.get("importance_signals"):
                entry["importance_signals"] = rec["importance_signals"]
            frame_index.append(entry)
        except Exception as e:
            print(f"    Warning: {e}")

    # 清理临时目录
    shutil.rmtree(tmp_scene_dir, ignore_errors=True)
    shutil.rmtree(tmp_interval_dir, ignore_errors=True)
    shutil.rmtree(out_dir / "_psd_tmp", ignore_errors=True)
    shutil.rmtree(out_dir / "_words_guided_tmp", ignore_errors=True)

    index_data = {
        "video": _portable_path(video),
        "duration_s": round(duration, 3) if duration > 0 else None,
        "total_frames": len(frame_index),
        "method": method_used,
        "words_json_used": words_json_path is not None and Path(words_json_path).exists(),
        "scene_threshold": scene_threshold,
        "fallback_interval": fallback_interval,
        "frames": frame_index,
    }
    with open(out_dir / "frames_index.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    final_scene = sum(1 for e in frame_index if e["type"] in ("scene", "pyscenedetect"))
    final_words = sum(1 for e in frame_index if e["type"] == "words_guided")
    final_interval = len(frame_index) - final_scene - final_words
    print(
        f"  完成: {out_dir} （共 {len(frame_index)} 帧，"
        f"方法={method_used}，场景={final_scene}，"
        f"词级引导={final_words}，间隔={final_interval}）"
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="视频关键帧提取（PySceneDetect + FFmpeg + words.json引导）")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--threshold", type=float, default=0.25, help="FFmpeg scene 阈值（兜底用）")
    parser.add_argument("--interval", type=int, default=30, help="兜底间隔采样秒数")
    parser.add_argument("--max-frames", type=int, default=80)
    parser.add_argument("--quality", type=int, default=2, help="JPEG质量 1-31，越小越好")
    parser.add_argument("--force-interval", action="store_true", help="跳过场景检测，强制使用间隔采样")
    parser.add_argument(
        "--words-json", default=None,
        help="词级时间戳 JSON 路径（{video_stem}_words.json），用于难点时刻补充关键帧"
    )
    parser.add_argument(
        "--words-gap", type=float, default=0.8,
        help="停顿检测阈值（秒），低于此值的词间停顿不触发额外帧。默认0.8s，讲课类视频推荐0.6-1.0s"
    )
    parser.add_argument(
        "--words-proximity", type=float, default=10.0,
        help="words引导帧与已有帧的最小距离（秒），过近则跳过。默认10s"
    )
    args = parser.parse_args()

    sys.exit(extract_keyframes(
        args.video, args.output_dir, args.threshold,
        args.interval, args.max_frames, args.quality,
        args.force_interval,
        words_json_path=args.words_json,
        words_gap_threshold=args.words_gap,
        words_proximity=args.words_proximity,
    ))


if __name__ == "__main__":
    main()
