#!/usr/bin/env python3
"""
transcribe_api.py - 使用在线 API（多提供商）进行语音转文字
输出：.srt 字幕文件 + 词级时间戳 JSON

支持的提供商（provider 参数）：
  openai      - OpenAI Whisper API（whisper-1、gpt-4o-transcribe 等）
  groq        - Groq API（whisper-large-v3-turbo，速度极快）
  siliconflow - SiliconFlow（FunAudioLLM/SenseVoiceSmall，中文最优，目前免费）
  aliyun      - 阿里云 DashScope Paraformer（中文专项，词级时间戳，10h/月免费）
  azure       - Azure OpenAI（需设置 base_url）
  assemblyai  - AssemblyAI（需额外安装: pip install assemblyai）
  deepgram    - Deepgram（需额外安装: pip install deepgram-sdk）
  custom      - 任意 OpenAI 兼容接口（需设置 base_url）

阿里云 Paraformer 特别说明：
  - 使用 DashScope SDK（pip install dashscope）
  - API 要求音频文件必须通过公网 URL 访问，本地文件需先上传到阿里云 OSS
  - 需在 config/config.yaml 的 api.aliyun_oss 节中配置 OSS 凭证
  - 支持词级时间戳（begin_time/end_time 单位为毫秒）
  - 仅对语音内容时长计费（静音段不计费），实际费用低于按总时长估算

OSS 上传 ConnectionResetError(10054) 排查：
  - 本脚本已改用分片上传 + 120s 连接超时，多数情况下可缓解
  - 若仍失败：1) 检查防火墙/代理/VPN 2) 在 aliyun_oss 中设 part_size_mb: 1
  - 网络极差时可改用本地 Whisper（选择 1-6 而非 0）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: Path, root: Path = WORKER_ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)

# ─── 常量 ────────────────────────────────────────────────────────────────────

API_FILE_LIMIT = 24 * 1024 * 1024   # 24 MB（OpenAI/Groq 上限约 25 MB，留余量）
CHUNK_DURATION_SEC = 600             # 分片时长：10 分钟/片

# 使用 OpenAI SDK 的提供商（共享同一代码路径）
OPENAI_COMPATIBLE = {"openai", "groq", "siliconflow", "azure", "custom"}

# 各提供商默认参数（用户未在 config 里指定时生效）
PROVIDER_DEFAULTS: dict[str, dict] = {
    "openai": {
        "base_url": None,
        "model": "whisper-1",
        "file_limit": API_FILE_LIMIT,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "whisper-large-v3-turbo",
        "file_limit": API_FILE_LIMIT,
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "FunAudioLLM/SenseVoiceSmall",
        "file_limit": 20 * 1024 * 1024,   # SiliconFlow 单次上限约 20 MB
    },
    "aliyun": {
        "base_url": None,
        "model": "paraformer-v2",           # 推荐：多语种+方言，任意采样率
        "file_limit": 0,                    # DashScope SDK 自行处理
    },
    "azure": {
        "base_url": None,
        "model": "whisper",
        "file_limit": API_FILE_LIMIT,
    },
    "assemblyai": {
        "base_url": None,
        "model": "best",
        "file_limit": 0,    # SDK 自行处理，不在此处限制
    },
    "deepgram": {
        "base_url": None,
        "model": "nova-3",
        "file_limit": 0,
    },
    "custom": {
        "base_url": None,
        "model": "whisper-1",
        "file_limit": API_FILE_LIMIT,
    },
}

# config.yaml 路径（相对于本脚本所在目录的上层）
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

# ─── 加载 .env 文件（若存在）────────────────────────────────────────────────
# 从 config/ 同级目录（portable-gpu-worker/）加载 .env，无需 python-dotenv。
# 已在环境中存在的变量不会被覆盖。
def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    with open(dotenv_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip("\"'")
            if _key and _key not in os.environ:
                os.environ[_key] = _val


_load_dotenv(_CONFIG_PATH.parent.parent / ".env")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def _format_ts(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    secs = int(s % 60)
    millis = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{secs:02d},{millis:03d}"


def _get_audio_duration(path: Path) -> float:
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def _retry(fn, retries: int = 3, initial_delay: float = 3.0):
    """带指数退避的重试；认证错误直接抛出，不重试。"""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if any(kw in err_str for kw in ("401", "403", "invalid_api_key", "authentication", "unauthorized")):
                raise
            if attempt < retries - 1:
                delay = initial_delay * (2 ** attempt)
                # 遇到限速错误延长等待
                if any(kw in err_str for kw in ("429", "rate_limit", "too_many", "quota")):
                    delay = max(delay, 30.0)
                print(f"  请求失败: {e}")
                print(f"  将在 {delay:.0f}s 后重试（第 {attempt + 1}/{retries - 1} 次）...")
                time.sleep(delay)
    raise last_err  # type: ignore[misc]


def _split_audio(audio_path: Path, chunk_dir: Path) -> list[tuple[Path, float]]:
    """将长音频按固定时长切分，返回 [(chunk_path, start_sec), ...]"""
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return [(audio_path, 0.0)]
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[tuple[Path, float]] = []
    start = 0.0
    idx = 0
    while start < duration:
        chunk_path = chunk_dir / f"chunk_{idx:03d}.mp3"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(audio_path),
            "-ss", str(start), "-t", str(CHUNK_DURATION_SEC),
            "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
            str(chunk_path),
        ]
        if subprocess.run(cmd, capture_output=True, timeout=300).returncode != 0:
            break
        if not chunk_path.exists():
            break
        chunks.append((chunk_path, start))
        start += CHUNK_DURATION_SEC
        idx += 1
    return chunks


def _write_outputs(
    segments: list[dict],
    srt_path: Path,
    words_path: Path,
    video: Path,
    detected_lang: str,
    duration: float,
) -> None:
    """将转写结果写入 SRT 和 words JSON 文件。"""
    for i, seg in enumerate(segments, 1):
        seg["id"] = i
    if duration <= 0 and segments:
        duration = max(s["end"] for s in segments)

    with open(srt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"{seg['id']}\n")
            f.write(f"{_format_ts(seg['start'])} --> {_format_ts(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")

    with open(words_path, "w", encoding="utf-8") as f:
        json.dump({
            "video": _portable_path(video),
            "language": detected_lang,
            "duration": duration,
            "segments": segments,
        }, f, ensure_ascii=False, indent=2)


# ─── OpenAI SDK 兼容实现 ───────────────────────────────────────────────────────

def _parse_openai_response(resp, offset: float = 0.0) -> list[dict]:
    """将 OpenAI 兼容 API 响应解析为统一 segments 格式。"""
    out: list[dict] = []
    if hasattr(resp, "segments") and resp.segments:
        for seg in resp.segments:
            words = []
            for w in (getattr(seg, "words", None) or []):
                words.append({
                    "word": getattr(w, "word", str(w)),
                    "start": round(getattr(w, "start", 0.0) + offset, 3),
                    "end": round(getattr(w, "end", 0.0) + offset, 3),
                    "probability": getattr(w, "probability", 1.0),
                })
            out.append({
                "id": len(out) + 1,
                "start": round(seg.start + offset, 3),
                "end": round(seg.end + offset, 3),
                "text": (seg.text or "").strip(),
                "words": words,
            })
    elif hasattr(resp, "text") and resp.text:
        out.append({
            "id": 1,
            "start": round(offset, 3),
            "end": round(offset + CHUNK_DURATION_SEC, 3),
            "text": (resp.text or "").strip(),
            "words": [],
        })
    return out


def _call_openai_transcribe(client, audio_file, model: str, language: str, prompt: str):
    """调用 OpenAI 兼容 transcriptions API，不支持词级时间戳时自动降级。"""
    kwargs: dict = dict(
        model=model,
        file=audio_file,
        response_format="verbose_json",
        language=language or None,
        prompt=prompt or None,
        timestamp_granularities=["segment", "word"],
    )

    def _call():
        return client.audio.transcriptions.create(**kwargs)

    try:
        return _retry(_call)
    except Exception as e:
        if "timestamp_granularities" in str(e) or "granularities" in str(e).lower():
            print("  该提供商不支持词级时间戳，降级为段落级时间戳...")
            kwargs.pop("timestamp_granularities", None)
            return _retry(lambda: client.audio.transcriptions.create(**kwargs))
        raise


def _transcribe_openai_compat(
    audio_path: Path,
    api_key: str,
    model: str,
    language: str,
    prompt: str,
    base_url: str | None,
    provider: str,
) -> tuple[list[dict], str, float]:
    """
    使用 OpenAI SDK 兼容 API 转写，返回 (segments, detected_lang, duration)。
    大文件自动分片，并将上一片末尾文本作为下一片 prompt 以保证技术术语连贯。
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai 未安装。请运行: pip install openai", file=sys.stderr)
        raise

    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    effective_base_url = base_url or defaults["base_url"]
    file_limit: int = defaults["file_limit"]

    client_kwargs: dict = {"api_key": api_key}
    if effective_base_url:
        client_kwargs["base_url"] = effective_base_url
    client = OpenAI(**client_kwargs)

    file_size = audio_path.stat().st_size
    need_chunk = file_limit > 0 and file_size > file_limit

    if need_chunk:
        print(f"  音频 {file_size / 1024 / 1024:.1f} MB 超过 API 限制，将分片处理...")
        with tempfile.TemporaryDirectory() as tmp:
            chunks = _split_audio(audio_path, Path(tmp) / "chunks")
            if not chunks:
                raise RuntimeError("音频分片失败，未能生成任何分片")
            print(f"  共 {len(chunks)} 片，每片约 {CHUNK_DURATION_SEC // 60} 分钟")

            all_segs: list[dict] = []
            current_prompt = prompt
            detected_lang: str = language or "zh"

            for i, (chunk_path, offset) in enumerate(chunks):
                print(f"  转写片段 {i + 1}/{len(chunks)}（偏移 {offset:.0f}s）...")
                with open(chunk_path, "rb") as f:
                    resp = _call_openai_transcribe(client, f, model, language, current_prompt)

                segs = _parse_openai_response(resp, offset)
                all_segs.extend(segs)

                # 将本片最后几句话作为下一片 prompt，提高跨片技术术语一致性
                if segs:
                    tail = " ".join(s["text"] for s in segs[-3:])
                    current_prompt = tail[-200:]
                else:
                    current_prompt = prompt

                if hasattr(resp, "language") and resp.language:
                    detected_lang = resp.language

        duration = _get_audio_duration(audio_path)
        if duration <= 0 and all_segs:
            duration = max(s["end"] for s in all_segs)
        return all_segs, detected_lang, duration

    else:
        # 单次请求，必要时先转为 mp3 以减小体积
        tmp_path: Path | None = None
        try:
            if audio_path.suffix.lower() not in (".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg", ".flac"):
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-i", str(audio_path), "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
                     str(tmp_path)],
                    capture_output=True, timeout=600, check=True
                )
                src = tmp_path
            else:
                src = audio_path

            print(f"  调用 {provider} API（模型: {model}）...")
            with open(src, "rb") as f:
                resp = _call_openai_transcribe(client, f, model, language, prompt)

        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        detected_lang = getattr(resp, "language", None) or language or "zh"
        duration = float(getattr(resp, "duration", None) or 0.0)
        segs = _parse_openai_response(resp)
        if duration <= 0 and segs:
            duration = max(s["end"] for s in segs)
        return segs, detected_lang, duration


