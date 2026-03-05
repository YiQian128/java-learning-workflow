#!/usr/bin/env python3
"""
extract_audio.py - 从视频中提取16kHz单声道WAV音频，用于Whisper转写
便携包自包含版本，路径以 Path(__file__).resolve().parent 为基准。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def extract_audio(video_path: str, output_path: str, denoise: bool = False) -> int:
    """
    提取视频音频为 16kHz 单声道 WAV。
    16kHz 是 Whisper 最优输入格式。
    """
    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found. Please install FFmpeg.", file=sys.stderr)
        return 1

    video = Path(video_path)
    if not video.exists():
        print(f"ERROR: Video file not found: {video_path}", file=sys.stderr)
        return 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if denoise:
        audio_filter = "anlmdn=s=7,highpass=f=80,lowpass=f=8000"
    else:
        audio_filter = "highpass=f=80,lowpass=f=8000"

    cmd = [
        "ffmpeg",
        "-i", str(video),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        "-af", audio_filter,
        str(output), "-y", "-loglevel", "error"
    ]

    try:
        result = subprocess.run(cmd, timeout=1800)
    except subprocess.TimeoutExpired:
        print("ERROR: Audio extraction timed out after 30 minutes", file=sys.stderr)
        return 1
    if result.returncode == 0:
        size = output.stat().st_size / 1024 / 1024
        print(f"Audio extracted: {output} ({size:.1f} MB)")
    else:
        print(f"ERROR: Audio extraction failed (exit code {result.returncode})", file=sys.stderr)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="提取视频音频为WAV格式")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--denoise", action="store_true")
    args = parser.parse_args()
    sys.exit(extract_audio(args.video, args.output, args.denoise))


if __name__ == "__main__":
    main()
