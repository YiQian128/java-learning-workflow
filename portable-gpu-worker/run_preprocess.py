#!/usr/bin/env python3
"""
run_preprocess.py - 便携包预处理入口
扫描 videos/、交互选择、带进度条执行预处理
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ─── 加载 .env 文件（若存在）────────────────────────────────────────────────
# 支持与 config.yaml 同目录下的 .env 文件，避免将密钥硬编码到配置文件中。
# 不依赖 python-dotenv；已在环境中存在的变量不会被覆盖。
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


_load_dotenv(ROOT / ".env")


VIDEOS_DIR = ROOT / "videos"
OUTPUT_DIR = ROOT / "output"
SCRIPTS_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "config" / "config.yaml"
MODELS_DIR = ROOT / "_env" / "models"

# 体量从小到大
WHISPER_MODEL_NAMES = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
WHISPER_MODEL_DESC = {
    "tiny": "~75MB，最快，精度较低",
    "base": "~145MB，快，精度一般",
    "small": "~465MB，平衡",
    "medium": "~1.5GB，推荐，质量好",
    "large-v2": "~3GB，高质量",
    "large-v3": "~3GB，最高质量",
}

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts"]
LONG_VIDEO_THRESHOLD = 5400
SEGMENT_TARGET = 2700

# 各提供商读取 API Key 时依次尝试的环境变量（第一个非空即用）
PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "openai":      ["OPENAI_API_KEY"],
    "groq":        ["GROQ_API_KEY", "OPENAI_API_KEY"],
    "siliconflow": ["SILICONFLOW_API_KEY", "OPENAI_API_KEY"],
    "aliyun":      ["DASHSCOPE_API_KEY"],
    "azure":       ["AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"],
    "assemblyai":  ["ASSEMBLYAI_API_KEY"],
    "deepgram":    ["DEEPGRAM_API_KEY"],
    "custom":      ["OPENAI_API_KEY"],
}

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "openai":      "OpenAI Whisper",
    "groq":        "Groq",
    "siliconflow": "SiliconFlow",
    "aliyun":      "阿里云 Paraformer",
    "azure":       "Azure OpenAI",
    "assemblyai":  "AssemblyAI",
    "deepgram":    "Deepgram",
    "custom":      "自定义 OpenAI 兼容",
}

# 各提供商默认模型（仅用于菜单展示，实际由 transcribe_api.py 处理）
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai":      "whisper-1",
    "groq":        "whisper-large-v3-turbo",
    "siliconflow": "FunAudioLLM/SenseVoiceSmall",
    "aliyun":      "paraformer-v2",
    "azure":       "whisper",
    "assemblyai":  "best",
    "deepgram":    "nova-3",
    "custom":      "whisper-1",
}


def _ensure_utf8():
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_config() -> dict:
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_video_duration(path: str) -> float:
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def format_duration(s: float) -> str:
    h, m = int(s // 3600), int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def _safe_dirname(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def _get_vram_gb() -> float:
    """通过 nvidia-smi 查询第一张 GPU 的显存（GB），失败返回 0"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return float(r.stdout.strip().split("\n")[0]) / 1024
    except Exception:
        pass
    return 0.0


def _select_model_by_vram(vram_gb: float, available: list[str], source: str) -> tuple[str, str]:
    """根据显存大小从已缓存模型中选出最佳推荐"""
    if vram_gb >= 10 and "large-v3" in available:
        return ("large-v3", f"{source} {vram_gb:.1f}GB 显存，推荐 large-v3")
    if vram_gb >= 8 and "large-v2" in available:
        return ("large-v2", f"{source} {vram_gb:.1f}GB 显存，推荐 large-v2")
    if vram_gb >= 6 and "medium" in available:
        return ("medium", f"{source} {vram_gb:.1f}GB 显存，推荐 medium")
    if vram_gb >= 3 and "small" in available:
        return ("small", f"{source} {vram_gb:.1f}GB 显存，推荐 small")
    if "base" in available:
        return ("base", f"{source} {vram_gb:.1f}GB 显存，推荐 base")
    return (available[0] if available else "tiny", f"{source} 推荐最小可用模型")


