#!/usr/bin/env python3
"""
Java Learning Workflow - MCP Server
提供视频处理、字幕对齐、Anki 打包等工具给 Claude Code。
兼容任意 AI API 后端。
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── 路径配置 ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_ROOT = PROJECT_ROOT / "portable-gpu-worker"


def _detect_workspace() -> tuple[Path, Path, Path]:
    """项目固定使用 portable-gpu-worker 的 videos/output/scripts"""
    return (
        PORTABLE_ROOT / "videos",
        PORTABLE_ROOT / "output",
        PORTABLE_ROOT / "scripts",
    )


VIDEOS_DIR, OUTPUT_DIR, PORTABLE_SCRIPTS_DIR = _detect_workspace()
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"
MAIN_SCRIPTS_DIR = PROJECT_ROOT / "scripts"

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts"]

# ── Server init ──────────────────────────────────────────────────────────────
server = Server("java-learning-workflow")


def _get_python() -> str:
    venv = PROJECT_ROOT / ".venv"
    if sys.platform == "win32":
        p = venv / "Scripts" / "python.exe"
    else:
        p = venv / "bin" / "python"
    return str(p) if p.exists() else sys.executable


def _safe_dirname(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def _get_output_paths(video_stem: str, video_path: str = None) -> dict:
    """获取视频对应的输出路径结构。

    优先策略（按顺序）：
    1. 若 video_path 在 VIDEOS_DIR 内，则保留相对层级结构映射到 OUTPUT_DIR
       例：videos/Java基础-视频上/day01/01-xxx.mp4 → output/Java基础-视频上/day01/01-xxx/
    2. 扫描 OUTPUT_DIR 找到已存在的匹配目录（向后兼容）
    3. 退回到 OUTPUT_DIR/{safe_stem}/ 的平级结构（新建时默认）
    """
    safe_stem = _safe_dirname(video_stem)

    # 策略 1：根据 video_path 相对于 VIDEOS_DIR 推断层级
    if video_path:
        vp = Path(video_path).resolve()
        vd = VIDEOS_DIR.resolve()
        try:
            rel = vp.relative_to(vd)
            # rel = Java基础-视频上/day01/01-xxx.mp4 → parent = Java基础-视频上/day01
            base = OUTPUT_DIR / rel.parent / safe_stem
            prep = base / "_preprocessing"
            return {
                "base": str(base),
                "preprocessing": str(prep),
                "frames": str(prep / "frames"),
                "audio": str(prep / f"{safe_stem}_audio.wav"),
                "srt": str(prep / f"{safe_stem}.srt"),
                "words_json": str(prep / f"{safe_stem}_words.json"),
                "knowledge": str(base / f"knowledge_{safe_stem}.md"),
            }
        except ValueError:
            pass  # video_path 不在 VIDEOS_DIR 内，继续后续策略

    # 策略 2：扫描 OUTPUT_DIR 寻找已存在的同名目录（向后兼容旧产物）
    if OUTPUT_DIR.exists():
        for candidate in OUTPUT_DIR.rglob(safe_stem):
            if candidate.is_dir() and candidate.name == safe_stem:
                base = candidate
                prep = base / "_preprocessing"
                return {
                    "base": str(base),
                    "preprocessing": str(prep),
                    "frames": str(prep / "frames"),
                    "audio": str(prep / f"{safe_stem}_audio.wav"),
                    "srt": str(prep / f"{safe_stem}.srt"),
                    "words_json": str(prep / f"{safe_stem}_words.json"),
                    "knowledge": str(base / f"knowledge_{safe_stem}.md"),
                }

    # 策略 3：默认平级结构（用于新建）
    base = OUTPUT_DIR / safe_stem
    prep = base / "_preprocessing"
    return {
        "base": str(base),
        "preprocessing": str(prep),
        "frames": str(prep / "frames"),
        "audio": str(prep / f"{safe_stem}_audio.wav"),
        "srt": str(prep / f"{safe_stem}.srt"),
        "words_json": str(prep / f"{safe_stem}_words.json"),
        "knowledge": str(base / f"knowledge_{safe_stem}.md"),
    }


async def _run_subprocess(*cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    """异步执行子进程，避免阻塞事件循环。
    
    使用 run_in_executor + subprocess.run 代替 asyncio.create_subprocess_exec，
    以规避 Windows 上 MCP stdio 服务器中 asyncio 子进程的 ProactorEventLoop 死锁问题。
    """
    import concurrent.futures
    loop = asyncio.get_event_loop()

    def _blocking():
        result = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        return (
            result.returncode,
            result.stdout.decode("utf-8", errors="replace"),
            result.stderr.decode("utf-8", errors="replace"),
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await asyncio.wait_for(
                loop.run_in_executor(pool, _blocking),
                timeout=timeout + 5,  # 给线程多 5 秒缓冲
            )
    except (asyncio.TimeoutError, subprocess.TimeoutExpired):
        return -1, "", f"Timeout after {timeout}s"


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_video_metadata",
            description="获取视频文件的元数据：时长、帧率、分辨率、音频信息等",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"}
                },
                "required": ["video_path"]
            }
        ),
        Tool(
            name="transcribe_video",
            description="使用 faster-whisper 对视频进行语音转文字，生成 .srt 字幕和词级时间戳 JSON",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"},
                    "output_dir": {"type": "string", "description": "输出目录(默认使用标准路径)"},
                    "audio_path": {"type": "string", "description": "已提取的音频路径（优先于视频，避免重复解码，提升速度）"},
                    "model_size": {
                        "type": "string",
                        "enum": ["tiny", "base", "small", "medium", "large-v3"],
                        "default": "medium"
                    },
                    "language": {"type": "string", "default": "zh"},
                    "beam_size": {"type": "integer", "default": 5},
                    "device": {"type": "string", "enum": ["auto", "cpu", "cuda"], "default": "auto"},
                    "initial_prompt": {"type": "string"}
                },
                "required": ["video_path"]
            }
        ),
        Tool(
            name="extract_keyframes",
            description=(
                "从视频中提取场景切换关键帧。"
                "支持三种策略：PySceneDetect（AI自适应）→ FFmpeg scene filter → 固定间隔采样。"
                "若提供 words_json 路径，还会根据词级时间戳分析语速/停顿/关键词密度，"
                "在知识难点时刻补充提取关键帧，提升教学关键帧的准确率。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "scene_threshold": {"type": "number", "default": 0.25,
                                        "description": "FFmpeg scene 阈值（兜底用）"},
                    "fallback_interval": {"type": "integer", "default": 30,
                                          "description": "兜底间隔采样秒数"},
                    "max_frames": {"type": "integer", "default": 80,
                                   "description": "最终帧数上限（超出时均匀抽样）"},
                    "quality": {"type": "integer", "default": 2,
                                "description": "JPEG 质量 (1=最高, 31=最低)"},
                    "words_json": {
                        "type": "string",
                        "description": (
                            "词级时间戳 JSON 路径（{video_stem}_words.json）。"
                            "提供后，工具会分析语速骤降、长停顿、技术关键词密度，"
                            "在难点时刻自动补充关键帧，并在 frames_index.json 中记录 importance_signals。"
                        )
                    },
                    "words_gap": {
                        "type": "number", "default": 0.6,
                        "description": "停顿检测阈值（秒）。低于此值的词间停顿不触发额外帧。讲课类视频推荐0.6-0.8s（默认0.6）"
                    },
                    "words_proximity": {
                        "type": "number", "default": 10.0,
                        "description": "words引导帧与已有帧的最小距离（秒），距离更近的时刻会被跳过，避免重复（默认10s）"
                    }
                },
                "required": ["video_path", "output_dir"]
            }
        ),
        Tool(
            name="align_frames_to_transcript",
            description="将关键帧时间戳与字幕段落对齐，生成帧-段落映射表",
            inputSchema={
                "type": "object",
                "properties": {
                    "srt_path": {"type": "string"},
                    "frames_dir": {"type": "string"},
                    "words_json": {"type": "string"}
                },
                "required": ["srt_path", "frames_dir"]
            }
        ),
        Tool(
            name="export_anki_package",
            description="将 CSV 格式的 Anki 卡片打包为 .apkg 文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "deck_name": {"type": "string", "default": "Java 全栈学习"},
                    "include_images_dir": {"type": "string"}
                },
                "required": ["csv_path", "output_path"]
            }
        ),
        Tool(
            name="list_video_files",
            description="扫描 portable-gpu-worker/videos/ 目录，列出所有视频文件及元数据、处理状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "视频目录(默认 portable-gpu-worker/videos/)"},
                    "recursive": {"type": "boolean", "default": True}
                },
                "required": []
            }
        ),
        Tool(
            name="check_preprocessing_status",
            description="检查视频的预处理产物是否存在（字幕、关键帧、知识文档等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string"}
                },
                "required": ["video_path"]
            }
        ),
        Tool(
            name="split_long_video",
            description="对长视频（>90分钟）进行智能分段，按静音点切割为多个短视频",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "max_duration": {"type": "integer", "default": 5400},
                    "target_duration": {"type": "integer", "default": 2700}
                },
                "required": ["video_path"]
            }
        ),
        Tool(
            name="get_output_paths",
            description="获取视频对应的标准输出路径结构（含知识文档、预处理目录等路径）",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_name": {"type": "string", "description": "视频文件名(不含扩展名)"},
                    "video_path": {"type": "string", "description": "视频文件完整路径（可选，用于推断层级目录结构）"}
                },
                "required": ["video_name"]
            }
        ),
        Tool(
            name="check_environment",
            description="检查项目运行环境：Python、FFmpeg、虚拟环境、依赖安装状态",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="run_bootstrap",
            description="运行环境初始化脚本：创建虚拟环境、安装依赖、配置 MCP",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="query_knowledge_graph",
            description=(
                "查询课程知识图谱，了解某些概念是否已被覆盖、当前覆盖深度、以及首次出现位置。"
                "在处理新视频的流程A Step 2（与 get_video_metadata / check_preprocessing_status 同步调用，A1 字幕分析执行前）调用，以便判断处理模式（Full/Supplement/DeepDive/Practice）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "concept_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要查询的概念 ID 列表（可用话题名称，工具会做模糊匹配）"
                    },
                    "list_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "若为 true，返回全部已记录概念的摘要。必须配合 chapter_filter 使用，否则随课程增长 token 将持续厉增。"
                    },
                    "chapter_filter": {
                        "type": "string",
                        "description": "全部方式过滤：只返回指定章节中出现的概念。传入相对路径如 'Java基础-视频上/day01-Java入门'。list_all=true 时必填，可将 token 消耗保持在 ~10-15k 而不随课程全局增长。"
                    },
                    "compact": {
                        "type": "boolean",
                        "default": True,
                        "description": "若为 true（默认），每个概念只返回决策所需字段。Stage 1 分析和流程C均应保持默认。"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="update_knowledge_graph",
            description=(
                "在处理完一个视频的 A2 知识文档生成后（流程A Step 6），将该视频覆盖的知识点写入课程知识图谱。"
                "同时记录隐性知识（代码中出现但未口头解释的概念）和当前覆盖深度。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_stem": {"type": "string", "description": "视频文件名（不含扩展名）"},
                    "video_path": {"type": "string", "description": "视频完整路径（用于推断文档位置）"},
                    "knowledge_doc_path": {"type": "string", "description": "本视频生成的知识文档路径"},
                    "processing_mode": {
                        "type": "string",
                        "enum": ["Full", "Supplement", "DeepDive", "Practice"],
                        "description": "本视频使用的处理模式"
                    },
                    "covered_concepts": {
                        "type": "array",
                        "description": "本视频正式覆盖的概念列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_id": {"type": "string"},
                                "display_name": {"type": "string"},
                                "depth": {
                                    "type": "number",
                                    "description": "1=引介 2=运用 3=原理 4=专家"
                                },
                                "aspect": {"type": "string", "description": "覆盖的面（如 conceptual/installation/principle）"},
                                "summary": {"type": "string", "description": "该概念在本文档中的一句话摘要"}
                            },
                            "required": ["concept_id", "depth"]
                        }
                    },
                    "implicit_concepts": {
                        "type": "array",
                        "description": "代码/演示中出现但未口头解释的概念（depth=0.5）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_id": {"type": "string"},
                                "display_name": {"type": "string"},
                                "context": {"type": "string", "description": "出现的上下文（如'HelloWorld.java 代码演示中'）"}
                            },
                            "required": ["concept_id"]
                        }
                    },
                    "chapter_summary": {
                        "type": "string",
                        "description": "本视频知识文档的 2-3 句话摘要，供章节综合使用"
                    }
                },
                "required": ["video_stem", "covered_concepts"]
            }
        ),
        Tool(
            name="read_chapter_summaries",
            description=(
                "读取某章节目录下所有视频的摘要信息，用于生成章节综合文档。"
                "返回：所有视频的知识摘要、已覆盖概念汇总、待补全项清单。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "chapter_dir": {
                        "type": "string",
                        "description": (
                            "章节目录路径（如 portable-gpu-worker/output/Java基础-视频上/day01-Java入门）。"
                            "工具会扫描该目录下所有子目录中的 knowledge_*.md 和知识图谱条目。"
                        )
                    },
                    "include_graph_data": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否包含知识图谱中该章节相关的深度追踪数据"
                    }
                },
                "required": ["chapter_dir"]
            }
        ),
        Tool(
            name="scan_chapter_completeness",
            description=(
                "扫描某章节的知识完整性：检查知识图谱中该章节引入的概念是否有未覆盖的面、"
                "哪些隐性知识（depth=0.5）尚未正式解释、哪些概念预期在后续章节深化。"
                "输出用于章节综合文档末尾的'待补全清单'。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "chapter_dir": {"type": "string", "description": "章节目录路径"},
                    "course_scope": {
                        "type": "string",
                        "description": "课程范围关键词（如 'Java基础'），用于过滤无关概念"
                    }
                },
                "required": ["chapter_dir"]
            }
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tool dispatch
# ─────────────────────────────────────────────────────────────────────────────
@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handlers = {
        "get_video_metadata": _get_video_metadata,
        "transcribe_video": _transcribe_video,
        "extract_keyframes": _extract_keyframes,
        "align_frames_to_transcript": _align_frames,
        "export_anki_package": _export_anki,
        "list_video_files": _list_video_files,
        "check_preprocessing_status": _check_preprocessing_status,
        "split_long_video": _split_long_video,
        "get_output_paths": _get_output_paths_tool,
        "check_environment": _check_environment,
        "run_bootstrap": _run_bootstrap,
        "query_knowledge_graph": _query_knowledge_graph,
        "update_knowledge_graph": _update_knowledge_graph,
        "read_chapter_summaries": _read_chapter_summaries,
        "scan_chapter_completeness": _scan_chapter_completeness,
    }

    handler = handlers.get(name)
    if handler:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ─────────────────────────────────────────────────────────────────────────────
# Implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _get_video_metadata(args: dict) -> list[TextContent]:
    video_path = args["video_path"]
    if not Path(video_path).exists():
        return [TextContent(type="text", text=f"ERROR: File not found: {video_path}")]

    returncode, stdout, stderr = await _run_subprocess(
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", video_path,
        timeout=30
    )
    if returncode != 0:
        return [TextContent(type="text", text=f"ffprobe error: {stderr}")]

    try:
        data = json.loads(stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        meta = {
            "file_name": Path(video_path).name,
            "file_stem": Path(video_path).stem,
            "duration_seconds": duration,
            "duration_formatted": _format_duration(duration),
            "size_mb": round(int(data.get("format", {}).get("size", 0)) / 1024 / 1024, 1),
            "is_long_video": duration > 5400,
            "estimated_segments": max(1, int(duration / 2700)) if duration > 5400 else 1,
            "output_paths": _get_output_paths(Path(video_path).stem, video_path),
            "streams": []
        }
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                meta["streams"].append({
                    "type": "video",
                    "codec": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "fps": stream.get("r_frame_rate", "?")
                })
            elif stream.get("codec_type") == "audio":
                meta["streams"].append({
                    "type": "audio",
                    "codec": stream.get("codec_name"),
                    "sample_rate": stream.get("sample_rate"),
                    "channels": stream.get("channels")
                })
        return [TextContent(type="text", text=json.dumps(meta, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _transcribe_video(args: dict) -> list[TextContent]:
    video_path = args["video_path"]
    script = PORTABLE_SCRIPTS_DIR / "transcribe.py"

    if not script.exists():
        return [TextContent(type="text", text="ERROR: scripts/transcribe.py not found")]

    output_dir = args.get("output_dir",
                          str(Path(_get_output_paths(Path(video_path).stem, video_path)["preprocessing"])))
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 若未提供 initial_prompt，从 config.yaml 读取（提升 Java 技术词汇识别率）
    initial_prompt = args.get("initial_prompt")
    if not initial_prompt and CONFIG_FILE.exists():
        try:
            import yaml
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            initial_prompt = cfg.get("whisper", {}).get("initial_prompt")
        except Exception:
            pass

    cmd = [
        _get_python(), str(script),
        "--video", video_path,
        "--output-dir", output_dir,
        "--model", args.get("model_size", "medium"),
        "--language", args.get("language", "zh"),
        "--beam-size", str(args.get("beam_size", 5)),
        "--device", args.get("device", "auto"),
    ]
    if initial_prompt:
        cmd += ["--prompt", initial_prompt]
    # 若提供已提取音频，或输出目录下已有对应音频，优先使用（避免重复解码视频，提升转写速度）
    audio_path = args.get("audio_path")
    if not audio_path:
        safe_stem = _safe_dirname(Path(video_path).stem)
        default_audio = Path(output_dir) / f"{safe_stem}_audio.wav"
        if default_audio.exists():
            audio_path = str(default_audio)
    if audio_path and Path(audio_path).exists():
        cmd += ["--audio", audio_path]

    try:
        returncode, stdout, stderr = await _run_subprocess(*cmd, timeout=3600)
        if returncode != 0:
            return [TextContent(type="text", text=f"Transcription failed:\n{stderr}")]

        return [TextContent(type="text", text=stdout)]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text="ERROR: Transcription timed out after 1 hour")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _extract_keyframes(args: dict) -> list[TextContent]:
    video_path = args["video_path"]
    output_dir = args["output_dir"]
    threshold = args.get("scene_threshold", 0.25)
    fallback = args.get("fallback_interval", 30)
    max_frames = args.get("max_frames", 80)
    quality = args.get("quality", 2)
    words_json = args.get("words_json")
    words_gap = args.get("words_gap", 0.6)
    words_proximity = args.get("words_proximity", 10.0)

    # 若未提供 words_json，自动查找同目录下的 _words.json
    if not words_json:
        safe_stem = _safe_dirname(Path(video_path).stem)
        paths = _get_output_paths(Path(video_path).stem, video_path)
        candidate = Path(paths["preprocessing"]) / f"{safe_stem}_words.json"
        if candidate.exists():
            words_json = str(candidate)

    script = PORTABLE_SCRIPTS_DIR / "extract_keyframes.py"
    if not script.exists():
        return [TextContent(type="text", text="ERROR: scripts/extract_keyframes.py not found")]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cmd = [
        _get_python(), str(script),
        "--video", video_path,
        "--output-dir", output_dir,
        "--threshold", str(threshold),
        "--interval", str(fallback),
        "--max-frames", str(max_frames),
        "--quality", str(quality),
    ]
    if words_json and Path(words_json).exists():
        cmd += ["--words-json", words_json,
                "--words-gap", str(words_gap),
                "--words-proximity", str(words_proximity)]

    try:
        returncode, stdout, stderr = await _run_subprocess(*cmd, timeout=1800)
        if returncode != 0:
            return [TextContent(type="text", text=f"Keyframe extraction failed:\n{stderr}")]

        frames = sorted(Path(output_dir).glob("*.jpg"))
        index_file = Path(output_dir) / "frames_index.json"
        if index_file.exists():
            index_data = json.loads(index_file.read_text(encoding="utf-8"))
        else:
            index_data = {"frames": [
                {"filename": f.name, "type": "scene" if f.name.startswith("scene") else
                 ("words_guided" if f.name.startswith("words") else "interval")}
                for f in frames
            ]}

        words_guided_count = sum(
            1 for e in index_data.get("frames", []) if e.get("type") == "words_guided"
        )
        result = {
            "status": "success",
            "output_dir": output_dir,
            "total_frames": len(frames),
            "words_json_used": (words_json is not None),
            "words_guided_frames": words_guided_count,
            "index": index_data.get("frames", []),
            "script_output": stdout
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text="ERROR: Keyframe extraction timed out")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error extracting keyframes: {str(e)}")]


async def _align_frames(args: dict) -> list[TextContent]:
    """将关键帧时间戳与字幕段落对齐，优先读取 frames_index.json 中的精确时间戳"""
    srt_path = args["srt_path"]
    frames_dir = args["frames_dir"]

    if not Path(srt_path).exists():
        return [TextContent(type="text", text=f"SRT file not found: {srt_path}")]
    if not Path(frames_dir).exists():
        return [TextContent(type="text", text=f"Frames dir not found: {frames_dir}")]

    try:
        segments = _parse_srt(srt_path)

        # 优先从 frames_index.json 读取精确时间戳（extract_keyframes.py 生成的）
        index_file = Path(frames_dir) / "frames_index.json"
        frames_with_ts: list[dict] = []

        if index_file.exists():
            try:
                index_data = json.loads(index_file.read_text(encoding="utf-8"))
                for entry in index_data.get("frames", []):
                    fname = entry.get("filename", "")
                    fpath = Path(frames_dir) / fname
                    frames_with_ts.append({
                        "name": fname,
                        "path": str(fpath),
                        "timestamp_sec": entry.get("timestamp_s"),
                        "type": entry.get("type", "scene"),
                        "time_str": entry.get("time_str", ""),
                    })
            except Exception:
                pass  # fallback to filename-based estimation below

        # 若 frames_index.json 不可用，回退到文件名估算
        if not frames_with_ts:
            frames = sorted(Path(frames_dir).rglob("*.jpg"))
            total_duration = 0.0
            if segments:
                last_end = _srt_time_to_seconds(segments[-1]["end"])
                if last_end is not None:
                    total_duration = last_end
            scene_frames = [f for f in frames if f.name.startswith("scene_")]
            total_scene = len(scene_frames)

            for f in frames:
                scene_idx = next((j for j, sf in enumerate(scene_frames) if sf == f), None)
                ts = _extract_frame_timestamp(
                    f.name,
                    total_duration=total_duration if total_duration > 0 else None,
                    scene_index=(scene_idx + 1) if scene_idx is not None else None,
                    total_scene_frames=total_scene
                )
                frames_with_ts.append({
                    "name": f.name,
                    "path": str(f),
                    "timestamp_sec": ts,
                    "type": "scene" if f.name.startswith("scene_") else "interval",
                    "time_str": "",
                })

        # 对每个帧找到时间上最近的字幕段
        mapping = []
        for frame in frames_with_ts:
            ts = frame["timestamp_sec"]
            nearby = []
            if ts is not None and segments:
                for seg in segments:
                    seg_start = _srt_time_to_seconds(seg["start"])
                    seg_end = _srt_time_to_seconds(seg["end"])
                    if seg_start is not None and seg_end is not None:
                        if abs(ts - seg_start) < 120 or (seg_start <= ts <= seg_end):
                            nearby.append(seg)
                    if len(nearby) >= 3:
                        break
            if not nearby and segments:
                nearby = segments[:1]

            mapping.append({
                "frame": frame["name"],
                "frame_path": frame["path"],
                "frame_type": frame["type"],
                "timestamp_sec": ts,
                "time_str": frame.get("time_str", ""),
                "timestamp_source": "frames_index.json" if index_file.exists() else "filename_estimate",
                "nearby_segments": nearby[:3]
            })

        result = {
            "status": "success",
            "total_segments": len(segments),
            "total_frames": len(frames_with_ts),
            "timestamp_source": "frames_index.json" if index_file.exists() else "filename_estimate",
            "mapping": mapping
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error aligning frames: {str(e)}")]


async def _export_anki(args: dict) -> list[TextContent]:
    """直接 import generate_anki.generate_apkg() 在进程内执行，彻底规避 Windows asyncio 子进程死锁。"""
    import io
    import contextlib
    script = MAIN_SCRIPTS_DIR / "generate_anki.py"
    if not script.exists():
        return [TextContent(type="text", text="ERROR: scripts/generate_anki.py not found")]

    # 确保 scripts/ 在 sys.path 中
    scripts_dir = str(MAIN_SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("generate_anki", str(script))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # 捕获 generate_apkg 的 stdout 输出
        buf = io.StringIO()
        loop = asyncio.get_event_loop()
        import concurrent.futures

        def _run():
            with contextlib.redirect_stdout(buf):
                rc = mod.generate_apkg(
                    csv_path=args["csv_path"],
                    output_path=args["output_path"],
                    deck_name=args.get("deck_name", "Java 全栈学习"),
                    images_dir=args.get("include_images_dir"),
                )
            return rc

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            rc = await loop.run_in_executor(pool, _run)

        output = buf.getvalue().strip()
        if rc != 0:
            return [TextContent(type="text", text=f"Anki export failed (rc={rc}):\n{output}")]
        return [TextContent(type="text", text=output or f"Success: {args['output_path']}")]
    except Exception as e:
        import traceback
        return [TextContent(type="text", text=f"Error in export_anki_package: {e}\n{traceback.format_exc()}")]


async def _list_video_files(args: dict) -> list[TextContent]:
    directory = args.get("directory", str(VIDEOS_DIR))
    recursive = args.get("recursive", True)

    if not Path(directory).exists():
        return [TextContent(type="text", text=f"Directory not found: {directory}")]

    pattern = "**/*" if recursive else "*"
    files = []
    for ext in VIDEO_EXTENSIONS:
        files.extend(Path(directory).glob(f"{pattern}{ext}"))

    files = sorted(files)
    result = []

    for f in files:
        stat = f.stat()
        stem = f.stem
        duration = 0
        try:
            rc, stdout, _ = await _run_subprocess(
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(f),
                timeout=15
            )
            if rc == 0:
                data = json.loads(stdout)
                duration = float(data.get("format", {}).get("duration", 0))
        except Exception:
            pass

        paths = _get_output_paths(stem, str(f))
        prep_dir = Path(paths["preprocessing"])
        safe_stem = _safe_dirname(stem)
        has_srt = (prep_dir / f"{safe_stem}.srt").exists()
        if not has_srt and (prep_dir / "segments" / "_split_info.json").exists():
            has_srt = any(prep_dir.glob(f"{safe_stem}_part*.srt"))
        frames_path = prep_dir / "frames"
        frame_list = list(frames_path.glob("*.jpg")) if frames_path.exists() else []
        if not frame_list and frames_path.exists():
            for sub in frames_path.iterdir():
                if sub.is_dir():
                    frame_list.extend(sub.glob("*.jpg"))
        has_frames = len(frame_list) > 0
        has_knowledge = Path(paths["knowledge"]).exists()

        result.append({
            "name": f.name,
            "stem": stem,
            "path": str(f),
            "size_mb": round(stat.st_size / 1024 / 1024, 1),
            "duration_seconds": duration,
            "duration_formatted": _format_duration(duration),
            "is_long_video": duration > 5400,
            "status": {
                "has_srt": has_srt,
                "has_frames": has_frames,
                "has_knowledge": has_knowledge,
                "summary": "已完成" if has_knowledge else ("已预处理" if has_srt else "待处理")
            },
        })

    # Build per-chapter grouping (2-level relative path: course/day)
    videos_root = Path(directory).resolve()
    chapters: dict = {}
    for r in result:
        vpath = Path(r["path"]).resolve()
        try:
            rel = vpath.relative_to(videos_root)
            parts = rel.parts
            chapter_key = str(Path(*parts[:2])) if len(parts) >= 3 else str(Path(parts[0])) if parts else "(root)"
        except ValueError:
            chapter_key = "(unknown)"
        r["chapter"] = chapter_key
        if chapter_key not in chapters:
            chapters[chapter_key] = {"total": 0, "completed": 0, "preprocessed": 0, "pending": 0, "has_knowledge_doc": False}
        chapters[chapter_key]["total"] += 1
        s = r["status"]["summary"]
        if s == "已完成":
            chapters[chapter_key]["completed"] += 1
            chapters[chapter_key]["has_knowledge_doc"] = True
        elif s == "已预处理":
            chapters[chapter_key]["preprocessed"] += 1
        else:
            chapters[chapter_key]["pending"] += 1

    return [TextContent(type="text", text=json.dumps({
        "directory": directory,
        "total_files": len(result),
        "long_videos": sum(1 for r in result if r["is_long_video"]),
        "completed": sum(1 for r in result if r["status"]["has_knowledge"]),
        "preprocessed": sum(1 for r in result if r["status"]["has_srt"] and not r["status"]["has_knowledge"]),
        "pending": sum(1 for r in result if r["status"]["summary"] == "待处理"),
        "chapters": chapters,
        "files": [{k: v for k, v in r.items()} for r in result]
    }, ensure_ascii=False, indent=2))]


async def _check_preprocessing_status(args: dict) -> list[TextContent]:
    video_path = args["video_path"]
    video = Path(video_path)
    stem = video.stem
    safe_stem = _safe_dirname(stem)
    paths = _get_output_paths(stem, video_path)

    frames_dir = Path(paths["frames"])
    frame_list = list(frames_dir.glob("*.jpg")) if frames_dir.exists() else []

    srt_exists = Path(paths["srt"]).exists()

    # 长视频分段检测
    prep_dir = Path(paths["preprocessing"])
    split_info_path = prep_dir / "segments" / "_split_info.json"
    is_segmented = split_info_path.exists()
    if is_segmented and not srt_exists:
        srt_exists = any(prep_dir.glob(f"{safe_stem}_part*.srt"))

    # 计算实际 SRT 文件路径列表（分段视频有多个分段 SRT）
    if is_segmented:
        actual_srt_paths = sorted([str(p) for p in prep_dir.glob(f"{safe_stem}_part*.srt")])
    else:
        actual_srt_paths = [paths["srt"]] if Path(paths["srt"]).exists() else []

    # 帧目录也检查子目录（分段帧存放在 frames/{seg_stem}/）
    if not frame_list and frames_dir.exists():
        for sub in frames_dir.iterdir():
            if sub.is_dir():
                frame_list.extend(sub.glob("*.jpg"))

    topics_json = prep_dir / f"{safe_stem}_topics.json"
    teaching_style_json = prep_dir / f"{safe_stem}_teaching_style.json"

    status = {
        "video": str(video),
        "video_name": video.name,
        "exists": video.exists(),
        "is_segmented": is_segmented,
        "output_paths": paths,
        "artifacts": {
            "srt": {
                "path": paths["srt"],
                "exists": srt_exists,
                "srt_paths": actual_srt_paths,
                "note": "分段视频（is_segmented=true）请使用 srt_paths 列表逐段读取字幕；非分段视频直接使用 path" if is_segmented else ""
            },
            "words_json": {
                "path": paths["words_json"],
                "exists": Path(paths["words_json"]).exists()
            },
            "frames_dir": {
                "path": paths["frames"],
                "exists": frames_dir.exists(),
                "count": len(frame_list)
            },
            "topics_json": {
                "path": str(topics_json),
                "exists": topics_json.exists(),
                "note": "A1 字幕分析阶段产物（话题清单），若不存在需重新运行 A1_subtitle_analysis.md"
            },
            "teaching_style_json": {
                "path": str(teaching_style_json),
                "exists": teaching_style_json.exists(),
                "note": "A1 字幕分析阶段产物（教学风格），若不存在需重新运行 A1_subtitle_analysis.md"
            },
            "knowledge_doc": {
                "path": paths["knowledge"],
                "exists": Path(paths["knowledge"]).exists()
            },
        }
    }

    preprocessing_ready = all([
        srt_exists,
        len(frame_list) > 0
    ])
    stage1_complete = topics_json.exists() and teaching_style_json.exists()
    fully_complete = status["artifacts"]["knowledge_doc"]["exists"]

    status["preprocessing_complete"] = preprocessing_ready
    status["stage1_complete"] = stage1_complete
    status["fully_complete"] = fully_complete

    if fully_complete:
        status["recommendation"] = f"知识文档已生成（knowledge_{safe_stem}.md）。章节学习包（练习+Anki）通过流程C生成。"
    elif stage1_complete:
        status["recommendation"] = "A1 字幕分析已完成（_topics.json + _teaching_style.json），可运行 A2_knowledge_gen.md 生成知识文档"
    elif preprocessing_ready:
        status["recommendation"] = "预处理已完成，可运行 A1_subtitle_analysis.md（字幕分析 + 教学风格提取，流程A Step 3）"
    else:
        portable_bat = PORTABLE_ROOT / "0_开始使用.bat"
        if PORTABLE_ROOT.exists() and portable_bat.exists():
            status["recommendation"] = (
                "需要先运行预处理: 在 portable-gpu-worker 目录下执行 0_开始使用.bat，选择 [3] 开始预处理"
            )
        else:
            status["recommendation"] = (
                "需要先运行预处理: 请使用 portable-gpu-worker 的 0_开始使用.bat，选择 [3] 开始预处理"
            )

    return [TextContent(type="text", text=json.dumps(status, ensure_ascii=False, indent=2))]


async def _split_long_video(args: dict) -> list[TextContent]:
    video_path = args["video_path"]
    stem = Path(video_path).stem
    output_dir = args.get("output_dir",
                          str(Path(_get_output_paths(stem, video_path)["preprocessing"]) / "segments"))
    max_dur = args.get("max_duration", 5400)
    target_dur = args.get("target_duration", 2700)

    script = PORTABLE_SCRIPTS_DIR / "split_video.py"
    if not script.exists():
        return [TextContent(type="text", text="ERROR: scripts/split_video.py not found")]

    try:
        returncode, stdout, stderr = await _run_subprocess(
            _get_python(), str(script),
            "--video", video_path,
            "--output-dir", output_dir,
            "--max-duration", str(max_dur),
            "--target-duration", str(target_dur),
            "--json",
            timeout=1800
        )
        if returncode != 0:
            return [TextContent(type="text", text=f"Split failed:\n{stderr}")]
        return [TextContent(type="text", text=stdout)]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text="ERROR: Video splitting timed out")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _get_output_paths_tool(args: dict) -> list[TextContent]:
    video_name = args["video_name"]
    video_path = args.get("video_path")
    paths = _get_output_paths(video_name, video_path)
    return [TextContent(type="text", text=json.dumps(paths, ensure_ascii=False, indent=2))]


async def _check_environment(args: dict) -> list[TextContent]:
    env = {
        "project_root": str(PROJECT_ROOT),
        "python_version": sys.version,
        "platform": sys.platform,
    }

    venv_python = Path(_get_python())
    env["venv_exists"] = (PROJECT_ROOT / ".venv").exists()
    env["venv_python"] = str(venv_python)
    env["venv_python_exists"] = venv_python.exists()

    # ffmpeg (异步)
    rc, stdout, _ = await _run_subprocess("ffmpeg", "-version", timeout=10)
    env["ffmpeg_available"] = rc == 0
    env["ffmpeg_version"] = stdout.split("\n")[0] if rc == 0 else None

    # 依赖检查：在进程内直接用 importlib 检测，避免 Windows 子进程边界问题
    import importlib.util
    packages = {}
    for pkg in ["mcp", "faster_whisper", "genanki", "yaml", "rich", "scenedetect", "cv2"]:
        packages[pkg] = importlib.util.find_spec(pkg) is not None
    # scenedetect 安装包名为 scenedetect[opencv]，cv2 是其依赖
    packages["scenedetect_with_opencv"] = packages.get("scenedetect", False) and packages.get("cv2", False)

    env["dependencies"] = packages
    env["all_dependencies_ok"] = all(
        packages[k] for k in ["mcp", "faster_whisper", "genanki", "yaml", "rich"]
    )
    env["keyframe_detection_ok"] = packages.get("scenedetect_with_opencv", False)
    if not env["keyframe_detection_ok"]:
        env["keyframe_install_hint"] = ".venv/Scripts/pip install scenedetect[opencv]  # Windows"

    env["directories"] = {
        "videos": str(VIDEOS_DIR),
        "videos_exists": VIDEOS_DIR.exists(),
        "output": str(OUTPUT_DIR),
        "output_exists": OUTPUT_DIR.exists(),
    }

    mcp_config = PROJECT_ROOT / ".mcp.json"
    cursor_mcp_config = PROJECT_ROOT / ".cursor" / "mcp.json"
    vscode_mcp_config = PROJECT_ROOT / ".vscode" / "mcp.json"
    env["mcp_config_exists"] = mcp_config.exists()
    env["cursor_mcp_config_exists"] = cursor_mcp_config.exists()
    env["vscode_mcp_config_exists"] = vscode_mcp_config.exists()

    env["ready"] = all([
        env["venv_exists"],
        env["ffmpeg_available"],
        env["all_dependencies_ok"],
        env["mcp_config_exists"] or env["cursor_mcp_config_exists"] or env["vscode_mcp_config_exists"],
    ])

    return [TextContent(type="text", text=json.dumps(env, ensure_ascii=False, indent=2))]


async def _run_bootstrap(args: dict) -> list[TextContent]:
    bootstrap = MAIN_SCRIPTS_DIR / "bootstrap.py"
    if not bootstrap.exists():
        return [TextContent(type="text", text="ERROR: scripts/bootstrap.py not found")]

    try:
        returncode, stdout, stderr = await _run_subprocess(sys.executable, str(bootstrap), timeout=300)
        output = stdout + stderr
        return [TextContent(type="text", text=output)]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text="ERROR: Bootstrap timed out after 5 minutes")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error running bootstrap: {str(e)}")]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_srt(srt_path: str) -> list[dict]:
    segments = []
    with open(srt_path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3:
            try:
                time_parts = lines[1].split(" --> ")
                segments.append({
                    "index": lines[0].strip(),
                    "start": time_parts[0].strip(),
                    "end": time_parts[1].strip(),
                    "text": " ".join(lines[2:])
                })
            except (IndexError, ValueError):
                continue

    return segments


def _srt_time_to_seconds(time_str: str) -> float | None:
    """将 SRT 时间格式 (HH:MM:SS,mmm) 转换为秒"""
    try:
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except (IndexError, ValueError):
        return None


def _extract_frame_timestamp(filename: str, total_duration: float | None = None,
                             scene_index: int | None = None,
                             total_scene_frames: int = 1,
                             fallback_interval: int = 30) -> float | None:
    """从帧文件名推断时间戳（基于序号估算）
    - interval_*: ffmpeg %08d 是 1-based，实际时间 = (seq-1) × fallback_interval
    - scene_*: 无直接时间戳，需结合 total_duration 估算
    注意：有 frames_index.json 时不走此函数，此为纯 fallback。
    """
    match = re.search(r'(\d+)', filename)
    if not match:
        return None
    seq = int(match.group(1))
    if filename.startswith("interval"):
        # ffmpeg sequence starts at 1, so index i=0 → seq=1
        return max(0, seq - 1) * float(fallback_interval)
    # scene 帧：用序号在总时长中的比例估算（避免全部映射到第一段）
    if filename.startswith("scene") and total_duration and total_duration > 0:
        idx = scene_index if scene_index is not None else seq
        if total_scene_frames > 0:
            return (idx / total_scene_frames) * total_duration
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 知识图谱工具实现
# ─────────────────────────────────────────────────────────────────────────────

KNOWLEDGE_GRAPH_PATH = OUTPUT_DIR / "course_knowledge_graph.json"


def _load_knowledge_graph() -> dict:
    """加载知识图谱，不存在时返回初始结构。"""
    if KNOWLEDGE_GRAPH_PATH.exists():
        try:
            with open(KNOWLEDGE_GRAPH_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "version": "2.0",
        "concepts": {},
        "video_index": {},
        "last_updated": ""
    }


def _save_knowledge_graph(graph: dict) -> None:
    """保存知识图谱到磁盘。自动剥离旧版静态元数据（节省 ~3k tokens）。"""
    import datetime
    # 剥离静态文档键（这些内容在 SKILL.md 中维护，不需要在 JSON 文件里浪费空间）
    for key in ("description", "depth_scale", "processing_modes"):
        graph.pop(key, None)
    graph["last_updated"] = datetime.datetime.now().isoformat()
    KNOWLEDGE_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWLEDGE_GRAPH_PATH, encoding="utf-8", mode="w") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)


def _fuzzy_match_concept(graph: dict, query: str) -> list[str]:
    """模糊匹配概念 ID：先精确匹配，再按关键词匹配。"""
    concepts = graph.get("concepts", {})
    query_lower = query.lower()

    exact = [cid for cid in concepts if cid.lower() == query_lower]
    if exact:
        return exact

    partial = [
        cid for cid, cdata in concepts.items()
        if query_lower in cid.lower()
        or query_lower in cdata.get("display_name", "").lower()
        or any(query_lower in a.lower() for a in cdata.get("aspects_covered", []))
    ]
    return partial


def _migrate_concept_inplace(cdata: dict) -> None:
    """将旧格式（appearances 数组 + implicit_seen_in 数组）迁移为压缩格式。
    直接就地修改 cdata，安全可重入。
    """
    # 迁移 appearances → first_seen / first_doc / last_seen / seen_count
    apps = cdata.get("appearances")
    if isinstance(apps, list) and apps:
        first = apps[0]
        cdata.setdefault("first_seen", first.get("video_stem", ""))
        cdata.setdefault("first_doc",  first.get("doc", ""))
        if len(apps) > 1:
            cdata.setdefault("last_seen", apps[-1].get("video_stem", ""))
        cdata.setdefault("seen_count", len(apps))
        del cdata["appearances"]
    elif "appearances" in cdata:
        del cdata["appearances"]

    # 迁移 implicit_seen_in → first_implicit_video / implicit_count
    impl = cdata.get("implicit_seen_in")
    if isinstance(impl, list) and impl:
        cdata.setdefault("first_implicit_video", impl[0].get("video_stem", ""))
        cdata.setdefault("implicit_count", len(impl))
        del cdata["implicit_seen_in"]
    elif "implicit_seen_in" in cdata:
        del cdata["implicit_seen_in"]


async def _query_knowledge_graph(args: dict) -> list[TextContent]:
    graph = _load_knowledge_graph()
    concepts = graph.get("concepts", {})

    # 如果图谱尚未迁移，透明地迁移内存结构（下次 save 时持久化）
    for cdata in concepts.values():
        if "appearances" in cdata or "implicit_seen_in" in cdata:
            _migrate_concept_inplace(cdata)

    if args.get("list_all"):
        chapter_filter = args.get("chapter_filter", "").strip()
        video_index = graph.get("video_index", {})

        # 正刚必要：不提供 chapter_filter 将返回全部，但警告会很大
        if chapter_filter:
            # 找到属于该章节的所有 video_stem
            chapter_stems: set[str] = set()
            for stem, vdata in video_index.items():
                vpath = vdata.get("video_path", "")
                # 匹配方式：路径包含 chapter_filter（支持正旜斜和反斜）
                if chapter_filter.replace("\\", "/") in vpath.replace("\\", "/"):
                    chapter_stems.add(stem)
                    continue
                # 也尝试匹配 video_index 键中的概念列表
                for cid in vdata.get("concepts", []):
                    pass  # 部分匹配通过路径完成

            # 属于该章节的概念： first_seen 或 last_seen 在 chapter_stems 中
            matched_concepts = {
                cid: cdata for cid, cdata in concepts.items()
                if (cdata.get("first_seen", "") in chapter_stems
                    or cdata.get("last_seen",  "") in chapter_stems
                    or any(cid in vdata.get("concepts", [])
                           for stem, vdata in video_index.items()
                           if stem in chapter_stems))
            }
            source = matched_concepts
            filter_note = f"过滤章节: {chapter_filter}"
        else:
            source = concepts
            filter_note = "警告: 未使用 chapter_filter，返回全部概念，将随课程增长。建议传入 chapter_filter='课程/章节'。"

        summary = []
        for cid, cdata in source.items():
            entry = {
                "concept_id":         cid,
                "display_name":       cdata.get("display_name", cid),
                "current_depth":      cdata.get("current_depth", 0),
                "expected_max_depth": cdata.get("expected_max_depth", 4),
                "aspects_covered":    cdata.get("aspects_covered", []),
                "aspects_pending":    cdata.get("aspects_pending", []),
                "first_seen":         cdata.get("first_seen", ""),
                "first_doc":          cdata.get("first_doc",  ""),
            }
            if cdata.get("last_seen"):
                entry["last_seen"] = cdata["last_seen"]
            if cdata.get("seen_count", 0) > 1:
                entry["seen_count"] = cdata["seen_count"]
            summary.append(entry)
        return [TextContent(type="text", text=json.dumps({
            "total_concepts_in_filter": len(summary),
            "total_graph_concepts": len(concepts),
            "note": filter_note,
            "concepts": summary,
        }, ensure_ascii=False, indent=2))]

    concept_ids = args.get("concept_ids", [])
    compact = args.get("compact", True)  # 默认启用，A1 阶段查询省 tokens
    results = {}

    def _compact_concept(cdata: dict) -> dict:
        """只保留模式决策所需的核心字段。"""
        entry = {
            "concept_id":         cdata.get("concept_id", ""),
            "display_name":       cdata.get("display_name", ""),
            "current_depth":      cdata.get("current_depth", 0),
            "expected_max_depth": cdata.get("expected_max_depth", 4),
            "aspects_covered":    cdata.get("aspects_covered", []),
            "aspects_pending":    cdata.get("aspects_pending", []),
            "first_seen":         cdata.get("first_seen",  cdata.get("first_doc", "")),
        }
        return entry

    for qid in concept_ids:
        matched = _fuzzy_match_concept(graph, qid)
        if matched:
            concept_data = {
                m: (_compact_concept(concepts[m]) if compact else concepts[m])
                for m in matched
            }
            results[qid] = {"matched_ids": matched, "data": concept_data}
        else:
            results[qid] = {"matched_ids": [], "data": {}, "note": "未在知识图谱中找到该概念"}

    return [TextContent(type="text", text=json.dumps({
        "query_results": results,
        "graph_stats": {
            "total_concepts": len(concepts),
            "videos_processed": len(graph.get("video_index", {}))
        },
    }, ensure_ascii=False, indent=2))]


async def _update_knowledge_graph(args: dict) -> list[TextContent]:
    graph = _load_knowledge_graph()
    concepts = graph.setdefault("concepts", {})
    video_index = graph.setdefault("video_index", {})

    video_stem = args["video_stem"]
    video_path = args.get("video_path", "")
    knowledge_doc_path = args.get("knowledge_doc_path", "")
    processing_mode = args.get("processing_mode", "Full")
    chapter_summary = args.get("chapter_summary", "")

    # 推断文档的相对路径（相对于 OUTPUT_DIR）
    doc_rel_path = knowledge_doc_path
    if knowledge_doc_path:
        try:
            doc_rel_path = str(Path(knowledge_doc_path).relative_to(OUTPUT_DIR))
        except ValueError:
            doc_rel_path = knowledge_doc_path

    # 记录到 video_index
    covered_concept_ids: list[str] = []
    updated_concepts = []

    # 更新正式覆盖的概念
    for concept in args.get("covered_concepts", []):
        cid = concept["concept_id"]
        depth = float(concept.get("depth", 1))
        aspect = concept.get("aspect", "general")
        summary = concept.get("summary", "")
        display_name = concept.get("display_name", cid)

        if cid not in concepts:
            concepts[cid] = {
                "concept_id": cid,
                "display_name": display_name,
                "current_depth": depth,
                "expected_max_depth": 4,
                "aspects_covered": [aspect],
                "aspects_pending": [],
                "first_seen":  video_stem,
                "first_doc":   doc_rel_path,
                "seen_count":  1,
            }
        else:
            existing = concepts[cid]
            # 如果是旧格式，先就地迁移
            if "appearances" in existing or "implicit_seen_in" in existing:
                _migrate_concept_inplace(existing)
            if depth > existing.get("current_depth", 0):
                existing["current_depth"] = depth
            if display_name and not existing.get("display_name"):
                existing["display_name"] = display_name
            covered = existing.setdefault("aspects_covered", [])
            if aspect not in covered:
                covered.append(aspect)
            # 从 pending 中移除已覆盖的 aspect
            pending = existing.get("aspects_pending", [])
            if aspect in pending:
                pending.remove(aspect)
            # 更新次数计数和最近一次出现
            existing["seen_count"] = existing.get("seen_count", 1) + 1
            existing["last_seen"]  = video_stem

        covered_concept_ids.append(cid)
        updated_concepts.append(cid)

    # 记录隐性知识（depth=0.5）
    implicit_added = []
    for implicit in args.get("implicit_concepts", []):
        cid = implicit["concept_id"]
        context = implicit.get("context", "")
        display_name = implicit.get("display_name", cid)

        if cid not in concepts:
            concepts[cid] = {
                "concept_id": cid,
                "display_name": display_name,
                "current_depth": 0.5,
                "expected_max_depth": 4,
                "aspects_covered": [],
                "aspects_pending": [],
                "first_implicit_video": video_stem,
                "implicit_count": 1,
            }
        else:
            existing = concepts[cid]
            if "appearances" in existing or "implicit_seen_in" in existing:
                _migrate_concept_inplace(existing)
            if not existing.get("first_implicit_video"):
                existing["first_implicit_video"] = video_stem
            existing["implicit_count"] = existing.get("implicit_count", 0) + 1
            # 只有在没有正式覆盖时，才保持 depth=0.5
            if existing.get("current_depth", 0) < 1:
                existing["current_depth"] = 0.5
        implicit_added.append(cid)

    # 记录到 video_index（包含本视频覆盖的概念列表，供章节过滤使用）
    video_index[video_stem] = {
        "video_path":    video_path,
        "knowledge_doc": doc_rel_path,
        "processing_mode": processing_mode,
        "chapter_summary": chapter_summary,
        "concepts":       covered_concept_ids,  # 为 chapter_filter 提供快速查找
    }

    _save_knowledge_graph(graph)

    return [TextContent(type="text", text=json.dumps({
        "status": "success",
        "video_stem": video_stem,
        "processing_mode": processing_mode,
        "updated_concepts": updated_concepts,
        "implicit_concepts_recorded": implicit_added,
        "total_graph_concepts": len(concepts),
        "knowledge_graph_path": str(KNOWLEDGE_GRAPH_PATH)
    }, ensure_ascii=False, indent=2))]


async def _read_chapter_summaries(args: dict) -> list[TextContent]:
    chapter_dir = Path(args["chapter_dir"])
    include_graph = args.get("include_graph_data", True)

    if not chapter_dir.exists():
        return [TextContent(type="text", text=f"ERROR: Chapter directory not found: {chapter_dir}")]

    graph = _load_knowledge_graph() if include_graph else {}
    video_index = graph.get("video_index", {})

    summaries = []
    for video_dir in sorted(chapter_dir.iterdir()):
        if not video_dir.is_dir() or video_dir.name.startswith("_"):
            continue
        if video_dir.name.startswith("CHAPTER_SYNTHESIS") or video_dir.name.startswith("DAY"):
            continue

        knowledge_files = list(video_dir.glob("knowledge_*.md"))

        video_stem = video_dir.name
        graph_data = video_index.get(video_stem, {})

        # 读取知识文档前200字符作为摘要预览
        doc_preview = ""
        if knowledge_files:
            try:
                with open(knowledge_files[0], encoding="utf-8") as f:
                    content = f.read(800)
                    # 提取标题和前几行
                    lines = [l for l in content.split("\n") if l.strip()]
                    doc_preview = "\n".join(lines[:8])
            except IOError:
                pass

        # 读取已保存的 chapter_summary.json（如存在）
        prep_dir = video_dir / "_preprocessing"
        summary_json_path = prep_dir / f"{_safe_dirname(video_stem)}_chapter_summary.json"
        saved_summary = {}
        if summary_json_path.exists():
            try:
                with open(summary_json_path, encoding="utf-8") as f:
                    saved_summary = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        summaries.append({
            "video_stem": video_stem,
            "dir": str(video_dir),
            "has_knowledge_doc": bool(knowledge_files),
            "processing_mode": graph_data.get("processing_mode", "unknown"),
            "chapter_summary": graph_data.get("chapter_summary", saved_summary.get("summary", "")),
            "doc_preview": doc_preview,
            "saved_summary": saved_summary,
            "knowledge_doc_path": str(knowledge_files[0]) if knowledge_files else None,
        })

    # 从知识图谱中提取本章相关概念
    chapter_concepts = {}
    if include_graph:
        chapter_stems = {s["video_stem"] for s in summaries}
        for cid, cdata in graph.get("concepts", {}).items():
            # 新格式：通过 first_seen/last_seen 或 video_index.concepts 判断是否属于本章
            in_chapter = (
                cdata.get("first_seen", "") in chapter_stems
                or cdata.get("last_seen", "") in chapter_stems
            )
            if not in_chapter:
                for stem in chapter_stems:
                    if cid in video_index.get(stem, {}).get("concepts", []):
                        in_chapter = True
                        break
            if in_chapter:
                chapter_concepts[cid] = {
                    "display_name":    cdata.get("display_name", cid),
                    "current_depth":   cdata.get("current_depth", 0),
                    "aspects_covered": cdata.get("aspects_covered", []),
                }

    unprocessed = [s["video_stem"] for s in summaries if not s["has_knowledge_doc"]]

    return [TextContent(type="text", text=json.dumps({
        "chapter_dir": str(chapter_dir),
        "total_videos": len(summaries),
        "processed_videos": sum(1 for s in summaries if s["has_knowledge_doc"]),
        "unprocessed_videos": unprocessed,
        "all_processed": len(unprocessed) == 0,
        "summaries": summaries,
        "chapter_concepts_count": len(chapter_concepts),
        "chapter_concepts": chapter_concepts,
    }, ensure_ascii=False, indent=2))]


async def _scan_chapter_completeness(args: dict) -> list[TextContent]:
    chapter_dir = Path(args["chapter_dir"])
    graph = _load_knowledge_graph()

    if not chapter_dir.exists():
        return [TextContent(type="text", text=f"ERROR: Chapter directory not found: {chapter_dir}")]

    video_index = graph.get("video_index", {})
    all_concepts = graph.get("concepts", {})

    # 收集本章涉及的所有 video_stems
    chapter_stems = set()
    for video_dir in chapter_dir.iterdir():
        if video_dir.is_dir() and not video_dir.name.startswith(("_", "CHAPTER", "DAY")):
            chapter_stems.add(video_dir.name)

    # 分析本章概念的完整性
    implicit_not_explained = []   # depth=0.5，在本章未正式解释
    shallow_but_important = []    # depth=1，预期会更深
    multi_aspect_partial = []     # 只覆盖了部分面

    for cid, cdata in all_concepts.items():
        # 新格式：通过 first_seen/last_seen 或 video_index.concepts 判断是否属于本章
        is_in_chapter = (
            cdata.get("first_seen", "") in chapter_stems
            or cdata.get("last_seen", "") in chapter_stems
            or cdata.get("first_implicit_video", "") in chapter_stems
        )
        if not is_in_chapter:
            for stem in chapter_stems:
                if cid in video_index.get(stem, {}).get("concepts", []):
                    is_in_chapter = True
                    break
        if not is_in_chapter:
            continue

        cur_depth = cdata.get("current_depth", 0)
        exp_depth = cdata.get("expected_max_depth", 4)
        pending = cdata.get("aspects_pending", [])

        if cur_depth <= 0.5:
            implicit_not_explained.append({
                "concept_id": cid,
                "display_name": cdata.get("display_name", cid),
                "first_seen_in": cdata.get("first_implicit_video", cdata.get("first_seen", "")),
                "note": "代码中出现过，尚未正式讲解"
            })
        elif cur_depth < exp_depth:
            shallow_but_important.append({
                "concept_id": cid,
                "display_name": cdata.get("display_name", cid),
                "current_depth": cur_depth,
                "expected_max_depth": exp_depth,
                "aspects_pending": pending,
                "note": f"当前深度 {cur_depth}/4，后续会更深讲解"
            })

        if pending:
            multi_aspect_partial.append({
                "concept_id": cid,
                "display_name": cdata.get("display_name", cid),
                "aspects_covered": cdata.get("aspects_covered", []),
                "aspects_pending": pending
            })

    # 生成 completeness_audit.md 内容
    audit_lines = [
        f"# 章节完整性核查 — {chapter_dir.name}\n",
        f"扫描时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"本章已处理视频：{len([v for v in chapter_stems if v in video_index])}/{len(chapter_stems)}\n",
        "",
        "## ⚠ 代码中出现但尚未正式讲解的概念",
    ]
    if implicit_not_explained:
        for item in implicit_not_explained:
            audit_lines.append(f"- `{item['display_name']}`（见于 {item['first_seen_in']}）")
    else:
        audit_lines.append("- 无")

    audit_lines += [
        "",
        "## 📈 本章引入但后续才完整覆盖的概念",
    ]
    if shallow_but_important:
        for item in shallow_but_important:
            audit_lines.append(
                f"- `{item['display_name']}`：当前深度 {item['current_depth']}/4"
                + (f"，待覆盖面：{', '.join(item['aspects_pending'])}" if item['aspects_pending'] else "")
            )
    else:
        audit_lines.append("- 无")

    audit_content = "\n".join(audit_lines)

    # 保存 audit 文件
    synthesis_dir = chapter_dir / f"CHAPTER_SYNTHESIS_{chapter_dir.name}"
    synthesis_dir.mkdir(parents=True, exist_ok=True)
    audit_path = synthesis_dir / "chapter_completeness_audit.md"
    try:
        with open(audit_path, "w", encoding="utf-8") as f:
            f.write(audit_content)
    except IOError as e:
        pass

    return [TextContent(type="text", text=json.dumps({
        "status": "success",
        "chapter_dir": str(chapter_dir),
        "audit_path": str(audit_path),
        "implicit_not_explained": implicit_not_explained,
        "shallow_but_important": shallow_but_important,
        "multi_aspect_partial": multi_aspect_partial,
        "audit_content": audit_content
    }, ensure_ascii=False, indent=2))]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