# ─── 阿里云 DashScope Paraformer 实现 ─────────────────────────────────────────

def _load_aliyun_oss_config() -> dict:
    """从 config.yaml 读取 api.aliyun_oss 配置节；空字段自动从环境变量补全。"""
    try:
        import yaml  # type: ignore
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        oss = cfg.get("api", {}).get("aliyun_oss", {})
    except Exception:
        oss = {}
    # 环境变量回退（config.yaml 留空时自动读取）
    if not oss.get("access_key_id"):
        oss["access_key_id"] = os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID", "")
    if not oss.get("access_key_secret"):
        oss["access_key_secret"] = os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET", "")
    if not oss.get("bucket_name"):
        oss["bucket_name"] = os.environ.get("ALIYUN_OSS_BUCKET", "")
    return oss


def _upload_to_oss(audio_path: Path, oss_cfg: dict) -> tuple[str, "callable[[], None]"]:
    """
    将本地音频文件上传到阿里云 OSS，返回 (签名 URL, 清理函数)。
    签名 URL 有效期 7200 秒（2 小时），留有充足余量。
    使用分片上传 + 较长超时 + 重试，降低 ConnectionResetError(10054) 发生率。
    """
    try:
        import oss2  # type: ignore
        from oss2.resumable import resumable_upload, make_upload_store  # type: ignore
    except ImportError:
        raise RuntimeError(
            "oss2 未安装，阿里云 Paraformer 需要 OSS 上传本地文件。\n"
            "安装方式: pip install oss2"
        )

    endpoint     = oss_cfg.get("endpoint", "oss-cn-beijing.aliyuncs.com").strip()
    access_key   = oss_cfg.get("access_key_id", "").strip()
    secret_key   = oss_cfg.get("access_key_secret", "").strip()
    bucket_name  = oss_cfg.get("bucket_name", "").strip()
    prefix       = oss_cfg.get("prefix", "paraformer-tmp/").rstrip("/") + "/"
    connect_timeout = float(oss_cfg.get("connect_timeout", 120))
    part_size_mb    = float(oss_cfg.get("part_size_mb", 2))

    if not all([access_key, secret_key, bucket_name]):
        raise RuntimeError(
            "阿里云 OSS 凭证未配置。请在 config/config.yaml 的 api.aliyun_oss 节填写：\n"
            "  access_key_id, access_key_secret, bucket_name"
        )

    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}"

    auth   = oss2.Auth(access_key, secret_key)
    bucket = oss2.Bucket(auth, endpoint, bucket_name, connect_timeout=connect_timeout)

    obj_key = f"{prefix}{audio_path.stem}_{int(time.time())}{audio_path.suffix}"
    file_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"    [Paraformer] 上传到 OSS: {bucket_name}/{obj_key} ({file_mb:.1f} MB)", flush=True)

    part_size = max(1024 * 1024, int(part_size_mb * 1024 * 1024))
    store_dir = Path(tempfile.gettempdir()) / "paraformer_oss_store"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = make_upload_store(root=str(store_dir))

    def _do_upload():
        resumable_upload(
            bucket, obj_key, str(audio_path),
            store=store,
            multipart_threshold=0,
            part_size=part_size,
            num_threads=1,
        )

    _retry(_do_upload, retries=4, initial_delay=5.0)

    # 生成签名 URL（2 小时有效期，留出充足余量）
    signed_url = bucket.sign_url("GET", obj_key, 7200, slash_safe=True)

    def _cleanup() -> None:
        try:
            bucket.delete_object(obj_key)
            print(f"    [Paraformer] OSS 临时文件已删除: {obj_key}", flush=True)
        except Exception as e:
            print(f"    [Paraformer] [警告] OSS 清理失败（可手动删除 {obj_key}）: {e}", flush=True)

    return signed_url, _cleanup


