#!/usr/bin/env python3
"""
bootstrap_standalone.py - 便携包环境初始化（纯离线）
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "_env"
VENV_DIR = ENV_DIR / "venv"
PYTHON_EMBED = ENV_DIR / "python"
FFMPEG_DIR = ENV_DIR / "ffmpeg"
WHEELS_DIR = ENV_DIR / "wheels"
MODELS_DIR = ENV_DIR / "models"
REQUIREMENTS = ROOT / "requirements.txt"
GET_PIP = ENV_DIR / "get-pip.py"


def _ensure_utf8():
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_cmd(cmd: list, cwd: Path | None = None, env: dict | None = None,
            capture: bool = True, print_on_fail: bool = True) -> int:
    """capture=False 时实时输出（用于 pip install 等长时间操作）"""
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(
        cmd, cwd=cwd or ROOT, env=e,
        capture_output=capture, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 and capture and print_on_fail and (r.stdout or r.stderr):
        if r.stdout:
            print(r.stdout, end="")
        if r.stderr:
            print(r.stderr, end="", file=sys.stderr)
    return r.returncode


def main():
    _ensure_utf8()
    print("便携式 GPU 预处理包 - 环境补齐（离线）")
    print("=" * 50)

    ENV_DIR.mkdir(exist_ok=True)

    for pth in (PYTHON_EMBED).glob("*.pth") if PYTHON_EMBED.exists() else []:
        content = pth.read_text(encoding="utf-8")
        if "#import site" in content:
            pth.write_text(content.replace("#import site", "import site"), encoding="utf-8")

    python_exe = sys.executable
    if (PYTHON_EMBED / "python.exe").exists():
        python_exe = str(PYTHON_EMBED / "python.exe")
        print(f"使用便携 Python: {python_exe}")
    else:
        print(f"使用系统 Python: {python_exe}")

    venv_py_win = VENV_DIR / "Scripts" / "python.exe"
    venv_py_unix = VENV_DIR / "bin" / "python"
    venv_python = venv_py_win if platform.system() == "Windows" else venv_py_unix

    # 若 venv 已存在，校验是否可用（复制到新机器后可能失效）
    if venv_python.exists():
        try:
            r = subprocess.run(
                [str(venv_python), "-c", "import faster_whisper"],
                capture_output=True,
                cwd=ROOT,
                timeout=15,
            )
            if r.returncode != 0:
                raise RuntimeError("faster_whisper import failed")
        except Exception:
            print("\n检测到 venv 不可用（可能从其他机器复制），将重建...")
            shutil.rmtree(VENV_DIR, ignore_errors=True)
            venv_python = None

    if not venv_python or not venv_python.exists():
        print("\n创建虚拟环境...")
        # 嵌入式 Python 无 venv 模块，必须用 virtualenv
        use_embed = (PYTHON_EMBED / "python.exe").exists()
        ret = 1 if use_embed else run_cmd([python_exe, "-m", "venv", str(VENV_DIR)])
        if ret != 0:
            shutil.rmtree(VENV_DIR, ignore_errors=True)
            # 仅当 pip 不可用时才运行 get-pip（get-pip 需联网，离线会卡住）
            pip_ok = subprocess.run(
                [python_exe, "-m", "pip", "--version"],
                capture_output=True, cwd=ROOT, timeout=10,
            ).returncode == 0
            if not pip_ok and GET_PIP.exists():
                print("  安装 pip（需联网）...")
                run_cmd([python_exe, str(GET_PIP), "-q"])
            elif not pip_ok:
                print("  [FAIL] pip 不可用且无 get-pip.py，请先在联网环境运行 0_开始使用.bat → [1] 联网准备")
                sys.exit(1)
            has_wheels = WHEELS_DIR.exists() and bool(list(WHEELS_DIR.glob("*.whl")))
            print("  安装 virtualenv...")
            if has_wheels:
                ret = run_cmd([python_exe, "-m", "pip", "install", "--no-index", "--find-links", str(WHEELS_DIR), "virtualenv", "-q"])
            else:
                ret = run_cmd([python_exe, "-m", "pip", "install", "virtualenv", "-q"])
            if ret != 0:
                print("  [FAIL] virtualenv 安装失败")
                sys.exit(1)
            print("  创建 venv 目录...")
            # 使用 --no-seed 避免 virtualenv 自带的 pip 与 Python 3.12 不兼容导致损坏
            used_venv_fallback = False
            ret = run_cmd([python_exe, "-m", "virtualenv", "--no-seed", str(VENV_DIR)])
            if ret != 0:
                # 便携 Python 可能因权限/杀毒等失败，尝试用其他 Python（含 venv 模块）创建
                print("  便携 Python 创建失败，尝试其他 Python...")
                shutil.rmtree(VENV_DIR, ignore_errors=True)
                time.sleep(1)  # 等待文件句柄释放
                fallback_py = None
                for candidate in [
                    ROOT.parent / ".venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python"),
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
                ]:
                    if candidate and Path(candidate).exists():
                        r = subprocess.run([str(candidate), "-c", "import venv"], capture_output=True, timeout=5)
                        if r.returncode == 0:
                            fallback_py = str(candidate)
                            break
                if not fallback_py:
                    fallback_py = shutil.which("python")
                if fallback_py:
                    ret = run_cmd([fallback_py, "-m", "venv", str(VENV_DIR)])
                if not fallback_py or ret != 0:
                    print("  [FAIL] 虚拟环境创建失败。请尝试：以管理员身份运行 0_开始使用.bat，或临时关闭杀毒软件")
                    sys.exit(1)
                used_venv_fallback = True
            # 安装/修复 pip（virtualenv --no-seed 无 pip；venv fallback 的 pip 可能损坏）
            if GET_PIP.exists():
                print("  安装 pip...")
                venv_py = str(VENV_DIR / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python"))
                get_pip_args = [venv_py, str(GET_PIP), "-q"]
                if WHEELS_DIR.exists() and list(WHEELS_DIR.glob("pip*.whl")):
                    get_pip_args.extend(["--no-index", "--find-links", str(WHEELS_DIR)])
                ret = run_cmd(get_pip_args)
                if ret != 0:
                    print("  [FAIL] pip 安装失败")
                    sys.exit(1)
    venv_python = venv_py_win if platform.system() == "Windows" else venv_py_unix
    if not venv_python.exists():
        venv_python = Path(python_exe)

    print("\n安装依赖...")
    has_wheels = WHEELS_DIR.exists() and bool(list(WHEELS_DIR.glob("*.whl")))
    if has_wheels:
        pip_args = ["install", "--no-index", "--find-links", str(WHEELS_DIR), "-r", str(REQUIREMENTS)]
        print("  使用 _env/wheels 离线安装（约 1–3 分钟）...")
    else:
        pip_args = ["install", "-r", str(REQUIREMENTS)]
        print("  未找到 wheels，将尝试联网安装...")
    run_cmd([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "-q"], capture=True)
    ret = run_cmd([str(venv_python), "-m", "pip"] + pip_args, capture=False)
    if ret != 0:
        print("\n  [FAIL] 依赖安装失败")
        sys.exit(1)
    print("  依赖安装完成")

    ffmpeg_zip = ENV_DIR / "ffmpeg.zip"
    if ffmpeg_zip.exists() and not (FFMPEG_DIR / "bin" / "ffmpeg.exe").exists():
        print("\n解压 FFmpeg...")
        FFMPEG_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(ffmpeg_zip, "r") as z:
            z.extractall(FFMPEG_DIR)
        for sub in FFMPEG_DIR.iterdir():
            if sub.is_dir() and (sub / "bin" / "ffmpeg.exe").exists():
                for item in sub.iterdir():
                    shutil.move(str(item), str(FFMPEG_DIR))
                sub.rmdir()
                break
        print("  FFmpeg 已解压到 _env/ffmpeg/")

    ffmpeg_bin = FFMPEG_DIR / "bin"
    if ffmpeg_bin.exists():
        os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + os.environ.get("PATH", "")
        print(f"\nFFmpeg: {ffmpeg_bin}")

    MODELS_DIR.mkdir(exist_ok=True)
    print(f"Whisper 模型: {MODELS_DIR}")

    # 验证 faster_whisper 可导入
    r = subprocess.run(
        [str(venv_python), "-c", "import faster_whisper; print('OK')"],
        capture_output=True, text=True, cwd=ROOT, timeout=15,
    )
    if r.returncode != 0:
        print("\n  [WARN] faster_whisper 导入校验未通过，预处理可能受影响")
        if r.stderr:
            for line in r.stderr.strip().split("\n")[:5]:
                print(f"    {line}")
    else:
        print("\n  [OK] faster_whisper 校验通过")

    print("\n环境补齐完成。将视频放入 videos/，运行 0_开始使用.bat → [3] 开始预处理")


if __name__ == "__main__":
    main()