def recommend_model_by_hardware(available: list[str]) -> tuple[str, str]:
    """
    根据当前硬件推荐模型，返回 (模型名, 说明)。
    显存参考：tiny/base~1GB, small~2GB, medium~5GB, large-v2/v3~6-10GB
    优先用 torch 检测；torch 不存在时改用 ctranslate2 + nvidia-smi（便携包场景）。
    """
    # 优先路径：torch 已安装
    try:
        import torch
        if torch.cuda.is_available():
            try:
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                return _select_model_by_vram(vram_gb, available, "检测到 GPU")
            except Exception:
                pass
            return ("medium" if "medium" in available else available[0], "检测到 GPU，推荐 medium")
        # torch 在但无 CUDA → CPU
        if "base" in available:
            return ("base", "未检测到 GPU，CPU 模式推荐 base")
        return (available[0] if available else "tiny", "未检测到 GPU，推荐最小可用模型")
    except ImportError:
        pass

    # 备用路径：torch 未安装，用 ctranslate2 检测 CUDA
    cuda_ok = False
    try:
        import ctranslate2
        cuda_ok = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass

    if cuda_ok:
        vram_gb = _get_vram_gb()
        if vram_gb > 0:
            return _select_model_by_vram(vram_gb, available, "检测到 GPU")
        return ("large-v2" if "large-v2" in available else
                "medium" if "medium" in available else
                available[0] if available else "medium",
                "检测到 GPU（显存未知），推荐 large-v2")

    # CPU 兜底
    if "base" in available:
        return ("base", "未检测到 GPU，CPU 模式推荐 base")
    return (available[0] if available else "tiny", "未检测到 GPU，推荐最小可用模型")


def get_available_models() -> list[str]:
    """返回 _env/models 中已缓存的模型列表（与 download_model._model_cached 逻辑一致）"""
    if not MODELS_DIR.exists():
        return []
    available = []
    for name in WHISPER_MODEL_NAMES:
        repo_id = f"Systran/faster-whisper-{name}"
        cache_name = "models--" + repo_id.replace("/", "--")
        cache_dir = MODELS_DIR / cache_name
        if (
            cache_dir.exists()
            and not list(cache_dir.rglob("*.incomplete"))
            and ((cache_dir / "snapshots").exists() or (cache_dir / "blobs").exists())
        ):
            available.append(name)
    return available


def _is_preprocessed(stem: str, rel_dir: Path | None) -> bool:
    """检查视频是否已完成预处理（SRT 文件存在即视为完成）"""
    prep_dir = get_preprocessing_dir(stem, rel_dir=rel_dir)
    return any(prep_dir.glob("*.srt")) if prep_dir.exists() else False


def scan_videos() -> list[dict]:
    if not VIDEOS_DIR.exists():
        return []
    videos = []
    for f in sorted(VIDEOS_DIR.rglob("*")):
        if f.suffix.lower() in VIDEO_EXTENSIONS and not f.name.startswith("."):
            dur = get_video_duration(str(f))
            try:
                rel_dir = f.parent.relative_to(VIDEOS_DIR)
            except ValueError:
                rel_dir = Path(".")
            done = _is_preprocessed(f.stem, rel_dir)
            videos.append({
                "path": str(f), "name": f.name, "stem": f.stem,
                "rel_dir": rel_dir,
                "duration": dur, "duration_fmt": format_duration(dur),
                "is_long": dur > LONG_VIDEO_THRESHOLD,
                "done": done,
            })
    return videos


def get_preprocessing_dir(stem: str, base_stem: str | None = None, rel_dir: Path | None = None) -> Path:
    """base_stem: 长视频分段时使用原视频 stem；rel_dir: 保持与 videos 一致的目录结构"""
    stem_to_use = (base_stem or stem)
    prefix = OUTPUT_DIR
    if rel_dir and str(rel_dir) != ".":
        for part in rel_dir.parts:
            if part != ".":
                prefix = prefix / _safe_dirname(part)
    return prefix / _safe_dirname(stem_to_use) / "_preprocessing"


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

    # 确保子进程能找到 _env/ffmpeg（extract_audio、extract_keyframes、split_video 需要）
    env = dict(os.environ)
    ffmpeg_bin = ROOT / "_env" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")
    # 字幕转写时使用 _env/models 作为 HuggingFace 缓存，避免路径解析错误
    if "transcribe" in str(script) and "transcribe_api" not in str(script):
        models_dir = ROOT / "_env" / "models"
        if models_dir.exists():
            env["HF_HUB_CACHE"] = str(models_dir)

    return subprocess.run([str(py), str(script)] + args, env=env).returncode