def _parse_paraformer_result(result_json: dict, offset: float = 0.0) -> list[dict]:
    """
    将 Paraformer 录音文件识别结果 JSON 解析为统一 segments 格式。

    结果 JSON 结构（来自 transcription_url）：
      transcripts[].sentences[].begin_time  (毫秒)
      transcripts[].sentences[].end_time    (毫秒)
      transcripts[].sentences[].text        (整句文字)
      transcripts[].sentences[].words[].begin_time / end_time / text / punctuation
    """
    segs: list[dict] = []
    for transcript in result_json.get("transcripts", []):
        for sentence in transcript.get("sentences", []):
            text = (sentence.get("text") or "").strip()
            if not text:
                continue
            begin_ms = sentence.get("begin_time", 0)
            end_ms   = sentence.get("end_time",   0)

            # 词级时间戳（begin_time/end_time 均为毫秒）
            words: list[dict] = []
            for w in (sentence.get("words") or []):
                w_text = (w.get("text") or "") + (w.get("punctuation") or "")
                if w_text.strip():
                    words.append({
                        "word":  w_text,
                        "start": round(offset + w.get("begin_time", 0) / 1000.0, 3),
                        "end":   round(offset + w.get("end_time",   0) / 1000.0, 3),
                    })

            segs.append({
                "id":    len(segs) + 1,
                "start": round(offset + begin_ms / 1000.0, 3),
                "end":   round(offset + end_ms   / 1000.0, 3),
                "text":  text,
                "words": words,
            })
    return segs


