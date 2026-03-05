#!/usr/bin/env python3
"""
prepare_env.py - 便携包环境资源下载（在联网环境运行）
下载到 _env/ 下所有离线所需资源，确保复制到新机器后拆开即用。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "_env"
WHEELS_DIR = ENV_DIR / "wheels"
MODELS_DIR = ENV_DIR / "models"
FFMPEG_DIR = ENV_DIR / "ffmpeg"
PYTHON_DIR = ENV_DIR / "python"

PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip"
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl-shared.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GET_PIP_FALLBACK_URL = "https://raw.githubusercontent.com/pypa/get-pip/main/public/get-pip.py"


def _ensure_utf8():
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _env_has(name: str) -> bool:
    if name == "python":
        return (PYTHON_DIR / "python.exe").exists()
    if name == "ffmpeg":
        return (FFMPEG_DIR / "bin" / "ffmpeg.exe").exists() or (ENV_DIR / "ffmpeg.zip").exists()
    if name == "wheels":
        return WHEELS_DIR.exists() and bool(list(WHEELS_DIR.glob("*.whl")))
    if name == "model":
        if not MODELS_DIR.exists():
            return False
        for p in MODELS_DIR.rglob("*.incomplete"):
            return False
        for p in MODELS_DIR.iterdir():
            if p.is_dir() and ("Systran" in p.name or "systran" in p.name.lower()):
                return True
            if p.is_dir() and (p / "config.json").exists():
                return True
            if p.suffix == ".bin":
                return True
        return False
    return False


def download_file(url: str, dest: Path, desc: str, skip_if_exists: bool = True) -> bool:
    if skip_if_exists and dest.exists():
        print(f"  已存在，跳过: {dest.name}")
        return True
    print(f"  下载 {desc}...")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        def _progress(block_num, block_size, total):
            if total > 0:
                pct = min(100, block_num * block_size * 100 // total)
                print(f"\r    {pct}%", end="", flush=True)
        urlretrieve(url, dest, _progress)
        print()
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        return False


def main():
    _ensure_utf8()
    print("便携式 GPU 预处理包 - 环境资源准备")
    print("（在联网环境运行，完成后可复制到离线/GPU 机器使用）")
    print("=" * 50)

    ENV_DIR.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Windows":
        print("\n[1/5] Python 嵌入式包")
        if _env_has("python"):
            print("  已存在，跳过")
        else:
            dest = ENV_DIR / "python-embed.zip"
            if download_file(PYTHON_EMBED_URL, dest, "Python 3.12 embed"):
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    with zipfile.ZipFile(dest, "r") as z:
                        z.extractall(tmp)
                    subdirs = [d for d in Path(tmp).iterdir() if d.is_dir()]
                    src = subdirs[0] if subdirs else Path(tmp)
                    PYTHON_DIR.mkdir(parents=True, exist_ok=True)
                    for item in src.iterdir():
                        shutil.move(str(item), str(PYTHON_DIR / item.name))
                for pth in PYTHON_DIR.glob("*.pth"):
                    content = pth.read_text(encoding="utf-8")
                    if "#import site" in content:
                        pth.write_text(content.replace("#import site", "import site"), encoding="utf-8")
                print("  Python 已解压到 _env/python/")
    else:
        print("\n[1/5] Python 嵌入式包 - 跳过（仅 Windows）")

    print("\n[2/5] get-pip.py")
    get_pip = ENV_DIR / "get-pip.py"
    if get_pip.exists():
        print("  已存在，跳过")
    else:
        if not download_file(GET_PIP_URL, get_pip, "get-pip.py"):
            print("  主源失败，尝试备用源...")
            download_file(GET_PIP_FALLBACK_URL, get_pip, "get-pip.py (GitHub)")

    if platform.system() == "Windows":
        print("\n[3/5] FFmpeg")
        if (FFMPEG_DIR / "bin" / "ffmpeg.exe").exists():
            print("  已解压，跳过")
        else:
            dest = ENV_DIR / "ffmpeg.zip"
            if download_file(FFMPEG_URL, dest, "FFmpeg"):
                FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest, "r") as z:
                    z.extractall(FFMPEG_DIR)
                for sub in FFMPEG_DIR.iterdir():
                    if sub.is_dir() and (sub / "bin" / "ffmpeg.exe").exists():
                        for item in sub.iterdir():
                            shutil.move(str(item), str(FFMPEG_DIR / item.name))
                        sub.rmdir()
                        break
                print("  FFmpeg 已解压到 _env/ffmpeg/")
    else:
        print("\n[3/5] FFmpeg - 跳过（仅 Windows）")

    print("\n[4/5] pip wheels（离线安装包）")
    req_file = ROOT / "requirements.txt"
    has_wheels = False
    if _env_has("wheels"):
        wheels = list(WHEELS_DIR.glob("*.whl"))
        any_cp314 = any("cp314" in w.name for w in wheels)
        if any_cp314:
            print("  警告: 现有 wheels 为 cp314，将重新下载")
            for f in wheels:
                f.unlink()
        else:
            has_virtualenv = any("virtualenv" in w.name.lower() for w in wheels)
            # 检查 openai 是否在 wheels 中（API 转写必需，wheel 名可能含 - 或 _）
            def _has_pkg(pkg: str) -> bool:
                for w in wheels:
                    n = w.name.lower()
                    if n.startswith(pkg.replace("-", "_") + "-") or n.startswith(pkg.replace("_", "-") + "-"):
                        return True
                return False
            missing_openai = not _has_pkg("openai")
            if not has_virtualenv:
                print("  警告: wheels 缺少 virtualenv，将重新下载")
                for f in wheels:
                    f.unlink()
            elif missing_openai:
                print("  补充下载 openai...")
                WHEELS_DIR.mkdir(parents=True, exist_ok=True)
                pip_python = str(PYTHON_DIR / "python.exe") if (PYTHON_DIR / "python.exe").exists() else sys.executable
                ret = subprocess.run(
                    [pip_python, "-m", "pip", "download", "openai>=1.0.0", "-d", str(WHEELS_DIR)],
                    capture_output=True, text=True, cwd=ROOT,
                )
                if ret.returncode != 0:
                    ret = subprocess.run(
                        [sys.executable, "-m", "pip", "download", "openai>=1.0.0", "-d", str(WHEELS_DIR)],
                        capture_output=True, text=True, cwd=ROOT,
                    )
                if ret.returncode == 0:
                    print("  openai 已下载")
                    has_wheels = True
                else:
                    print("  下载失败:", ret.stderr or ret.stdout)
                    for f in wheels:
                        f.unlink()
            else:
                has_wheels = True
                print("  已存在，跳过")

    # 确保 wheels 包含 pip（bootstrap 使用 --no-seed 时 get-pip 需离线可用的 pip 包）
    if _env_has("wheels") and req_file.exists():
        wheels = list(WHEELS_DIR.glob("*.whl"))
        has_pip = any("pip-" in w.name.lower() or w.name.lower().startswith("pip-") for w in wheels)
        if not has_pip:
            print("  补充下载 pip...")
            pip_py = str(PYTHON_DIR / "python.exe") if (PYTHON_DIR / "python.exe").exists() else sys.executable
            subprocess.run([pip_py, "-m", "pip", "download", "pip", "-d", str(WHEELS_DIR)],
                          capture_output=True, text=True, cwd=ROOT)
            subprocess.run([sys.executable, "-m", "pip", "download", "pip", "-d", str(WHEELS_DIR)],
                          capture_output=True, text=True, cwd=ROOT)

    if not has_wheels and req_file.exists():
        print("  正在下载 wheels...")
        WHEELS_DIR.mkdir(parents=True, exist_ok=True)
        pip_python = str(PYTHON_DIR / "python.exe") if (PYTHON_DIR / "python.exe").exists() else sys.executable
        if pip_python == str(PYTHON_DIR / "python.exe") and (ENV_DIR / "get-pip.py").exists():
            subprocess.run([pip_python, str(ENV_DIR / "get-pip.py"), "-q"], capture_output=True, cwd=ROOT)
        ret = subprocess.run(
            [pip_python, "-m", "pip", "download", "-r", str(req_file), "-d", str(WHEELS_DIR)],
            capture_output=True, text=True, cwd=ROOT,
        )
        if ret.returncode != 0:
            ret2 = subprocess.run(
                [sys.executable, "-m", "pip", "download", "-r", str(req_file), "-d", str(WHEELS_DIR),
                 "--python-version", "312", "--platform", "win_amd64", "--only-binary", ":all:"],
                capture_output=True, text=True, cwd=ROOT,
            )
            if ret2.returncode != 0:
                subprocess.run(
                    [sys.executable, "-m", "pip", "download", "-r", str(req_file), "-d", str(WHEELS_DIR)],
                    capture_output=True, text=True, cwd=ROOT,
                )
        print("  wheels 已下载到 _env/wheels/")
    elif not has_wheels:
        print(f"  未找到 requirements.txt（路径: {req_file}）")

    print("\n[5/5] Whisper 模型")
    if _env_has("model"):
        print("  模型已缓存，跳过")
    else:
        print("  将在环境补齐后由 download_model.py 下载")

    print("\n" + "=" * 50)
    print("环境准备完成。可将 portable-gpu-worker 复制到目标机器，运行 0_开始使用.bat → [2] 离线准备")


if __name__ == "__main__":
    main()
