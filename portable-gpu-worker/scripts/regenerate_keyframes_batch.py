#!/usr/bin/env python3
"""
regenerate_keyframes_batch.py - 批量重新生成 output 下所有现有关键帧
遍历 output 中已有 _preprocessing 的目录，清空 frames 后重新运行 extract_keyframes.py
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "videos"
OUTPUT_DIR = ROOT / "output"
SCRIPTS_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _safe_dirname(name: str) -> str:
    import re
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def load_config() -> dict:
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def run_script(script_name: str, args: list[str]) -> int:
    script = SCRIPTS_DIR / script_name
    if not script.exists():
        print(f"ERROR: 脚本不存在 {script}")
        return 1
    venv_py = ROOT / "_env" / "venv"
    if platform.system() == "Windows":
        py = venv_py / "Scripts" / "python.exe"
    else:
        py = venv_py / "bin" / "python"
    if not py.exists():
        py = ROOT / "_env" / "python" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    env = dict(os.environ)
    ffmpeg_bin = ROOT / "_env" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")
    return subprocess.run([str(py), str(script)] + args, env=env, cwd=ROOT).returncode


def collect_tasks() -> list[tuple[Path, Path, Path | None]]:
    """返回 [(video_path, frames_dir, words_json_path or None), ...]"""
    tasks = []
    if not OUTPUT_DIR.exists():
        return tasks
    for prep in OUTPUT_DIR.rglob("_preprocessing"):
        if not prep.is_dir():
            continue
        # prep = output/rel_dir/stem/_preprocessing
        stem_dir = prep.parent
        stem = stem_dir.name
        rel_dir = stem_dir.parent.relative_to(OUTPUT_DIR) if stem_dir != OUTPUT_DIR else Path(".")
        safe_stem = _safe_dirname(stem)

        # 检查是否有 srt（表示已完成转写）
        srt_files = list(prep.glob("*.srt"))
        if not srt_files:
            continue

        seg_dir = prep / "segments"
        split_info = seg_dir / "_split_info.json"

        if split_info.exists():
            try:
                data = json.loads(split_info.read_text(encoding="utf-8"))
                segments = data.get("segments", [])
            except (json.JSONDecodeError, OSError):
                segments = []
            for seg in segments:
                seg_path = Path(seg.get("path", ""))
                if not seg_path.exists():
                    continue
                seg_stem = seg_path.stem
                seg_safe = _safe_dirname(seg_stem)
                frames_dir = prep / "frames" / seg_safe
                words_json = prep / f"{seg_safe}_words.json"
                if not words_json.exists():
                    words_json = None
                tasks.append((seg_path, frames_dir, words_json))
        else:
            # 单视频
            video_path = VIDEOS_DIR / rel_dir / f"{stem}.mp4"
            if not video_path.exists():
                for ext in (".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts"):
                    alt = VIDEOS_DIR / rel_dir / f"{stem}{ext}"
                    if alt.exists():
                        video_path = alt
                        break
            if not video_path.exists():
                continue
            frames_dir = prep / "frames"
            words_json = prep / f"{safe_stem}_words.json"
            if not words_json.exists():
                words_json = None
            tasks.append((video_path, frames_dir, words_json))
    return tasks


def main() -> int:
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("批量重新生成关键帧")
    print("=" * 50)
    tasks = collect_tasks()
    if not tasks:
        print("未找到需要处理的目录（output 下需有 _preprocessing 且含 .srt）")
        return 0

    print(f"共 {len(tasks)} 个视频/分段待处理")
    config = load_config()
    kc = config.get("keyframes", {})

    failed = []
    for i, (video, frames_dir, words_json) in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {video.name} -> {frames_dir.relative_to(ROOT)}")
        # 清空现有关键帧
        for f in list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("frames_index.json")):
            try:
                f.unlink()
            except Exception as e:
                print(f"  Warning: 无法删除 {f.name}: {e}")
        frames_dir.mkdir(parents=True, exist_ok=True)

        kf_args = [
            "--video", str(video),
            "--output-dir", str(frames_dir),
            "--threshold", str(kc.get("scene_threshold", 0.25)),
            "--interval", str(kc.get("fallback_interval", 30)),
            "--max-frames", str(kc.get("max_frames_per_video", 80)),
            "--quality", str(kc.get("jpg_quality", 2)),
        ]
        if words_json and words_json.exists():
            kf_args += [
                "--words-json", str(words_json),
                "--words-gap", str(kc.get("words_gap", 0.6)),
                "--words-proximity", str(kc.get("words_proximity", 10.0)),
            ]
        ret = run_script("extract_keyframes.py", kf_args)
        if ret != 0:
            failed.append(video.name)
            print(f"  [失败] 退出码 {ret}")

    print("\n" + "=" * 50)
    print(f"完成: {len(tasks) - len(failed)}/{len(tasks)} 成功")
    if failed:
        print("失败列表:")
        for n in failed:
            print(f"  · {n}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
