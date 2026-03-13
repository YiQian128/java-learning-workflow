#!/usr/bin/env python3
"""
split_video.py - 长视频按静音点智能分段
便携包自包含版本。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: str | Path, root: Path = WORKER_ROOT) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(candidate)

DEFAULT_MAX_DURATION = 5400
DEFAULT_TARGET_DURATION = 2700
OVERLAP_SECONDS = 30


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def get_video_duration(video_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr}")
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def detect_silence_points(video_path: str, min_duration: float = 0.5,
                          noise_threshold: str = "-30dB",
                          video_duration: float = 0) -> list[float]:
    timeout = max(1800, int(video_duration * 0.5)) if video_duration > 0 else 1800
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_threshold}:d={min_duration}",
        "-f", "null", "-"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return []
    silence_points = []
    for line in result.stderr.split("\n"):
        match = re.search(r'silence_end:\s*([\d.]+)', line)
        if match:
            silence_points.append(float(match.group(1)))
    return silence_points


def find_best_split_points(duration: float, target_duration: float,
                           silence_points: list[float]) -> list[float]:
    num_segments = max(2, math.ceil(duration / target_duration))
    ideal_points = [duration * i / num_segments for i in range(1, num_segments)]
    split_points = []
    for ideal in ideal_points:
        window_start, window_end = ideal - 120, ideal + 120
        candidates = [p for p in silence_points if window_start <= p <= window_end]
        if candidates:
            split_points.append(min(candidates, key=lambda p: abs(p - ideal)))
        else:
            split_points.append(ideal)
    return sorted(set(split_points))


def split_video(video_path: str, output_dir: str, split_points: list[float],
                duration: float) -> list[dict]:
    video = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segments = []
    boundaries = [0.0] + split_points + [duration]

    for i in range(len(boundaries) - 1):
        start = max(0, boundaries[i] - (OVERLAP_SECONDS if i > 0 else 0))
        end = boundaries[i + 1]
        safe_stem = _safe_filename(video.stem)
        segment_name = f"{safe_stem}_part{i + 1:02d}{video.suffix}"
        segment_path = out_dir / segment_name

        cmd = [
            "ffmpeg", "-y", "-i", str(video),
            "-ss", str(start), "-to", str(end),
            "-c", "copy", "-avoid_negative_ts", "make_zero",
            str(segment_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=600)
        except subprocess.TimeoutExpired:
            continue

        if result.returncode == 0 and segment_path.exists():
            segments.append({
                "index": i + 1,
                "path": str(segment_path),
                "filename": segment_name,
                "start_time": start,
                "end_time": end,
                "duration": end - start,
                "is_first": i == 0,
                "is_last": i == len(boundaries) - 2
            })

    return segments


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def analyze_and_split(video_path: str, output_dir: str,
                      max_duration: float = DEFAULT_MAX_DURATION,
                      target_duration: float = DEFAULT_TARGET_DURATION) -> dict:
    duration = get_video_duration(video_path)
    video_name = Path(video_path).name

    result = {
        "video": _portable_path(video_path),
        "video_name": video_name,
        "total_duration": duration,
        "duration_formatted": _fmt(duration),
        "needs_splitting": duration > max_duration,
    }

    if not result["needs_splitting"]:
        result["segments"] = [{
            "index": 1, "path": _portable_path(video_path), "filename": video_name,
            "start_time": 0, "end_time": duration, "duration": duration,
            "is_first": True, "is_last": True
        }]
        result["num_segments"] = 1
        return result

    print(f"  视频时长 {_fmt(duration)} 超过阈值，开始分段...")
    silence_points = detect_silence_points(video_path, video_duration=duration)
    split_points = find_best_split_points(duration, target_duration, silence_points)
    segments = split_video(video_path, output_dir, split_points, duration)
    result["segments"] = segments
    result["num_segments"] = len(segments)
    result["split_points"] = [_fmt(p) for p in split_points]

    info_path = Path(output_dir) / "_split_info.json"
    info_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="长视频自动分段")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-duration", type=int, default=DEFAULT_MAX_DURATION)
    parser.add_argument("--target-duration", type=int, default=DEFAULT_TARGET_DURATION)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"ERROR: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    result = analyze_and_split(
        args.video, args.output_dir,
        args.max_duration, args.target_duration
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["needs_splitting"]:
            for seg in result["segments"]:
                print(f"  Part {seg['index']}: {seg['filename']}")
        else:
            print(f"视频时长 {result['duration_formatted']}, 无需分段")


if __name__ == "__main__":
    main()
