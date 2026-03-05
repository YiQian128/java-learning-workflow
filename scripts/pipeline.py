#!/usr/bin/env python3
"""
Java Learning Workflow - 主流水线入口
用法：
  python pipeline.py setup                     # 首次运行: 环境检测与配置
  python pipeline.py scan                      # 扫描 portable-gpu-worker/videos/
  python pipeline.py status                    # 查看处理状态

预处理（音频、字幕、关键帧）请使用 portable-gpu-worker 的 0_开始使用.bat → 选项 [3]
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import textwrap
from pathlib import Path

_IS_WIN = platform.system() == "Windows"


def _ensure_utf8_console():
    """Windows 控制台 UTF-8 兼容，避免 Unicode 字符编码错误"""
    if _IS_WIN and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None

# ── 项目路径 ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_ROOT = PROJECT_ROOT / "portable-gpu-worker"


def _detect_workspace() -> tuple[Path, Path]:
    """项目固定使用 portable-gpu-worker 的 videos/output"""
    return PORTABLE_ROOT / "videos", PORTABLE_ROOT / "output"


VIDEOS_DIR, OUTPUT_DIR = _detect_workspace()
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts"]


def _load_long_video_config() -> tuple[int, int]:
    """从 config.yaml 读取长视频阈值；读取失败时退回默认值"""
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        lv = cfg.get("long_video", {})
        threshold = int(lv.get("max_segment_duration", 5400))
        target = int(lv.get("target_segment_duration", 2700))
        return threshold, target
    except Exception:
        return 5400, 2700


# 长视频阈值(秒): 超过此时长自动分段（从 config.yaml 读取）
LONG_VIDEO_THRESHOLD, SEGMENT_TARGET_DURATION = _load_long_video_config()


def print_info(msg: str, style: str = ""):
    if RICH:
        console.print(msg, style=style)
    else:
        clean = re.sub(r'\[/?[^\]]*\]', '', msg)
        print(clean)


def banner():
    _ensure_utf8_console()
    if RICH:
        console.print(Panel.fit(
            "[bold blue]Java 学习工作流 - 视频处理流水线[/bold blue]\n"
            "[dim]将教学视频转化为：知识文档（视频级） + 章节学习包（章节级）[/dim]\n"
            f"[dim]视频目录: {VIDEOS_DIR}[/dim]\n"
            f"[dim]输出目录: {OUTPUT_DIR}[/dim]",
            border_style="blue"
        ))
    else:
        print("=" * 60)
        print("Java 学习工作流 - 视频处理流水线")
        print(f"视频目录: {VIDEOS_DIR}")
        print(f"输出目录: {OUTPUT_DIR}")
        print("=" * 60)


# ── 工具函数 ────────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_video_duration(video_path: str) -> float:
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_format", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def scan_videos(directory: Path = None) -> list[dict]:
    """扫描目录中所有视频文件"""
    directory = directory or VIDEOS_DIR
    if not directory.exists():
        return []

    videos = []
    for f in sorted(directory.rglob("*")):
        if f.suffix.lower() in VIDEO_EXTENSIONS and not f.name.startswith("."):
            stat = f.stat()
            duration = get_video_duration(str(f))
            videos.append({
                "path": str(f),
                "name": f.name,
                "stem": f.stem,
                "relative": str(f.relative_to(directory)),
                "size_bytes": stat.st_size,
                "size": format_size(stat.st_size),
                "duration": duration,
                "duration_fmt": format_duration(duration),
                "is_long": duration > LONG_VIDEO_THRESHOLD,
                "output_dir": str(OUTPUT_DIR / _safe_dirname(f.stem)),
            })
    return videos


def _safe_dirname(name: str) -> str:
    """从视频文件名生成安全的目录名"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name.strip('. ')