def _transcribe_aliyun_paraformer(
    audio_path: Path,
    language: str,
    api_key: str,
    model: str = "paraformer-v2",
    oss_cfg: dict | None = None,
) -> tuple[list[dict], str, float]:
    """
    使用阿里云 DashScope Paraformer API 转写，返回 (segments, detected_lang, duration)。

    工作流：
      1. 将本地音频上传到 OSS，获取签名 URL（API 不支持本地文件直传）
      2. 提交异步转写任务（Transcription.async_call）
      3. 阻塞等待任务完成（Transcription.wait）
      4. 下载 transcription_url 中的结果 JSON
      5. 解析段落 + 词级时间戳
      6. 清理 OSS 临时文件
    """
    try:
        import dashscope  # type: ignore
        from dashscope.audio.asr import Transcription  # type: ignore
        from http import HTTPStatus
    except ImportError:
        raise RuntimeError(
            "dashscope 未安装，阿里云 Paraformer 需要 DashScope SDK。\n"
            "安装方式: pip install dashscope"
        )

    dashscope.api_key = api_key
    effective_model = model or "paraformer-v2"

    # ── 上传到 OSS 获取公网 URL ────────────────────────────────────────────────
    cfg = oss_cfg or _load_aliyun_oss_config()
    file_url, oss_cleanup = _upload_to_oss(audio_path, cfg)
    print(f"    [Paraformer] OSS 上传完成，提交转写任务（模型: {effective_model}）...", flush=True)

    all_segs: list[dict] = []
    detected_lang = language or "zh"
    duration = 0.0

    try:
        # ── 构造 language_hints ────────────────────────────────────────────────
        # paraformer-v2 支持 zh/en/ja/yue/ko/de/fr/ru
        lang_map = {
            "zh": ["zh", "en"], "en": ["en"], "ja": ["ja"],
            "ko": ["ko"], "de": ["de"], "fr": ["fr"],
        }
        language_hints = lang_map.get((language or "zh").lower(), ["zh", "en"])

        # ── 提交异步任务 ──────────────────────────────────────────────────────
        task_resp = _retry(
            lambda: Transcription.async_call(
                model=effective_model,
                file_urls=[file_url],
                language_hints=language_hints,   # 仅 paraformer-v2 支持
                timestamp_alignment_enabled=True, # 启用时间戳校准，提高同步精度
            ),
            retries=3,
            initial_delay=5.0,
        )

        task_id = task_resp.output.task_id
        print(f"    [Paraformer] 任务 ID: {task_id}，开始轮询...", flush=True)

        # ── 手动轮询（替代 Transcription.wait，支持超时和网络重连）────────────
        # 最多等待 3600s（1 小时）；每次 poll 失败允许最多 5 次网络重试
        POLL_INTERVAL  = 12   # 秒：两次 poll 的间隔
        POLL_TIMEOUT   = 3600 # 秒：总超时（1 小时）
        poll_start     = time.time()
        last_status    = ""
        network_errors = 0
        MAX_NET_ERRORS = 10   # 连续网络错误上限

        while True:
            elapsed = time.time() - poll_start
            if elapsed > POLL_TIMEOUT:
                raise RuntimeError(
                    f"Paraformer 任务等待超时（>{POLL_TIMEOUT}s），task_id={task_id}\n"
                    f"可登录阿里云控制台手动查询任务状态。"
                )

            try:
                # 优先用 fetch（非阻塞单次查询），不可用时退回 wait
                if hasattr(Transcription, "fetch"):
                    poll_resp = Transcription.fetch(task=task_id)
                else:
                    poll_resp = Transcription.wait(task=task_id)

                network_errors = 0  # 成功则重置连续错误计数

                if poll_resp.status_code != HTTPStatus.OK:
                    raise RuntimeError(
                        f"Paraformer 轮询失败: HTTP {poll_resp.status_code} "
                        f"{getattr(poll_resp, 'message', '')}"
                    )

                p_output = poll_resp.output
                task_status = (
                    getattr(p_output, "task_status", None)
                    or (p_output.get("task_status", "") if isinstance(p_output, dict) else "")
                )

                if task_status != last_status:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    print(
                        f"    [Paraformer] 状态: {task_status}（已等待 {mins:02d}:{secs:02d}）",
                        flush=True,
                    )
                    last_status = task_status

                if task_status == "SUCCEEDED":
                    transcribe_resp = poll_resp
                    break
                elif task_status == "FAILED":
                    raise RuntimeError(f"Paraformer 任务失败: {p_output}")
                # PENDING / RUNNING → 继续等待

                # 使用 wait 时它已阻塞完成，直接退出
                if not hasattr(Transcription, "fetch"):
                    transcribe_resp = poll_resp
                    break

            except RuntimeError:
                raise  # 任务失败类错误直接向上抛
            except Exception as e:
                network_errors += 1
                print(
                    f"    [Paraformer] [警告] 轮询网络错误（第 {network_errors} 次）: {e}",
                    flush=True,
                )
                if network_errors >= MAX_NET_ERRORS:
                    raise RuntimeError(
                        f"Paraformer 轮询连续 {MAX_NET_ERRORS} 次网络错误，放弃。"
                        f"task_id={task_id}"
                    ) from e

            time.sleep(POLL_INTERVAL)

        output = transcribe_resp.output

        # ── 解析子任务结果 ────────────────────────────────────────────────────
        # output.results 是一个列表，每个元素对应一个 file_url
        results = getattr(output, "results", None) or (output.get("results", []) if isinstance(output, dict) else [])
        if not results:
            raise RuntimeError("Paraformer 未返回任何结果")

        result = results[0]
        subtask_status = result.get("subtask_status", "")
        if subtask_status != "SUCCEEDED":
            err_code = result.get("code", "unknown")
            err_msg  = result.get("message", "")
            raise RuntimeError(
                f"Paraformer 子任务失败: [{err_code}] {err_msg}"
            )

        # ── 下载并解析结果 JSON（带重试）────────────────────────────────────
        result_url = result.get("transcription_url", "")
        if not result_url:
            raise RuntimeError("Paraformer 未返回 transcription_url")

        print(f"    [Paraformer] 下载识别结果...", flush=True)

        def _download_result() -> dict:
            with urllib.request.urlopen(result_url, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))

        result_json = _retry(_download_result, retries=4, initial_delay=5.0)

        all_segs = _parse_paraformer_result(result_json)

        # 从结果中提取语音内容时长（仅语音段，非总时长，即计费时长）
        for transcript in result_json.get("transcripts", []):
            content_ms = transcript.get("content_duration_in_milliseconds", 0)
            if content_ms > 0:
                duration = max(duration, content_ms / 1000.0)

        # 若结果中没有语音时长字段，从 segments 推断
        if duration <= 0 and all_segs:
            duration = max(s["end"] for s in all_segs)

        print(
            f"    [Paraformer] 完成：{len(all_segs)} 段，"
            f"语音内容时长 {duration:.1f}s（计费时长）",
            flush=True,
        )

    finally:
        # 无论成功失败，都清理 OSS 临时文件
        oss_cleanup()

    return all_segs, detected_lang, duration


