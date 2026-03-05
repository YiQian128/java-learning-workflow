#!/usr/bin/env python3
"""
verify_offline.py - 校验便携包是否具备离线运行条件
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "_env"


def check(name: str, ok: bool, msg: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" - {msg}" if msg else ""))
    return ok


def main() -> int:
    print("便携式 GPU 预处理包 - 离线就绪校验")
    print("=" * 50)

    all_ok = True
    python_exe = ENV / "python" / "python.exe"
    all_ok &= check("Python 便携版", python_exe.exists(), "" if python_exe.exists() else "缺失")
    if python_exe.exists():
        try:
            r = __import__("subprocess").run(
                [str(python_exe), "--version"],
                capture_output=True, text=True, timeout=5,
            )
            ver = r.stdout.strip() or r.stderr.strip()
            all_ok &= check("  Python 版本", "3.12" in ver, ver)
        except Exception as e:
            all_ok &= check("  Python 可执行", False, str(e))

    all_ok &= check("get-pip.py", (ENV / "get-pip.py").exists())
    all_ok &= check("FFmpeg", (ENV / "ffmpeg" / "bin" / "ffmpeg.exe").exists())
    all_ok &= check("FFprobe", (ENV / "ffmpeg" / "bin" / "ffprobe.exe").exists())

    wheels = list((ENV / "wheels").glob("*.whl")) if (ENV / "wheels").exists() else []
    has_wheels = len(wheels) > 0
    all_ok &= check("pip wheels", has_wheels, f"{len(wheels)} 个" if has_wheels else "缺失")
    if has_wheels:
        cp314 = any("cp314" in w.name for w in wheels)
        if cp314:
            all_ok &= check("  wheel 兼容性", False, "需重新运行 0_开始使用.bat → [1] 联网准备")
        else:
            check("  wheel 兼容性", True, "cp312 或通用")

    has_model = False
    if (ENV / "models").exists():
        for p in (ENV / "models").iterdir():
            if p.is_dir() and "Systran" in p.name:
                has_model = True
                break
    all_ok &= check("Whisper 模型", has_model)

    for r in ["faster_whisper", "pyyaml", "rich"]:
        found = any(r.replace("_", "-") in w.name.lower() or r in w.name.lower() for w in wheels)
        if has_wheels:
            all_ok &= check(f"  依赖 {r}", found)

    for s in ["extract_audio.py", "transcribe.py", "transcribe_api.py", "extract_keyframes.py", "split_video.py"]:
        all_ok &= check(f"脚本 {s}", (ROOT / "scripts" / s).exists())

    print("=" * 50)
    if all_ok:
        print("校验通过。可复制到目标机器，运行 0_开始使用.bat → [2] 离线准备 后离线使用。")
        return 0
    else:
        print("校验未通过。请运行 0_开始使用.bat → [1] 联网准备 补齐缺失资源。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