def get_output_paths(video_stem: str, video_path: str = None) -> dict:
    """获取视频对应的输出路径结构。

    优先策略（与 server.py 保持一致）：
    1. 若 video_path 在 VIDEOS_DIR 内，保留相对层级映射到 OUTPUT_DIR
    2. 扫描 OUTPUT_DIR 找已存在的匹配目录（向后兼容）
    3. 退回 OUTPUT_DIR/{safe_stem}/ 平级结构
    """
    safe_stem = _safe_dirname(video_stem)

    # 策略 1：根据 video_path 推断层级
    if video_path:
        vp = Path(video_path).resolve()
        vd = VIDEOS_DIR.resolve()
        try:
            rel = vp.relative_to(vd)
            base = OUTPUT_DIR / rel.parent / safe_stem
            prep = base / "_preprocessing"
            return {
                "base": base,
                "preprocessing": prep,
                "frames": prep / "frames",
                "audio": prep / f"{safe_stem}_audio.wav",
                "srt": prep / f"{safe_stem}.srt",
                "words_json": prep / f"{safe_stem}_words.json",
                "knowledge": base / f"knowledge_{safe_stem}.md",
            }
        except ValueError:
            pass

    # 策略 2：扫描已存在目录
    if OUTPUT_DIR.exists():
        for candidate in OUTPUT_DIR.rglob(safe_stem):
            if candidate.is_dir():
                base = candidate
                prep = base / "_preprocessing"
                return {
                    "base": base,
                    "preprocessing": prep,
                    "frames": prep / "frames",
                    "audio": prep / f"{safe_stem}_audio.wav",
                    "srt": prep / f"{safe_stem}.srt",
                    "words_json": prep / f"{safe_stem}_words.json",
                    "knowledge": base / f"knowledge_{safe_stem}.md",
                }

    # 策略 3：平级退回
    base = OUTPUT_DIR / safe_stem
    prep = base / "_preprocessing"
    return {
        "base": base,
        "preprocessing": prep,
        "frames": prep / "frames",
        "audio": prep / f"{safe_stem}_audio.wav",
        "srt": prep / f"{safe_stem}.srt",
        "words_json": prep / f"{safe_stem}_words.json",
        "knowledge": base / f"knowledge_{safe_stem}.md",
    }


def check_preprocessing_status(video_stem: str, video_path: str = None) -> dict:
    """检查预处理产物是否存在（支持长视频分段产物）"""
    paths = get_output_paths(video_stem, video_path)
    frames = list(paths["frames"].glob("*.jpg")) if paths["frames"].exists() else []
    # 长视频分段时，关键帧在 frames/{segment_stem}/ 子目录下
    if not frames and paths["frames"].exists():
        for sub in paths["frames"].iterdir():
            if sub.is_dir():
                frames.extend(sub.glob("*.jpg"))

    has_srt = paths["srt"].exists()
    has_audio = paths["audio"].exists()

    # 长视频分段：检查 _split_info.json 和各分段产物
    split_info_path = paths["preprocessing"] / "segments" / "_split_info.json"
    if split_info_path.exists() and not has_srt:
        safe_stem = _safe_dirname(video_stem)
        for part_srt in paths["preprocessing"].glob(f"{safe_stem}_part*.srt"):
            has_srt = True
            break
        for part_wav in paths["preprocessing"].glob(f"{safe_stem}_part*_audio.wav"):
            has_audio = True
            break

    return {
        "has_audio": has_audio,
        "has_srt": has_srt,
        "has_frames": len(frames) > 0,
        "has_knowledge": paths["knowledge"].exists(),
        "frame_count": len(frames),
        "is_segmented": split_info_path.exists(),
    }


# ── Setup 命令 ──────────────────────────────────────────────────────────────

def cmd_setup(args):
    """运行环境检测与自动配置"""
    bootstrap = Path(__file__).parent / "bootstrap.py"
    if not bootstrap.exists():
        print_info("[red]bootstrap.py 不存在[/red]")
        sys.exit(1)
    result = subprocess.run([sys.executable, str(bootstrap)])
    sys.exit(result.returncode)


# ── Scan 命令 ───────────────────────────────────────────────────────────────