# ─── AssemblyAI 实现 ───────────────────────────────────────────────────────────

def _transcribe_assemblyai(
    audio_path: Path,
    language: str,
    api_key: str,
    model: str = "best",
) -> tuple[list[dict], str, float]:
    """使用 AssemblyAI API 转写，返回 (segments, detected_lang, duration)。"""
    try:
        import assemblyai as aai
    except ImportError:
        raise ImportError(
            "assemblyai 未安装，请运行: pip install assemblyai"
        )

    aai.settings.api_key = api_key

    # AssemblyAI 语言代码映射
    lang_map = {"zh": "zh", "en": "en_us", "ja": "ja", "ko": "ko", "fr": "fr", "de": "de"}
    lang_code = lang_map.get((language or "").lower(), language) if language else None

    speech_model = aai.SpeechModel.nano if model == "nano" else aai.SpeechModel.best
    config = aai.TranscriptionConfig(
        language_code=lang_code,
        speech_model=speech_model,
        punctuate=True,
        format_text=True,
    )

    transcriber = aai.Transcriber(config=config)
    print(f"  上传并转写（AssemblyAI, model={model}）...")
    transcript = _retry(
        lambda: transcriber.transcribe(str(audio_path)),
        retries=2, initial_delay=5.0,
    )

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI 转写失败: {transcript.error}")

    detected_lang = getattr(transcript, "language_code", None) or language or "zh"
    audio_duration = float(transcript.audio_duration or 0.0)

    segs: list[dict] = []
    if transcript.utterances:
        for utt in transcript.utterances:
            words = [
                {
                    "word": w.text,
                    "start": round(w.start / 1000, 3),
                    "end": round(w.end / 1000, 3),
                    "probability": float(w.confidence or 1.0),
                }
                for w in (utt.words or [])
            ]
            segs.append({
                "id": len(segs) + 1,
                "start": round(utt.start / 1000, 3),
                "end": round(utt.end / 1000, 3),
                "text": (utt.text or "").strip(),
                "words": words,
            })
    elif transcript.text:
        segs = [{"id": 1, "start": 0.0, "end": audio_duration, "text": transcript.text.strip(), "words": []}]

    return segs, detected_lang, audio_duration


