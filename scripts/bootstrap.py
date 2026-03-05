#!/usr/bin/env python3
"""
Java Learning Workflow - 环境自检与自动配置
首次运行时自动检测环境、安装依赖、配置 MCP Server、安装 Skill。
支持 Windows / macOS / Linux。
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

# ── 颜色输出 ────────────────────────────────────────────────────────────────
_IS_WIN = platform.system() == "Windows"

def _supports_ansi() -> bool:
    if not _IS_WIN:
        return True
    return bool(
        os.environ.get("WT_SESSION")
        or os.environ.get("ANSICON")
        or "VSCODE" in os.environ.get("TERM_PROGRAM", "")
        or os.environ.get("ConEmuPID")
    )

_ANSI = _supports_ansi()

def _c(text: str, code: str) -> str:
    if not _ANSI:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t): return _c(t, "32")
def red(t): return _c(t, "31")
def yellow(t): return _c(t, "33")
def cyan(t): return _c(t, "36")
def bold(t): return _c(t, "1")

# ── 项目路径 ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_ROOT = PROJECT_ROOT / "portable-gpu-worker"
VENV_DIR = PROJECT_ROOT / ".venv"


def _get_workspace_dirs() -> tuple[Path, Path]:
    """项目固定使用 portable-gpu-worker 的 videos/output"""
    return PORTABLE_ROOT / "videos", PORTABLE_ROOT / "output"


VIDEOS_DIR, OUTPUT_DIR = _get_workspace_dirs()
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"
MCP_CONFIG = PROJECT_ROOT / ".mcp.json"
CURSOR_MCP_CONFIG = PROJECT_ROOT / ".cursor" / "mcp.json"
VSCODE_MCP_CONFIG = PROJECT_ROOT / ".vscode" / "mcp.json"
REQUIREMENTS = PROJECT_ROOT / "mcp-server" / "requirements.txt"


def _ensure_utf8_console():
    """Windows 控制台 UTF-8 兼容，避免 Unicode 字符编码错误"""
    if _IS_WIN and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def banner():
    _ensure_utf8_console()
    print()
    print(bold("=" * 60))
    print(bold("  Java 学习工作流 - 环境自检与自动配置"))
    print(bold("=" * 60))
    print(f"  项目目录: {PROJECT_ROOT}")
    print(f"  操作系统: {platform.system()} {platform.release()}")
    print(f"  Python:   {sys.version.split()[0]}")
    print(bold("=" * 60))
    print()


# ── Step 1: 环境检测 ────────────────────────────────────────────────────────

def check_python() -> bool:
    ver = sys.version_info
    ok = ver >= (3, 10)
    status = green("✓") if ok else red("✗")
    print(f"  {status} Python {ver.major}.{ver.minor}.{ver.micro}" +
          ("" if ok else red(" (需要 3.10+)")))
    return ok


def check_command(cmd: str, version_flag: str = "--version", name: str = "") -> Tuple[bool, str]:
    name = name or cmd
    try:
        result = subprocess.run(
            [cmd, version_flag],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        output = (result.stdout + result.stderr).strip().split("\n")[0]
        print(f"  {green('✓')} {name}: {output}")
        return True, output
    except FileNotFoundError:
        print(f"  {red('✗')} {name}: {red('未找到')}")
        return False, ""
    except Exception as e:
        print(f"  {red('✗')} {name}: {red(str(e))}")
        return False, ""


def check_ffmpeg() -> bool:
    ok, _ = check_command("ffmpeg", "-version", "FFmpeg")
    if not ok:
        print(yellow("    提示: 请安装 FFmpeg"))
        if _IS_WIN:
            print("    Windows: 从 https://ffmpeg.org/download.html 下载并加入 PATH")
            print("    或使用: winget install Gyan.FFmpeg")
        elif platform.system() == "Darwin":
            print("    macOS: brew install ffmpeg")
        else:
            print("    Linux: sudo apt install ffmpeg  (或对应的包管理器)")
    return ok


def check_node() -> bool:
    ok, _ = check_command("node", "--version", "Node.js")
    if not ok:
        print(yellow("    提示: Node.js 不是必需的，但某些功能可能需要"))
    return ok


def detect_gpu() -> str:
    """检测可用的 GPU 加速类型"""
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10
        )
        if result.returncode == 0:
            print(f"  {green('✓')} NVIDIA GPU 已检测到 (CUDA 可用)")
            return "cuda"
    except FileNotFoundError:
        pass

    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )
            if "Apple" in result.stdout or re.search(r'\bM\d+\b', result.stdout):
                print(f"  {green('✓')} Apple Silicon 已检测到")
                return "auto"
        except FileNotFoundError:
            pass

    print(f"  {yellow('○')} 未检测到 GPU, 将使用 CPU 模式 (速度较慢)")
    return "cpu"


def run_environment_check() -> dict:
    print(bold("▸ Step 1: 环境检测"))
    print()
    results = {
        "python_ok": check_python(),
        "ffmpeg_ok": check_ffmpeg(),
        "node_ok": check_node(),
        "gpu": detect_gpu(),
    }
    print()
    return results


# ── Step 2: 虚拟环境与依赖 ──────────────────────────────────────────────────

def setup_venv() -> bool:
    print(bold("▸ Step 2: Python 虚拟环境与依赖安装"))
    print()

    if VENV_DIR.exists():
        print(f"  {green('✓')} 虚拟环境已存在: {VENV_DIR}")
    else:
        print(f"  {cyan('○')} 创建虚拟环境: {VENV_DIR}")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(VENV_DIR)],
                check=True, capture_output=True
            )
            print(f"  {green('✓')} 虚拟环境创建成功")
        except subprocess.CalledProcessError as e:
            print(f"  {red('✗')} 虚拟环境创建失败: {e}")
            return False

    pip_exe = _get_venv_pip()
    if not pip_exe:
        print(f"  {red('✗')} 找不到 pip")
        return False

    print(f"  {cyan('○')} 升级 pip...")
    subprocess.run([str(pip_exe), "install", "--upgrade", "pip"],
                   capture_output=True, timeout=120)

    print(f"  {cyan('○')} 安装依赖: {REQUIREMENTS}")
    result = subprocess.run(
        [str(pip_exe), "install", "-r", str(REQUIREMENTS)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600
    )
    if result.returncode == 0:
        print(f"  {green('✓')} 依赖安装成功")
    else:
        print(f"  {red('✗')} 依赖安装失败:")
        for line in result.stderr.strip().split("\n")[-5:]:
            print(f"    {line}")
        return False

    print()
    return True


def _get_venv_python() -> Path | None:
    if _IS_WIN:
        p = VENV_DIR / "Scripts" / "python.exe"
    else:
        p = VENV_DIR / "bin" / "python"
    return p if p.exists() else None


def _get_venv_pip() -> Path | None:
    if _IS_WIN:
        p = VENV_DIR / "Scripts" / "pip.exe"
    else:
        p = VENV_DIR / "bin" / "pip"
    return p if p.exists() else None


# ── Step 3: MCP Server 配置 ─────────────────────────────────────────────────

def setup_mcp() -> bool:
    print(bold("▸ Step 3: MCP Server 配置"))
    print()

    venv_python = _get_venv_python()
    if not venv_python:
        venv_python = Path(sys.executable)

    mcp_server_config = {
        "command": str(venv_python),
        "args": [
            str(PROJECT_ROOT / "mcp-server" / "server.py")
        ],
        "env": {
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1"
        }
    }

    mcp_config = {
        "mcpServers": {
            "java-learning-workflow": mcp_server_config
        }
    }

    # Claude Code / Claude Desktop
    MCP_CONFIG.write_text(json.dumps(mcp_config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {green('✓')} MCP 配置已写入: {MCP_CONFIG}")

    # Cursor IDE 项目级 MCP 配置
    CURSOR_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_MCP_CONFIG.write_text(json.dumps(mcp_config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {green('✓')} Cursor MCP 配置已写入: {CURSOR_MCP_CONFIG}")

    # VS Code Copilot Agent (1.99+) 项目级 MCP 配置
    vscode_server_config = dict(mcp_server_config)
    vscode_server_config["type"] = "stdio"
    vscode_mcp_config = {
        "servers": {
            "java-learning-workflow": vscode_server_config
        }
    }
    VSCODE_MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    VSCODE_MCP_CONFIG.write_text(json.dumps(vscode_mcp_config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {green('✓')} VS Code MCP 配置已写入: {VSCODE_MCP_CONFIG}")

    # Claude Desktop config
    claude_config_paths = []
    if _IS_WIN:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            claude_config_paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    elif platform.system() == "Darwin":
        claude_config_paths.append(
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        )
    else:
        # Linux
        claude_config_paths.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")

    for config_path in claude_config_paths:
        if config_path.parent.exists():
            try:
                existing = {}
                if config_path.exists():
                    existing = json.loads(config_path.read_text(encoding="utf-8"))
                servers = existing.get("mcpServers", {})
                servers["java-learning-workflow"] = mcp_config["mcpServers"]["java-learning-workflow"]
                existing["mcpServers"] = servers
                config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  {green('✓')} Claude Desktop 配置已更新: {config_path}")
            except Exception as e:
                print(f"  {yellow('○')} 无法更新 Claude Desktop 配置: {e}")

    print()
    return True


# ── Step 4: 目录结构 ────────────────────────────────────────────────────────

def setup_directories() -> bool:
    print(bold("▸ Step 4: 目录结构初始化"))
    print()

    dirs = [VIDEOS_DIR, OUTPUT_DIR, PROJECT_ROOT / "config"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not any(d.iterdir()):
            gitkeep.touch()
        print(f"  {green('✓')} {d.relative_to(PROJECT_ROOT)}/")

    print()
    return True


# ── Step 5: 配置文件自适应 ──────────────────────────────────────────────────

def adapt_config(gpu: str) -> bool:
    print(bold("▸ Step 5: 配置文件自适应调整"))
    print()

    if not CONFIG_FILE.exists():
        print(f"  {yellow('○')} 配置文件不存在, 跳过")
        print()
        return True

    try:
        import yaml
    except ImportError:
        print(f"  {yellow('○')} PyYAML 不可用, 跳过配置自适应")
        print()
        return True

    try:
        config_text = CONFIG_FILE.read_text(encoding="utf-8")
        config = yaml.safe_load(config_text) or {}
        changes = []

        # GPU/CPU 适配（用字符串替换保留注释和格式）
        whisper = config.get("whisper", {})
        old_device = whisper.get("device", "auto")
        if old_device != gpu:
            config_text = re.sub(
                r'(device:\s*)"[^"]*"',
                f'\\1"{gpu}"',
                config_text
            )
            changes.append(f"Whisper 设备设置为: {gpu}")

        if gpu == "cpu" and whisper.get("model") in ("large-v3",):
            config_text = re.sub(
                r'(model:\s*)"large-v3"',
                '\\1"medium"',
                config_text
            )
            changes.append("Whisper 模型降级为 medium (CPU 模式)")

        # 路径适配——追加 paths 段（若不存在则添加）
        # 使用正斜杠路径避免 Windows 反斜杠在 re.sub 中的转义问题
        safe_root = str(PROJECT_ROOT).replace("\\", "/")
        safe_videos = str(VIDEOS_DIR).replace("\\", "/")
        safe_output = str(OUTPUT_DIR).replace("\\", "/")

        if "paths:" not in config_text:
            paths_block = (
                f"\n# ── 路径配置（自动生成）────────────────────────────────────────\n"
                f"paths:\n"
                f'  project_root: "{safe_root}"\n'
                f'  videos_dir: "{safe_videos}"\n'
                f'  output_dir: "{safe_output}"\n'
            )
            config_text += paths_block
            changes.append("路径配置已追加")
        else:
            config_text = re.sub(
                r'(project_root:\s*).*',
                f'\\1"{safe_root}"',
                config_text
            )
            config_text = re.sub(
                r'(videos_dir:\s*).*',
                f'\\1"{safe_videos}"',
                config_text
            )
            config_text = re.sub(
                r'(output_dir:\s*).*',
                f'\\1"{safe_output}"',
                config_text
            )
            changes.append("路径已更新为当前项目位置")

        CONFIG_FILE.write_text(config_text, encoding="utf-8")

        for change in changes:
            print(f"  {green('✓')} {change}")

    except Exception as e:
        print(f"  {yellow('○')} 配置自适应失败: {e}")

    print()
    return True


# ── Step 6: Skill 安装 ──────────────────────────────────────────────────────

def install_skill() -> bool:
    print(bold("▸ Step 6: Skill 安装"))
    print()

    skill_src = PROJECT_ROOT / "skills" / "java-learning" / "SKILL.md"
    if not skill_src.exists():
        print(f"  {yellow('○')} Skill 文件不存在, 跳过")
        print()
        return True

    # Claude Code / Cursor skills directory
    home = Path.home()
    skill_targets = [
        home / ".claude" / "skills" / "java-learning" / "SKILL.md",
        home / ".cursor" / "skills" / "java-learning" / "SKILL.md",
    ]

    for target in skill_targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_src, target)
            print(f"  {green('✓')} Skill 已安装到: {target}")
        except Exception as e:
            print(f"  {yellow('○')} 安装失败 ({target}): {e}")

    print()
    return True


# ── Step 7: 验证 ────────────────────────────────────────────────────────────

def verify_setup() -> bool:
    print(bold("▸ Step 7: 安装验证"))
    print()

    all_ok = True

    # 验证 venv
    venv_python = _get_venv_python()
    if venv_python and venv_python.exists():
        print(f"  {green('✓')} 虚拟环境 Python: {venv_python}")

        # 验证核心包
        packages = ["mcp", "faster_whisper", "genanki", "yaml", "rich"]
        for pkg in packages:
            result = subprocess.run(
                [str(venv_python), "-c", f"import {pkg}"],
                capture_output=True
            )
            if result.returncode == 0:
                print(f"  {green('✓')} {pkg}")
            else:
                print(f"  {red('✗')} {pkg} 导入失败")
                all_ok = False
    else:
        print(f"  {red('✗')} 虚拟环境未找到")
        all_ok = False

    # 验证 FFmpeg
    if shutil.which("ffmpeg"):
        print(f"  {green('✓')} FFmpeg 可用")
    else:
        print(f"  {yellow('△')} FFmpeg 不可用（视频处理需要）")

    # 验证 MCP 配置
    if MCP_CONFIG.exists():
        print(f"  {green('✓')} MCP 配置 (Claude): {MCP_CONFIG}")
    else:
        print(f"  {red('✗')} MCP 配置未创建")
        all_ok = False

    if CURSOR_MCP_CONFIG.exists():
        print(f"  {green('✓')} MCP 配置 (Cursor): {CURSOR_MCP_CONFIG}")
    else:
        print(f"  {yellow('△')} Cursor MCP 配置未创建（Cursor 用户需重启以加载）")

    if VSCODE_MCP_CONFIG.exists():
        print(f"  {green('✓')} MCP 配置 (VS Code): {VSCODE_MCP_CONFIG}")
    else:
        print(f"  {yellow('△')} VS Code MCP 配置未创建（重新运行 bootstrap.py 可生成）")

    # 验证目录
    for d in [VIDEOS_DIR, OUTPUT_DIR]:
        if d.exists():
            print(f"  {green('✓')} 目录: {d.relative_to(PROJECT_ROOT)}/")
        else:
            print(f"  {red('✗')} 目录不存在: {d.relative_to(PROJECT_ROOT)}/")
            all_ok = False

    print()
    return all_ok


# ── 总结 ────────────────────────────────────────────────────────────────────

def print_summary(success: bool):
    print(bold("=" * 60))
    if success:
        print(bold(green("  ✓ 环境配置完成！")))
    else:
        print(bold(yellow("  ⚠ 环境配置部分完成, 请检查上方警告")))
    print(bold("=" * 60))
    print()
    print("  后续操作:")
    print(f"  1. 将视频文件放入: {cyan(str(VIDEOS_DIR))}")
    print(f"  2. 运行处理流水线:")
    venv_py = _get_venv_python()
    py_cmd = str(venv_py) if venv_py else "python"
    print(f"     {cyan(py_cmd + ' scripts/pipeline.py scan')}")
    print(f"  3. 在 Claude Code / Cursor / VS Code 中使用:")
    print(f"     Claude Code: {cyan('/process-video <视频路径>')} 或 {cyan('/batch-process')}")
    print(f"     Cursor: 对话中直接要求处理视频（需完全重启 Cursor 以加载 MCP）")
    print(f"     VS Code: Copilot Chat → Agent 模式，工具栏可调用所有 MCP 工具（需 VS Code ≥ 1.99）")
    print()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    banner()

    env = run_environment_check()

    if not env["python_ok"]:
        print(red("Python 版本不满足要求 (需要 3.10+), 请升级后重试"))
        sys.exit(1)

    if not env["ffmpeg_ok"]:
        print(yellow("⚠ FFmpeg 未安装, 视频处理功能将不可用"))
        if sys.stdin.isatty():
            resp = input("是否继续? [y/N] ").strip().lower()
            if resp != "y":
                sys.exit(1)
        else:
            print(yellow("  (非交互模式, 自动继续)"))

    venv_ok = setup_venv()
    mcp_ok = setup_mcp()
    dir_ok = setup_directories()
    config_ok = adapt_config(env["gpu"])
    install_skill()  # Skill 安装为可选，不影响 success 判定
    verify_ok = verify_setup()

    success = all([venv_ok, mcp_ok, dir_ok, config_ok, verify_ok])
    print_summary(success)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