def cmd_scan(args):
    """扫描 portable-gpu-worker/videos/ 目录中的视频文件"""
    banner()
    print_info("\n[bold]扫描视频目录...[/bold]\n")

    videos = scan_videos()
    if not videos:
        print_info(f"[yellow]视频目录中未找到视频文件[/yellow]")
        print_info(f"请将视频文件放入: [cyan]{VIDEOS_DIR}[/cyan]")
        return

    if RICH:
        table = Table(title=f"找到 {len(videos)} 个视频文件", show_header=True,
                      header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("文件名", style="cyan", max_width=50)
        table.add_column("时长", justify="right")
        table.add_column("大小", justify="right")
        table.add_column("状态")
        table.add_column("备注")

        for i, v in enumerate(videos, 1):
            status = check_preprocessing_status(v["stem"], v["path"])
            if status["has_knowledge"]:
                st = "[green]✓ 已完成[/green]"
            elif status["has_srt"]:
                st = "[yellow]◐ 已预处理[/yellow]"
            else:
                st = "[dim]○ 待处理[/dim]"

            note = ""
            if v["is_long"]:
                note = "[red]⚠ 长视频(需分段)[/red]"

            table.add_row(str(i), v["name"], v["duration_fmt"], v["size"], st, note)
        console.print(table)
    else:
        for i, v in enumerate(videos, 1):
            status = check_preprocessing_status(v["stem"], v["path"])
            st = "✓" if status["has_knowledge"] else ("◐" if status["has_srt"] else "○")
            long_mark = " ⚠长" if v["is_long"] else ""
            print(f"  {i:3d}. [{st}] {v['name']}  {v['duration_fmt']}  {v['size']}{long_mark}")

    total_duration = sum(v["duration"] for v in videos)
    long_count = sum(1 for v in videos if v["is_long"])
    print_info(f"\n总时长: [bold]{format_duration(total_duration)}[/bold]")
    if long_count:
        print_info(f"[yellow]其中 {long_count} 个视频超过 {LONG_VIDEO_THRESHOLD//60} 分钟, 将自动分段处理[/yellow]")


# ── Status 命令 ─────────────────────────────────────────────────────────────

def cmd_status(args):
    """查看所有视频的处理状态"""
    banner()
    videos = scan_videos()

    if not videos:
        print_info("[yellow]未找到视频文件[/yellow]")
        return

    statuses = {v["stem"]: check_preprocessing_status(v["stem"], v["path"]) for v in videos}

    if RICH:
        table = Table(title="处理状态总览", show_header=True, header_style="bold magenta")
        table.add_column("文件名", style="cyan", max_width=40)
        table.add_column("时长", justify="right")
        table.add_column("字幕", justify="center")
        table.add_column("关键帧", justify="center")
        table.add_column("知识文档", justify="center")

        for v in videos:
            s = statuses[v["stem"]]
            table.add_row(
                v["name"],
                v["duration_fmt"],
                "[green]✓[/green]" if s["has_srt"] else "[red]✗[/red]",
                f"[green]✓ ({s['frame_count']})[/green]" if s["has_frames"] else "[red]✗[/red]",
                "[green]✓[/green]" if s["has_knowledge"] else "[red]✗[/red]",
            )
        console.print(table)
    else:
        for v in videos:
            s = statuses[v["stem"]]
            srt = "✓" if s["has_srt"] else "✗"
            frm = "✓" if s["has_frames"] else "✗"
            doc = "✓" if s["has_knowledge"] else "✗"
            print(f"  {srt} {frm} {doc} | {v['name']}")

    total = len(videos)
    done = sum(1 for s in statuses.values() if s["has_knowledge"])
    prep = sum(1 for s in statuses.values() if s["has_srt"])
    print_info(f"\n总计: {total} 个视频 | 已完成: {done} | 已预处理: {prep} | 待处理: {total - prep}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Java 学习工作流 - 视频处理流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
示例：
  python pipeline.py setup                              # 首次运行环境配置
  python pipeline.py scan                               # 扫描视频目录
  python pipeline.py status                             # 查看处理状态

预处理请使用 portable-gpu-worker 的 0_开始使用.bat → 选项 [3]
        """)
    )
    parser.add_argument("--config", default=str(CONFIG_PATH), help="配置文件路径")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    sub_setup = subparsers.add_parser("setup", help="环境检测与自动配置")
    sub_setup.set_defaults(func=cmd_setup)

    # scan
    sub_scan = subparsers.add_parser("scan", help="扫描 portable-gpu-worker/videos/")
    sub_scan.set_defaults(func=cmd_scan)

    # status
    sub_status = subparsers.add_parser("status", help="查看处理状态")
    sub_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