def preprocess_one(
    video: Path,
    config: dict,
    model_name: str = "medium",
    force: bool = False,
    is_segment: bool = False,
    base_stem: str | None = None,
    rel_dir: Path | None = None,
    use_api: bool = False,
    api_key: str | None = None,
) -> bool:
    """base_stem: 长视频分段时传入原视频 stem；rel_dir: 保持与 videos 一致的目录结构"""
    safe_stem = _safe_dirname(video.stem)
    prep = get_preprocessing_dir(video.stem, base_stem=base_stem, rel_dir=rel_dir)
    prep.mkdir(parents=True, exist_ok=True)

    audio_path = prep / f"{safe_stem}_audio.wav"
    srt_path = prep / f"{safe_stem}.srt"
    frames_dir = prep / "frames" / safe_stem if is_segment else prep / "frames"

    # 1. 音频
    if not audio_path.exists() or force:
        print("  [1/3] 提取音频...")
        if run_script("extract_audio.py", ["--video", str(video), "--output", str(audio_path)]) != 0:
            return False
    else:
        print("  [1/3] 音频已存在，跳过")

    # 2. 字幕
    if not srt_path.exists() or force:
        wc = config.get("whisper", {})
        lang = wc.get("language", "zh")
        prompt = wc.get("initial_prompt", "")

        if use_api and api_key:
            ac = config.get("api", {})
            _provider = ac.get("provider", "openai")
            _provider_name = PROVIDER_DISPLAY_NAMES.get(_provider, _provider)
            print(f"  [2/3] 字幕转写（在线 API: {_provider_name}）...")
            args = [
                "--audio", str(audio_path),
                "--output-dir", str(prep),
                "--video", str(video),
                "--api-key", api_key,
                "--model", ac.get("model") or "",
                "--language", lang,
                "--prompt", prompt,
                "--provider", _provider,
            ]
            if ac.get("base_url"):
                args += ["--base-url", ac["base_url"]]
            if run_script("transcribe_api.py", args) != 0:
                return False
        else:
            print(f"  [2/3] 字幕转写（模型: {model_name}）...")
            model_cache = str(ROOT / "_env" / "models") if (ROOT / "_env" / "models").exists() else None
            args = [
                "--video", str(video), "--output-dir", str(prep),
                "--model", model_name,
                "--language", lang,
                "--device", wc.get("device", "auto"),
            ]
            if prompt:
                args += ["--prompt", prompt]
            if audio_path.exists():
                args += ["--audio", str(audio_path)]
            if model_cache:
                args += ["--model-cache-dir", model_cache]
            if run_script("transcribe.py", args) != 0:
                return False
    else:
        print("  [2/3] 字幕已存在，跳过")

    # 3. 关键帧
    frames_dir.mkdir(parents=True, exist_ok=True)
    existing = list(frames_dir.glob("*.jpg"))
    if not existing or force:
        print("  [3/3] 提取关键帧...")
        kc = config.get("keyframes", {})
        kf_args = [
            "--video", str(video),
            "--output-dir", str(frames_dir),
            "--threshold", str(kc.get("scene_threshold", 0.25)),
            "--interval", str(kc.get("fallback_interval", 30)),
            "--max-frames", str(kc.get("max_frames_per_video", 80)),
            "--quality", str(kc.get("jpg_quality", 2)),
        ]
        # 自动检测 words.json，启用词级时间戳引导关键帧提取
        # 转写完成后 words.json 与 .srt 在同一目录（prep/）
        words_json_path = prep / f"{safe_stem}_words.json"
        if words_json_path.exists():
            kf_args += [
                "--words-json", str(words_json_path),
                "--words-gap", str(kc.get("words_gap", 0.6)),
                "--words-proximity", str(kc.get("words_proximity", 10.0)),
            ]
            print(f"    [words.json] 已找到词级时间戳，启用智能补帧")
        if run_script("extract_keyframes.py", kf_args) != 0:
            return False
    else:
        print("  [3/3] 关键帧已存在，跳过")

    return True


def _check_venv() -> bool:
    """检查 venv 是否存在且可用。
    先检测 yaml（轻量级，任何模式都需要），再检测 faster_whisper（本地模型需要）。
    两者任一成功即视为 venv 健康，避免纯 API 用户被 faster_whisper CUDA 问题阻断。
    """
    if platform.system() == "Windows":
        venv_py = ROOT / "_env" / "venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT / "_env" / "venv" / "bin" / "python"
    if not venv_py.exists():
        return False
    try:
        r = subprocess.run(
            [str(venv_py), "-c", "import yaml; import openai"],
            capture_output=True,
            cwd=ROOT,
            timeout=15,
        )
        if r.returncode == 0:
            return True
        # 兜底：尝试 faster_whisper（本地模型场景）
        r2 = subprocess.run(
            [str(venv_py), "-c", "import faster_whisper"],
            capture_output=True,
            cwd=ROOT,
            timeout=15,
        )
        return r2.returncode == 0
    except Exception:
        return False


