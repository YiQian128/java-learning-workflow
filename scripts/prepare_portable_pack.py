#!/usr/bin/env python3
"""
prepare_portable_pack.py - 为便携式 GPU 预处理包下载离线资源
委托 portable-gpu-worker/prepare_env.py 执行，确保 _env 下资源完整。
支持 HF_TOKEN 环境变量加速模型下载。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_ROOT = PROJECT_ROOT / "portable-gpu-worker"
PREPARE_SCRIPT = PORTABLE_ROOT / "setup" / "prepare_env.py"


def main():
    if not PORTABLE_ROOT.exists():
        print(f"便携包目录不存在: {PORTABLE_ROOT}")
        sys.exit(1)
    if not PREPARE_SCRIPT.exists():
        print(f"setup/prepare_env.py 不存在: {PREPARE_SCRIPT}")
        sys.exit(1)

    ret = subprocess.run([sys.executable, str(PREPARE_SCRIPT)] + sys.argv[1:])
    sys.exit(ret.returncode)


if __name__ == "__main__":
    main()
