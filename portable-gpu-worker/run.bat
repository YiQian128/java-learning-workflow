@echo off

chcp 65001 >nul 2>&1

cd /d "%~dp0"

call "%~dp00_开始使用.bat" %*