def _parse_selection(choice: str, videos: list[dict]) -> list[dict]:
    """解析用户选择，返回选中的视频列表。choice 如 a/p/1,3,5/1-5"""
    selected = []
    seen_idx = set()
    if choice.lower() == "a":
        selected = list(videos)
    elif choice.lower() == "p":
        selected = [v for v in videos if not v["done"]]
    else:
        for part in choice.replace("，", ",").split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    a, b = int(a.strip()), int(b.strip())
                    if a > b:
                        a, b = b, a
                    for idx in range(a, b + 1):
                        if 1 <= idx <= len(videos) and idx not in seen_idx:
                            seen_idx.add(idx)
                            selected.append(videos[idx - 1])
                except ValueError:
                    pass
            else:
                try:
                    idx = int(part)
                    if 1 <= idx <= len(videos) and idx not in seen_idx:
                        seen_idx.add(idx)
                        selected.append(videos[idx - 1])
                except ValueError:
                    pass
    return selected


def _print_video_list(videos: list[dict], compact: bool = False):
    """打印视频列表。compact=True 时只打印摘要，不逐条列出。"""
    done_count = sum(1 for v in videos if v["done"])
    pending_count = len(videos) - done_count
    print(f"\n找到 {len(videos)} 个视频（已完成: {done_count}，待处理: {pending_count}）")
    if not compact:
        for i, v in enumerate(videos, 1):
            long_mark = " [长视频]" if v["is_long"] else ""
            done_mark = " [已完成]" if v["done"] else ""
            print(f"  {i:>3}. {v['name']}  {v['duration_fmt']}{long_mark}{done_mark}")


