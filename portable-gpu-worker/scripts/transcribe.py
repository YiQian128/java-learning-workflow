#!/usr/bin/env python3
"""
transcribe.py - 使用 faster-whisper 进行语音转文字
输出：.srt 字幕文件 + 词级时间戳 JSON
便携包自包含版本。
"""
import argparse
import json
import re
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: Path, root: Path = WORKER_ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


DEFAULT_PROMPT = (
    "这是一段Java编程教学视频。涉及的技术术语包括："
    "JVM、JDK、JRE、HashMap、ArrayList、LinkedList、TreeMap、HashSet、"
    "synchronized、volatile、ThreadLocal、ReentrantLock、ConcurrentHashMap、"
    "泛型、通配符、反射、注解、Lambda表达式、Stream API、Optional、"
    "接口、抽象类、多态、继承、封装、设计模式、"
    "堆内存、栈内存、方法区、垃圾回收、GC、Young GC、Full GC、"
    "Integer、String、StringBuilder、StringBuffer、"
    "try-catch-finally、throws、Exception、RuntimeException、"
    "Java 8、Java 11、Java 17、Java 21、LTS版本"
)


def _find_cached_model_path(cache_dir: Path, model_name: str) -> Path | None:
    """从 HuggingFace 缓存中查找模型快照目录（含 model.bin 的目录）"""
    repo = f"Systran/faster-whisper-{model_name}"
    cache_name = "models--" + repo.replace("/", "--")
    base = cache_dir / cache_name / "snapshots"
    if not base.exists():
        return None
    for rev_dir in base.iterdir():
        if rev_dir.is_dir() and (rev_dir / "model.bin").exists():
            return rev_dir
    return None


def transcribe(
    video_path: str,
    output_dir: str,
    model_size: str = "medium",
    language: str = "zh",
    prompt: str = DEFAULT_PROMPT,
    beam_size: int = 5,
    device: str = "auto",
    audio_path: str | None = None,
    model_cache_dir: str | None = None
) -> int:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper not installed.", file=sys.stderr)
        return 1

    video = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = _safe_filename(video.stem)
    srt_path = out_dir / f"{safe_stem}.srt"
    words_path = out_dir / f"{safe_stem}_words.json"

    print(f"Loading Whisper model: {model_size} ({device})")

    if device == "auto":
        try:
            import torch
            compute_type = "float16" if torch.cuda.is_available() else "int8"
            device_actual = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            # torch 未安装时，直接用 ctranslate2 检测 CUDA（便携包默认路径）
            try:
                import ctranslate2
                cuda_ok = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                cuda_ok = False
            compute_type = "float16" if cuda_ok else "int8"
            device_actual = "cuda" if cuda_ok else "cpu"
    else:
        device_actual = device
        compute_type = "float16" if device == "cuda" else "int8"

    # 优先使用本地缓存的模型路径（绝对路径），避免路径解析错误
    model_path_or_size = model_size
    download_root = model_cache_dir
    if model_cache_dir:
        cache_path = Path(model_cache_dir).resolve()
        direct_path = _find_cached_model_path(cache_path, model_size)
        if direct_path:
            model_path_or_size = str(direct_path.resolve())
            download_root = None  # 已指定完整路径，不再传 download_root
            print(f"  Using cached model: {direct_path.parent.name}/.../{direct_path.name}")

    model = WhisperModel(model_path_or_size, device=device_actual, compute_type=compute_type,
                         download_root=download_root)

    input_path = video
    if audio_path and Path(audio_path).exists():
        input_path = Path(audio_path)
        print(f"Transcribing from pre-extracted audio: {input_path.name}")
    else:
        print(f"Transcribing: {video.name}")
    print(f"  Language: {language}, Beam size: {beam_size}")

    segments_data, info = model.transcribe(
        str(input_path),
        language=language,
        initial_prompt=prompt,
        beam_size=beam_size,
        word_timestamps=True,
        condition_on_previous_text=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200}
    )

    print(f"  Detected language: {info.language} (probability: {info.language_probability:.2f})")

    segments = []
    for seg in list(segments_data):
        segments.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "words": [
                {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                for w in (seg.words or [])
            ]
        })

    def _format_ts(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        secs = int(s % 60)
        millis = int((s % 1) * 1000)
        return f"{h:02d}:{m:02d}:{secs:02d},{millis:03d}"

    with open(srt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"{seg['id']}\n")
            f.write(f"{_format_ts(seg['start'])} --> {_format_ts(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")

    with open(words_path, "w", encoding="utf-8") as f:
        json.dump({
            "video": _portable_path(video),
            "language": info.language,
            "duration": info.duration,
            "segments": segments
        }, f, ensure_ascii=False, indent=2)

    print(f"  SRT saved: {srt_path} ({len(segments)} segments)")
    print(f"  Words JSON saved: {words_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="视频字幕转写（faster-whisper）")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"])
    parser.add_argument("--language", default="zh")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--audio", help="已提取的音频路径")
    parser.add_argument("--model-cache-dir", help="Whisper 模型缓存目录")
    args = parser.parse_args()

    sys.exit(transcribe(
        args.video, args.output_dir, args.model,
        args.language, args.prompt, args.beam_size, args.device,
        audio_path=args.audio, model_cache_dir=args.model_cache_dir
    ))


if __name__ == "__main__":
    main()