# ─── Deepgram 实现 ─────────────────────────────────────────────────────────────

def _transcribe_deepgram(
    audio_path: Path,
    language: str,
    api_key: str,
    model: str = "nova-3",
) -> tuple[list[dict], str, float]:
    """使用 Deepgram API 转写，返回 (segments, detected_lang, duration)。"""
    try:
        from deepgram import DeepgramClient, PrerecordedOptions, FileSource  # type: ignore
    except ImportError:
        raise ImportError(
            "deepgram-sdk 未安装，请运行: pip install deepgram-sdk"
        )

    client = DeepgramClient(api_key)
    print(f"  上传并转写（Deepgram, model={model}）...")

    with open(audio_path, "rb") as f:
        buf = f.read()

    payload: FileSource = {"buffer": buf}
    options = PrerecordedOptions(
        model=model,
        language=language or "zh-CN",
        smart_format=True,
        utterances=True,
        punctuate=True,
        diarize=False,
    )

    resp = _retry(
        lambda: client.listen.prerecorded.v("1").transcribe_file(payload, options),
        retries=3, initial_delay=3.0,
    )

    detected_lang = language or "zh"
    duration = 0.0
    segs: list[dict] = []

    try:
        if resp.metadata and hasattr(resp.metadata, "duration"):
            duration = float(resp.metadata.duration or 0.0)

        channels = (resp.results.channels or []) if resp.results else []
        if channels and hasattr(channels[0], "detected_language"):
            detected_lang = channels[0].detected_language or detected_lang

        for utt in (resp.results.utterances or []):
            words = [
                {
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": float(w.confidence or 1.0),
                }
                for w in (utt.words or [])
            ]
            segs.append({
                "id": len(segs) + 1,
                "start": round(utt.start, 3),
                "end": round(utt.end, 3),
                "text": (utt.transcript or "").strip(),
                "words": words,
            })

        if not segs and channels:
            for alt in (channels[0].alternatives or []):
                if alt.transcript:
                    segs = [{"id": 1, "start": 0.0, "end": duration,
                             "text": alt.transcript.strip(), "words": []}]
                    break

    except Exception as e:
        raise RuntimeError(f"Deepgram 响应解析失败: {e}") from e

    return segs, detected_lang, duration