def main():
    _ensure_utf8()
    print("便携式 GPU 预处理包 - 开始预处理")
    print("=" * 50)

    if not _check_venv():
        print("\n[错误] 环境未就绪。请先运行 0_开始使用.bat → [1] 联网准备 或 [2] 离线准备")
        sys.exit(1)

    VIDEOS_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 仅扫描一次，后续循环复用
    videos = scan_videos()
    if not videos:
        print(f"\n未找到视频。请将视频放入: {VIDEOS_DIR}")
        return

    _print_video_list(videos)

    default_choice = "p" if sum(1 for v in videos if not v["done"]) > 0 else "a"
    try:
        choice = input(
            f"\n选择要处理的视频 (a=全部, p=仅待处理, 1,3,5 或 1-5, q=取消) [{default_choice}]: "
        ).strip() or default_choice
    except (EOFError, KeyboardInterrupt):
        return

    if choice.lower() == "q":
        return

    # 选择转写方式：本地模型 或 在线 API（仅选一次，后续循环复用）
    config = load_config()
    available = get_available_models()
    api_config = config.get("api", {})

    # 按提供商优先级查找 API Key
    provider = api_config.get("provider", "openai")
    env_vars = PROVIDER_ENV_VARS.get(provider, ["OPENAI_API_KEY"])
    api_key = api_config.get("api_key", "")
    if not api_key:
        for ev in env_vars:
            api_key = os.environ.get(ev, "")
            if api_key:
                break

    use_api = False
    model_name = "medium"
    recommended, reason = recommend_model_by_hardware(available)
    default_model = recommended if recommended in available else (available[0] if available else "medium")

    has_api_option = bool(api_key)
    if not available and not has_api_option:
        print("\n未找到已缓存的 Whisper 模型。请先运行 0_开始使用.bat → [1] 联网准备 下载模型。")
        env_hint = " / ".join(PROVIDER_ENV_VARS.get(provider, ["OPENAI_API_KEY"]))
        print(f"或设置环境变量 {env_hint} 使用在线 API 转写（当前 provider: {provider}）。")
        sys.exit(1)

    provider_name = PROVIDER_DISPLAY_NAMES.get(provider, provider)
    provider_model = api_config.get("model") or PROVIDER_DEFAULT_MODELS.get(provider, "whisper-1")

    print(f"\n{reason}" if available else "\n未缓存本地模型。")
    if has_api_option:
        print(f"  0. 在线 API（{provider_name}，模型: {provider_model}，需消耗 API 额度）")
    if available:
        print(f"  1-{len(available)}. 本地模型（已缓存 {len(available)} 个）:")
        for i, m in enumerate(available, 1):
            desc = WHISPER_MODEL_DESC.get(m, "")
            default_mark = " [推荐]" if m == default_model else ""
            print(f"      {i}. {m} - {desc}{default_mark}")

    try:
        default_hint = "0" if has_api_option and not available else ("1" if available else "0")
        mode_choice = input(f"\n选择 (0=在线API, 1-{len(available)}=本地, 回车={default_hint}): ").strip() or default_hint
    except (EOFError, KeyboardInterrupt):
        return

    if mode_choice == "0" and has_api_option:
        use_api = True
        print(f"使用: 在线 API（{provider_name}, {provider_model}）")
    elif available:
        try:
            idx = int(mode_choice)
            if 1 <= idx <= len(available):
                model_name = available[idx - 1]
            else:
                model_name = default_model
        except ValueError:
            model_name = default_model
        print(f"使用模型: {model_name}")
    else:
        print("\n未选择有效方式，退出。")
        sys.exit(1)

    config = load_config()

    failed_videos: list[str] = []
    ok_count = 0
    is_first_batch = True

    while True:
        selected = _parse_selection(choice, videos)
        if not selected:
            print("\n未选择有效视频，请重新选择。")
            if not is_first_batch:
                try:
                    choice = input("输入范围 (a/p/1-5 等) [q=结束]: ").strip() or "q"
                except (EOFError, KeyboardInterrupt):
                    break
                if choice.lower() == "q":
                    break
                continue
            return

        failed_videos.clear()
        ok_count = 0

        for i, v in enumerate(selected, 1):
            print(f"\n[{i}/{len(selected)}] 处理: {v['name']}")
            video_path = Path(v["path"])
            video_ok = True

            try:
                if v["is_long"]:
                    seg_dir = get_preprocessing_dir(v["stem"], rel_dir=v.get("rel_dir")) / "segments"
                    seg_dir.mkdir(parents=True, exist_ok=True)
                    lc = config.get("long_video", {})
                    run_script("split_video.py", [
                        "--video", str(video_path),
                        "--output-dir", str(seg_dir),
                        "--max-duration", str(lc.get("max_segment_duration", LONG_VIDEO_THRESHOLD)),
                        "--target-duration", str(lc.get("target_segment_duration", SEGMENT_TARGET)),
                        "--json",
                    ])
                    split_info = seg_dir / "_split_info.json"
                    segments = []
                    if split_info.exists():
                        try:
                            data = json.loads(split_info.read_text(encoding="utf-8"))
                            segments = data.get("segments", [])
                        except (json.JSONDecodeError, OSError):
                            pass
                    if not segments:
                        segments = [{"path": str(video_path), "filename": video_path.name}]

                    for j, seg in enumerate(segments):
                        seg_path = Path(seg["path"])
                        print(f"  分段 {j+1}/{len(segments)}: {seg_path.name}")
                        seg_ok = preprocess_one(
                            seg_path, config, model_name=model_name,
                            is_segment=True, base_stem=v["stem"], rel_dir=v.get("rel_dir"),
                            use_api=use_api, api_key=api_key if use_api else None,
                        )
                        if not seg_ok:
                            video_ok = False
                else:
                    video_ok = preprocess_one(
                        video_path, config, model_name=model_name,
                        rel_dir=v.get("rel_dir"),
                        use_api=use_api, api_key=api_key if use_api else None,
                    )
            except KeyboardInterrupt:
                print(f"\n  [中断] 用户按下 Ctrl+C，跳过当前视频，退出处理。")
                failed_videos.append(f"{v['name']}（用户中断）")
                break
            except Exception as e:
                print(f"\n  [错误] 处理 {v['name']} 时发生未预期异常: {e}")
                video_ok = False

            if video_ok:
                ok_count += 1
                v["done"] = True
            else:
                failed_videos.append(v["name"])
                print(f"  [跳过] {v['name']} 处理失败，已记录，继续下一个...")

        # ── 本批汇总 ─────────────────────────────────────────────────────────
        print("\n" + "=" * 50)
        print(f"  处理汇总：本批 {len(selected)} 个，成功 {ok_count} 个，失败 {len(failed_videos)} 个")
        if failed_videos:
            print(f"\n  [本批失败（选 p 可重跑）]")
            for name in failed_videos:
                print(f"    · {name}")
        print("=" * 50)

        is_first_batch = False
        pending = sum(1 for v in videos if not v["done"])
        if pending == 0:
            print("\n全部视频已处理完成。")
            break

        try:
            cont = input(f"\n是否还有需要处理的视频？待处理 {pending} 个 (y/n) [n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cont not in ("y", "yes"):
            break

        _print_video_list(videos, compact=True)
        try:
            default_p = "p" if pending > 0 else "a"
            choice = input(f"输入范围 (a=全部, p=仅待处理[{pending}个], 1-5 或 21-30, q=结束) [{default_p}]: ").strip() or default_p
        except (EOFError, KeyboardInterrupt):
            break
        if choice.lower() == "q":
            break

    print("\n预处理完成。产物位于 output/ 目录。")


if __name__ == "__main__":
    main()
