@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if errorlevel 1 (
    echo [Error] cd failed. Path: %~dp0
    pause
    exit /b 1
)
set "ROOT=%~dp0"

:: ----- Python path -----
set "PY_PORTABLE=%ROOT%_env\python\python.exe"
set "PY_VENV=%ROOT%_env\venv\Scripts\python.exe"
set "PY_FALLBACK="
if exist "%PY_PORTABLE%" set "PY_FALLBACK=%PY_PORTABLE%"
if "%PY_FALLBACK%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_FALLBACK=python"
)

:: ----- Add ffmpeg to PATH -----
if exist "%ROOT%_env\ffmpeg\bin\ffmpeg.exe" set "PATH=%ROOT%_env\ffmpeg\bin;%PATH%"

:menu
cls
echo(
echo   +======================================================+
echo   +         便携式 GPU 预处理包  -  主菜单               +
echo   +======================================================+

:: Show status
if exist "%PY_VENV%" (
    echo   +  环境状态: [OK] 已就绪                              +
) else if exist "%PY_PORTABLE%" (
    echo   +  环境状态: [~] 便携 Python 已有，venv 未配置         +
) else if not "%PY_FALLBACK%"=="" (
    echo   +  环境状态: [!] 使用系统 Python，需先完成环境准备     +
) else (
    echo   +  环境状态: [X] 未找到 Python                        +
)

echo   +======================================================+
echo   +                                                      +
echo   +   [1]  联网准备   首次使用 / 更新模型，下载资源       +
echo   +   [2]  离线准备   复制到新机后运行，重建 venv         +
echo   +   [3]  开始预处理 提取视频转写字幕并提取关键帧        +
echo   +   [4]  估算费用   扫描视频时长，各 API 转写费用对比   +
echo   +   [0]  退出                                          +
echo   +                                                      +
echo   +======================================================+
echo(

:: Default choice
if exist "%PY_VENV%" (
    set "DEFAULT=3"
    echo   环境已就绪，直接回车 = 开始预处理
) else (
    set "DEFAULT=1"
    echo   未检测到环境，直接回车 = 联网准备
)
echo(

set /p "CHOICE=  请输入选项 [0-4，回车=%DEFAULT%]: "
if "!CHOICE!"=="" set "CHOICE=%DEFAULT%"

if "!CHOICE!"=="1" goto :do_online
if "!CHOICE!"=="2" goto :do_offline
if "!CHOICE!"=="3" goto :do_preprocess
if "!CHOICE!"=="4" goto :do_estimate
if "!CHOICE!"=="0" goto :bye

echo(
echo   无效输入，请重新选择...
timeout /t 2 >nul
goto :menu


:: ----- [1] Online setup -----
:do_online
cls
echo(
echo   [联网准备] 下载/更新 Python、FFmpeg、Whisper 模型及依赖...
echo   ------------------------------------------------------
echo   如需使用 HuggingFace 私有模型，请先设置环境变量:
echo     set HF_TOKEN=hf_xxx
echo(

if "%PY_FALLBACK%"=="" (
    echo   [错误] 未找到 Python。
    echo   请先安装 Python 3.12: https://www.python.org/downloads/
    echo   或将已准备好的 portable-gpu-worker 文件夹直接复制过来。
    echo(
    pause
    goto :menu
)

if not exist "%ROOT%setup\setup_env.py" (
    echo   [错误] setup_env.py 不存在，目录结构可能不完整。
    pause
    goto :menu
)

"%PY_FALLBACK%" "%ROOT%setup\setup_env.py" --online
echo(
echo   联网准备完成，按任意键返回主菜单...
pause >nul
goto :menu


:: ----- [2] Offline setup -----
:do_offline
cls
echo(
echo   [离线准备] 验证 _env 资源、配置/重建 venv 及预处理环境...
echo   ------------------------------------------------------
echo(

if "%PY_FALLBACK%"=="" (
    echo   [错误] 未找到 Python。
    echo   请先在联网环境运行选项 [1]，或从已准备好的电脑复制整个文件夹。
    echo(
    pause
    goto :menu
)

if not exist "%ROOT%setup\setup_env.py" (
    echo   [错误] setup_env.py 不存在，目录结构可能不完整。
    pause
    goto :menu
)

"%PY_FALLBACK%" "%ROOT%setup\setup_env.py" --offline
echo(
echo   离线准备完成，按任意键返回主菜单...
pause >nul
goto :menu


:: ----- [3] Start preprocessing -----
:do_preprocess
cls
echo(
echo   [开始预处理] 扫描 videos/ 目录，提取视频、转写字幕、提取关键帧...
echo   ------------------------------------------------------

:: Admin check for GPU
net session >nul 2>&1
if errorlevel 1 (
    echo   [提示] 以管理员身份运行可获得 GPU 加速。
    echo(
)

:: Auto run offline setup if venv not exists
if not exist "%PY_VENV%" (
    echo   [提示] 虚拟环境未配置，将自动执行离线准备...
    echo(
    if exist "%PY_PORTABLE%" (
        "%PY_PORTABLE%" "%ROOT%setup\setup_env.py" --offline
        echo(
    ) else if not "%PY_FALLBACK%"=="" (
        "%PY_FALLBACK%" "%ROOT%setup\setup_env.py" --offline
        echo(
    ) else (
        echo   [错误] 未找到 Python，请先运行 [1] 联网准备。
        pause
        goto :menu
    )
)

if not exist "%PY_VENV%" (
    echo   [错误] 环境配置失败，请运行 [1] 联网准备 或 [2] 离线准备。
    echo(
    pause
    goto :menu
)

"%PY_VENV%" "%ROOT%run_preprocess.py"
echo(
echo   预处理结束，按任意键返回主菜单...
pause >nul
goto :menu


:: ----- [4] Estimate cost -----
:do_estimate
cls
echo(
echo   [估算费用] 扫描视频时长，输出各 API 转写费用对比...
echo   ------------------------------------------------------
echo(
echo   参数说明（可选）:
echo     直接回车     仅估算待处理视频（推荐）
echo     --all        包含已处理视频一并统计
echo     --no-scan    跳过时长扫描，快速查看价格
echo     --dir day01  仅估算 day01 子目录
echo(

if not exist "%PY_VENV%" (
    echo   [错误] 环境未就绪，请先运行 [1] 联网准备 或 [2] 离线准备。
    pause
    goto :menu
)

set "EARGS="
set /p "EARGS=  请输入参数，直接回车使用默认: "
echo(
if "!EARGS!"=="" (
    "%PY_VENV%" "%ROOT%scripts\estimate_cost.py"
) else (
    "%PY_VENV%" "%ROOT%scripts\estimate_cost.py" !EARGS!
)
echo(
echo   估算完成，按任意键返回主菜单...
pause >nul
goto :menu


:bye
echo(
echo   再见
pause
exit /b 0