# ─── 主入口 ────────────────────────────────────────────────────────────────────

def transcribe_api(
    audio_path: str,
    output_dir: str,
    video_path: str,
    api_key: str,
    model: str = "",
    language: str = "zh",
    prompt: str = "",
    base_url: str | None = None,
    provider: str = "openai",
) -> int:
    """
    使用在线 API 转写音频，输出 SRT 字幕与词级 JSON。
    provider: openai / groq / siliconflow / azure / assemblyai / deepgram / custom
    """
    audio = Path(audio_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video = Path(video_path)
    safe_stem = _safe_filename(video.stem)
    srt_path = out_dir / f"{safe_stem}.srt"
    words_path = out_dir / f"{safe_stem}_words.json"

    # 未指定 model 时使用提供商默认值
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    effective_model = model or defaults["model"]

    try:
        if provider == "aliyun":
            segs, detected_lang, duration = _transcribe_aliyun_paraformer(
                audio, language, api_key, effective_model
            )
        elif provider == "assemblyai":
            segs, detected_lang, duration = _transcribe_assemblyai(
                audio, language, api_key, effective_model
            )
        elif provider == "deepgram":
            segs, detected_lang, duration = _transcribe_deepgram(
                audio, language, api_key, effective_model
            )
        else:
            segs, detected_lang, duration = _transcribe_openai_compat(
                audio, api_key, effective_model, language, prompt, base_url, provider
            )
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: 转写失败: {e}", file=sys.stderr)
        return 1

    if not segs:
        print("ERROR: 未获得任何转写结果", file=sys.stderr)
        return 1

    print(f"  检测语言: {detected_lang}")
    _write_outputs(segs, srt_path, words_path, video, detected_lang, duration)
    print(f"  SRT 已保存: {srt_path}（{len(segs)} 段）")
    print(f"  词级 JSON 已保存: {words_path}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="在线 API 语音转文字（多提供商）")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--video", required=True, help="原视频路径（用于输出文件名）")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="", help="转写模型（留空则使用提供商默认值）")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--base-url", default="", help="API 基础 URL（OpenAI 兼容接口可选）")
    parser.add_argument(
        "--provider", default="openai",
        choices=sorted(PROVIDER_DEFAULTS.keys()),
        help="API 提供商（aliyun 需配置 OSS 凭证，见 config/config.yaml）",
    )
    args = parser.parse_args()
    sys.exit(transcribe_api(
        args.audio, args.output_dir, args.video,
        api_key=args.api_key,
        model=args.model,
        language=args.language,
        prompt=args.prompt,
        base_url=args.base_url or None,
        provider=args.provider,
    ))
