#!/usr/bin/env python3
"""
download_model.py - 下载 Whisper 各体量模型到 _env/models
支持：tiny、base、small、medium、large-v2、large-v3
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "_env"
MODELS_DIR = ENV_DIR / "models"

# 各体量模型（体量从小到大，质量从低到高）
WHISPER_MODELS = [
    ("tiny", "Systran/faster-whisper-tiny", "~75MB"),
    ("base", "Systran/faster-whisper-base", "~145MB"),
    ("small", "Systran/faster-whisper-small", "~465MB"),
    ("medium", "Systran/faster-whisper-medium", "~1.5GB"),
    ("large-v2", "Systran/faster-whisper-large-v2", "~3GB"),
    ("large-v3", "Systran/faster-whisper-large-v3", "~3GB"),
]

# 至少需要这些模型才能正常预处理
MIN_REQUIRED = {"tiny", "base", "medium"}

ALLOW_PATTERNS = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]

MAX_RETRIES = 3
RETRY_DELAY = 5


def _model_cached(repo_id: str) -> bool:
    """检查模型是否已缓存（HuggingFace 缓存格式 models--org--repo）"""
    if not MODELS_DIR.exists():
        return False
    cache_name = "models--" + repo_id.replace("/", "--")
    cache_dir = MODELS_DIR / cache_name
    if not cache_dir.exists():
        return False
    if list(cache_dir.rglob("*.incomplete")):
        return False
    return (cache_dir / "snapshots").exists() or (cache_dir / "blobs").exists()


def main() -> int:
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hf_token:
        # 填入令牌时使用官网下载
        os.environ["HF_ENDPOINT"] = "https://huggingface.co"
        os.environ["HF_TOKEN"] = hf_token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
        print("  使用 HuggingFace 官网（已提供令牌）")
    else:
        # 默认使用国内镜像，无需令牌
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        print("  使用国内镜像 hf-mirror.com（无需令牌）")

    if MODELS_DIR.exists():
        incomplete = list(MODELS_DIR.rglob("*.incomplete"))
        if incomplete:
            print("  检测到未完成的下载，清理不完整缓存...")
            for p in incomplete:
                try:
                    p.unlink()
                except Exception:
                    pass

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("  ERROR: huggingface_hub 未安装")
        return 1

    print("  下载 Whisper 各体量模型（tiny/base/small/medium/large-v2/large-v3）...")
    failed = []
    for name, repo_id, size_hint in WHISPER_MODELS:
        if _model_cached(repo_id):
            print(f"    [{name}] 已缓存，跳过")
            continue
        last_err = None
        cache_name = "models--" + repo_id.replace("/", "--")
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                # 重试前清理该模型缓存，避免断点续传残留导致失败
                cache_dir = MODELS_DIR / cache_name
                if cache_dir.exists():
                    try:
                        shutil.rmtree(cache_dir)
                    except Exception:
                        pass
                time.sleep(RETRY_DELAY)
            try:
                print(f"    [{name}] 下载中（{size_hint}）" + (f" [重试 {attempt}/{MAX_RETRIES}]" if attempt > 1 else "") + "...")
                snapshot_download(
                    repo_id=repo_id,
                    cache_dir=str(MODELS_DIR),
                    local_files_only=False,
                    token=hf_token,
                    allow_patterns=ALLOW_PATTERNS,
                )
                print(f"    [{name}] 完成")
                last_err = None
                break
            except Exception as e:
                last_err = e
                print(f"    [{name}] 失败: {e}")
        if last_err is not None:
            failed.append(name)

    if failed:
        print(f"  部分模型下载失败: {', '.join(failed)}")
        cached = {n for n, rid, _ in WHISPER_MODELS if _model_cached(rid)}
        if MIN_REQUIRED.issubset(cached):
            print("  已具备 tiny/base/medium，可继续使用。可稍后重新运行 0_开始使用.bat → [1] 联网准备 补齐失败模型。")
            return 0
        print("  提示：默认使用国内镜像；若需官网下载，请设置环境变量 HF_TOKEN=hf_xxx")
        return 1
    print("  所有模型已缓存到 _env/models/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
