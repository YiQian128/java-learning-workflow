#!/usr/bin/env python3
"""
setup_env.py - 环境准备与校验统一入口
- 联网模式：校验 _env → 下载/更新资源 → 设置环境 → 校验预处理脚本
- 离线模式：校验 _env → 设置环境 → 校验预处理脚本
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP_DIR = ROOT / "setup"
ENV_DIR = ROOT / "_env"


def _ensure_utf8():
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _get_python_exe() -> Path | None:
    if platform.system() == "Windows":
        venv_py = ENV_DIR / "venv" / "Scripts" / "python.exe"
    else:
        venv_py = ENV_DIR / "venv" / "bin" / "python"
    if venv_py.exists():
        return venv_py
    embed_py = ENV_DIR / "python" / "python.exe"
    if embed_py.exists():
        return embed_py
    return None


def run_prepare_env() -> int:
    prepare = SETUP_DIR / "prepare_env.py"
    if not prepare.exists():
        print("ERROR: prepare_env.py 不存在")
        return 1
    py = sys.executable
    if (ENV_DIR / "python" / "python.exe").exists():
        py = str(ENV_DIR / "python" / "python.exe")
    return subprocess.run([py, str(prepare)], cwd=ROOT).returncode


def run_verify_env() -> int:
    verify = SETUP_DIR / "verify_offline.py"
    if not verify.exists():
        print("ERROR: verify_offline.py 不存在")
        return 1
    py = sys.executable
    if (ENV_DIR / "python" / "python.exe").exists():
        py = str(ENV_DIR / "python" / "python.exe")
    return subprocess.run([py, str(verify)], cwd=ROOT).returncode


def run_download_model() -> int:
    download = SETUP_DIR / "download_model.py"
    if not download.exists():
        print("ERROR: download_model.py 不存在")
        return 1
    py = _get_python_exe()
    if not py or "venv" not in str(py):
        print("  跳过模型下载（venv 未就绪）")
        return 0
    return subprocess.run([str(py), str(download)], cwd=ROOT, env=dict(os.environ)).returncode


def run_bootstrap() -> int:
    bootstrap = SETUP_DIR / "bootstrap_standalone.py"
    if not bootstrap.exists():
        print("ERROR: bootstrap_standalone.py 不存在")
        return 1
    py = sys.executable
    if (ENV_DIR / "python" / "python.exe").exists():
        py = str(ENV_DIR / "python" / "python.exe")
    return subprocess.run([py, str(bootstrap)], cwd=ROOT).returncode


def run_verify_preprocess() -> int:
    scripts = ["extract_audio.py", "transcribe.py", "transcribe_api.py", "extract_keyframes.py", "split_video.py"]
    py = _get_python_exe()
    if not py:
        print("  [FAIL] 未找到 _env 内 Python")
        return 1

    env = dict(os.environ)
    ffmpeg_bin = ENV_DIR / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")

    all_ok = True
    for name in scripts:
        script = ROOT / "scripts" / name
        if not script.exists():
            print(f"  [FAIL] 脚本不存在: {name}")
            all_ok = False
            continue
        r = subprocess.run(
            [str(py), str(script), "--help"],
            capture_output=True, text=True, cwd=ROOT, env=env, timeout=30,
        )
        if r.returncode != 0:
            print(f"  [FAIL] {name} 无法运行")
            all_ok = False
        else:
            print(f"  [OK] {name}")
    return 0 if all_ok else 1


def _get_api_provider() -> str:
    """读取 config.yaml，返回当前配置的 provider（默认 openai）"""
    try:
        import yaml  # noqa: PLC0415
        cfg_path = ROOT / "config" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("api", {}).get("provider", "openai")
    except Exception:
        pass
    return "openai"


def run_install_provider_deps() -> int:
    """根据 config.yaml 中的 provider，安装对应的额外依赖（如 dashscope、oss2）"""
    provider = _get_api_provider()
    extra: dict[str, list[str]] = {
        "aliyun":     ["dashscope>=1.20.0", "oss2>=2.18.0"],
        "assemblyai": ["assemblyai>=0.30.0"],
        "deepgram":   ["deepgram-sdk>=3.0.0"],
    }
    pkgs = extra.get(provider, [])
    if not pkgs:
        return 0

    py = _get_python_exe()
    if not py or "venv" not in str(py):
        print(f"  [跳过] provider={provider} 额外依赖未安装（venv 未就绪）")
        return 0

    print(f"  安装 provider={provider} 额外依赖: {', '.join(pkgs)}")
    r = subprocess.run(
        [str(py), "-m", "pip", "install", "--quiet"] + pkgs,
        cwd=ROOT,
    )
    if r.returncode == 0:
        print(f"  [OK] {', '.join(pkgs)} 安装完成")
    else:
        print(f"  [警告] 部分依赖安装失败，provider={provider} 可能无法正常使用")
    return r.returncode


def main_online() -> int:
    _ensure_utf8()
    print("便携式 GPU 预处理包 - 联网准备")
    print("=" * 50)
    print("将校验 _env、下载/更新资源、设置环境、校验预处理脚本")
    print()

    if run_prepare_env() != 0:
        print("\n[失败] 资源准备未完成")
        return 1
    print()
    if run_bootstrap() != 0:
        print("\n[失败] 环境设置未完成")
        return 1
    print()
    print("安装 provider 专用依赖...")
    run_install_provider_deps()
    print()
    print("[5/5] Whisper 模型")
    if run_download_model() != 0:
        print("\n[失败] 模型下载未完成")
        return 1
    print()
    if run_verify_env() != 0:
        print("\n[失败] _env 校验未通过")
        return 1
    print()
    print("校验预处理脚本...")
    if run_verify_preprocess() != 0:
        print("\n[失败] 预处理脚本校验未通过")
        return 1

    print("\n" + "=" * 50)
    print("联网准备完成。可将整个文件夹复制到目标机器，运行 0_开始使用.bat → [2] 离线准备")
    return 0


def main_offline() -> int:
    _ensure_utf8()
    print("便携式 GPU 预处理包 - 离线准备")
    print("=" * 50)
    print("将校验 _env、设置环境、校验预处理脚本（不联网）")
    print()

    if run_verify_env() != 0:
        print("\n[失败] _env 校验未通过，请先在联网环境运行 0_开始使用.bat → [1] 联网准备")
        return 1
    print()
    if run_bootstrap() != 0:
        print("\n[失败] 环境设置未完成")
        return 1
    print()
    print("校验预处理脚本...")
    if run_verify_preprocess() != 0:
        print("\n[失败] 预处理脚本校验未通过")
        return 1

    print("\n" + "=" * 50)
    print("离线准备完成。将视频放入 videos/，运行 0_开始使用.bat → [3] 开始预处理")
    return 0


def main():
    parser = argparse.ArgumentParser(description="便携包环境准备")
    parser.add_argument("--online", action="store_true", help="联网模式")
    parser.add_argument("--offline", action="store_true", help="离线模式")
    args = parser.parse_args()

    if args.online:
        sys.exit(main_online())
    elif args.offline:
        sys.exit(main_offline())
    else:
        parser.print_help()
        print("\n请指定 --online 或 --offline")
        sys.exit(1)


if __name__ == "__main__":
    main()
