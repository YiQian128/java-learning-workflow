#!/usr/bin/env python3
"""
write_run_bat.py - 生成 portable-gpu-worker/run.bat

run.bat 是简化入口：设置 chcp 65001（UTF-8）后调用主 BAT 文件。
主要用于双击启动或从其他脚本调用时确保编码正确。
"""
from pathlib import Path

CONTENT = "@echo off\r\nchcp 65001 >nul 2>&1\r\ncd /d \"%~dp0\"\r\ncall \"%~dp00_\u5f00\u59cb\u4f7f\u7528.bat\" %*\r\n"

bat_path = Path(__file__).resolve().parent.parent / "run.bat"
bat_path.write_text(CONTENT, encoding="utf-8")
print(f"Written: {bat_path}")
