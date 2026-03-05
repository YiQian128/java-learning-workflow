"""
java-learning-workflow GUI Launcher
启动时弹出可视化选择窗口，让用户选择要处理的章节和操作。
右侧面板动态显示选中章节的详情及各操作的效果预判。
输出 JSON 到 stdout 供后续流程（AI/脚本）读取。
"""
import json
import os
import sys
import argparse
import re
import tkinter as tk
from tkinter import ttk, font as tkfont
from pathlib import Path

# ── 路径推断 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE   = SCRIPT_DIR.parent
VIDEOS_DIR  = WORKSPACE / "portable-gpu-worker" / "videos"
OUTPUT_DIR  = WORKSPACE / "portable-gpu-worker" / "output"
VIDEO_EXTS   = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}
RESULT_FILE  = SCRIPT_DIR / "_gui_result.json"   # 结果文件，GUI 关闭后写入，--wait 模式轮询此文件

# ── 环境探测 ──────────────────────────────────────────────────────────────────
def detect_environment() -> str:
    """
    检测当前 AI 运行环境。
    返回: 'copilot' | 'cursor' | 'claude-code' | 'codex' | 'generic'
    优先级: Cursor > Copilot(VS Code) > Claude Code > Codex > Generic
    """
    has_vscode  = any(k.startswith("VSCODE_") for k in os.environ)
    has_cursor  = (WORKSPACE / ".cursor" / "mcp.json").exists() or \
                  (Path(os.environ.get("USERPROFILE", os.environ.get("HOME", ""))) / ".cursor" / "mcp.json").exists()
    has_claude  = (WORKSPACE / ".mcp.json").exists() or (WORKSPACE / ".claude").exists()
    has_codex   = bool(os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_ENV"))

    if has_cursor:
        return "cursor"
    if has_vscode:
        return "copilot"
    if has_claude:
        return "claude-code"
    if has_codex:
        return "codex"
    return "generic"

CURRENT_ENV = detect_environment()

# ── 各环境模型预设 ─────────────────────────────────────────────────────────────
# budget = 单次 Session 最大可消耗 tokens，计算方式：
#   Claude Code / 原生 API：ctx * 0.70（工具调用额外开销少）
#   Copilot / Cursor / Codex：ctx * 0.55（系统提示 + 会话历史占用多）
# 每视频固定消耗估算：提示词 ~8k + 知识图谱往返 ~4k + 输出 ~12k = 24k overhead
OVERHEAD_PER_VIDEO = 24_000   # tokens

_MODELS_CLAUDE_CODE = {
    "claude-sonnet": {"label": "Claude Sonnet",   "budget": 140_000, "ctx": 200_000},
    "claude-opus":   {"label": "Claude Opus",     "budget": 160_000, "ctx": 200_000},
    "custom-small":  {"label": "其他（小上下文）",  "budget":  50_000, "ctx":  80_000},
}

# GitHub Copilot 模型 — 按截图真实上下文窗口计算（ctx 为输入窗口大小）
_MODELS_COPILOT = {
    # ── Claude family（输入 128K × 0.55 ≈ 70k；Sonnet 4 输出仅 16K 故保守取 55k）──
    "cop-claude-sonnet-4.6": {"label": "Claude Sonnet 4.6", "budget":  70_000, "ctx": 128_000},
    "cop-claude-sonnet-4.5": {"label": "Claude Sonnet 4.5", "budget":  65_000, "ctx": 128_000},
    "cop-claude-opus-4.6":   {"label": "Claude Opus 4.6",   "budget":  70_000, "ctx": 128_000},
    "cop-claude-haiku-4.5":  {"label": "Claude Haiku 4.5",  "budget":  60_000, "ctx": 128_000},
    # ── GPT Codex 大窗口（272K × 0.52 ≈ 140k）──────────────────────────────────
    "cop-gpt-5.3-codex":     {"label": "GPT-5.3-Codex",     "budget": 140_000, "ctx": 272_000},
    "cop-gpt-5.2-codex":     {"label": "GPT-5.2-Codex",     "budget": 140_000, "ctx": 272_000},
    # ── GPT 标准（128K × 0.55 ≈ 70k）───────────────────────────────────────────
    "cop-gpt-5.1-codex-max": {"label": "GPT-5.1-Codex-Max", "budget":  70_000, "ctx": 128_000},
    "cop-gpt-5.1-codex":     {"label": "GPT-5.1-Codex",     "budget":  70_000, "ctx": 128_000},
    "cop-gpt-5.1":           {"label": "GPT-5.1",           "budget":  65_000, "ctx": 128_000},
    "cop-gpt-5-mini":        {"label": "GPT-5 mini",        "budget":  65_000, "ctx": 128_000},
    "cop-gpt-4.1":           {"label": "GPT-4.1",           "budget":  55_000, "ctx": 111_000},
    "cop-raptor-mini":       {"label": "Raptor mini",        "budget":  90_000, "ctx": 200_000},
    # ── Gemini（109K × 0.52 ≈ 57k）─────────────────────────────────────────────
    "cop-gemini-2.5-pro":    {"label": "Gemini 2.5 Pro",    "budget":  55_000, "ctx": 109_000},
    # ── 受限模型──────────────────────────────────────────────────────────────────
    "cop-gpt-4o":            {"label": "GPT-4o ⚠小",         "budget":  25_000, "ctx":  64_000},
}

_MODELS_CURSOR = {
    "cur-claude-sonnet": {"label": "Claude Sonnet",   "budget": 100_000, "ctx": 200_000},
    "cur-claude-opus":   {"label": "Claude Opus",     "budget": 120_000, "ctx": 200_000},
    "cur-gpt-4o":        {"label": "GPT-4o",          "budget":  55_000, "ctx": 128_000},
    "cur-deepseek-v3":   {"label": "DeepSeek-V3",     "budget":  90_000, "ctx": 160_000},
    "cur-custom":        {"label": "其他（小上下文）",  "budget":  50_000, "ctx":  80_000},
}

_MODELS_CODEX = {
    "codex-gpt-5.3-codex":      {"label": "GPT-5.3-Codex",     "budget": 150_000, "ctx": 272_000},
    "codex-gpt-5.2-codex":      {"label": "GPT-5.2-Codex",     "budget": 140_000, "ctx": 272_000},
    "codex-gpt-5.1-codex-max":  {"label": "GPT-5.1-Codex-Max", "budget": 110_000, "ctx": 128_000},
    "codex-gpt-5.1-codex":      {"label": "GPT-5.1-Codex",     "budget": 100_000, "ctx": 128_000},
    "codex-gpt-5.1":            {"label": "GPT-5.1",           "budget":  65_000, "ctx": 128_000},
}

_MODELS_GENERIC = {
    "claude-sonnet": {"label": "Claude Sonnet",   "budget": 140_000, "ctx": 200_000},
    "claude-opus":   {"label": "Claude Opus",     "budget": 160_000, "ctx": 200_000},
    "gpt-4o":        {"label": "GPT-4o",          "budget":  55_000, "ctx": 128_000},
    "deepseek-v3":   {"label": "DeepSeek-V3",     "budget":  90_000, "ctx": 160_000},
    "custom-small":  {"label": "其他（小上下文）",  "budget":  50_000, "ctx":  80_000},
}

_ENV_MODELS: dict[str, dict] = {
    "claude-code": _MODELS_CLAUDE_CODE,
    "copilot":     _MODELS_COPILOT,
    "cursor":      _MODELS_CURSOR,
    "codex":       _MODELS_CODEX,
    "generic":     _MODELS_GENERIC,
}

_ENV_DEFAULT: dict[str, str] = {
    "claude-code": "claude-sonnet",
    "copilot":     "cop-claude-sonnet-4.6",
    "cursor":      "cur-claude-sonnet",
    "codex":       "codex-gpt-5.1-codex",
    "generic":     "claude-sonnet",
}

_ENV_BADGE: dict[str, tuple[str, str]] = {
    # env → (显示名称, 徽章底色)
    "claude-code": ("Claude Code",     "#5a3a8a"),
    "copilot":     ("GitHub Copilot",  "#1f5a2a"),
    "cursor":      ("Cursor",          "#1a4a7a"),
    "codex":       ("OpenAI Codex",    "#10503a"),
    "generic":     ("通用模式",         "#3a3a3a"),
}

# 当前环境的模型预设（模块级快捷访问，兼容旧引用）
MODEL_PRESETS  = _ENV_MODELS[CURRENT_ENV]
DEFAULT_MODEL  = _ENV_DEFAULT[CURRENT_ENV]

# ── 颜色/风格 ─────────────────────────────────────────────────────────────────
CLR_BG       = "#1e1e2e"
CLR_SURFACE  = "#2a2a3e"
CLR_CARD     = "#313149"
CLR_PANEL    = "#252538"
CLR_ACCENT   = "#7c5cbf"
CLR_DONE     = "#4caf7d"
CLR_PREP     = "#f0a500"
CLR_PEND     = "#555577"
CLR_TEXT     = "#e0e0f0"
CLR_MUTED    = "#8888aa"
CLR_HOVER    = "#3d3d5c"
CLR_SEL      = "#4a3a6a"
CLR_BTN_A    = "#5a4a8a"   # 处理整章
CLR_BTN_C    = "#2a5fa8"   # 生成学习包
CLR_BTN_M    = "#3a3a52"   # 手动
CLR_BTN_X    = "#553333"   # 取消
CLR_WARN     = "#c07830"
CLR_INFO     = "#4a90d9"
CLR_DIVIDER  = "#3a3a54"
CLR_MODEL    = "#1a3a2a"
CLR_MODEL_SEL = "#2a5a3a"
CLR_SESSION  = "#2a3a5a"

# ── 数据层 ────────────────────────────────────────────────────────────────────
def _safe_dirname(stem: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', stem)

def _srt_bytes(video_stem: str, course: str, day: str) -> int:
    """返回视频字幕文件总字节数（用于估算 token 消耗）。"""
    safe = _safe_dirname(video_stem)
    prep = OUTPUT_DIR / course / day / safe / "_preprocessing"
    if prep.exists():
        files = list(prep.glob(f"{safe}*.srt"))
        total = sum(f.stat().st_size for f in files)
        if total > 0:
            return total
    return 5_000  # 无 SRT 时默认 5KB

def build_session_plan(info: dict, model_key: str, force_reprocess: bool = False) -> list[dict]:
    """按 SRT 大小贪心填充 Session。
    force_reprocess=False（默认）：跳过已完成和待预处理视频。
    force_reprocess=True：保留已完成视频（重新处理），仍跳过无字幕的待处理视频。
    """
    budget  = MODEL_PRESETS[model_key]["budget"]
    course  = info["course"]
    day     = info["day"]
    sessions: list[dict] = []
    cur_videos: list[str] = []
    cur_tokens = 0
    for v in info["videos"]:
        if v["status"] == "pending":
            continue  # 无字幕，始终跳过
        if v["status"] == "completed" and not force_reprocess:
            continue  # 已完成，仅在非强制模式下跳过
        cost = _srt_bytes(v["name"], course, day) // 4 + OVERHEAD_PER_VIDEO
        if cur_videos and cur_tokens + cost > budget:
            sessions.append({"index": len(sessions), "videos": cur_videos,
                             "video_count": len(cur_videos), "est_tokens": cur_tokens,
                             "status": "pending"})
            cur_videos, cur_tokens = [], 0
        cur_videos.append(v["name"])
        cur_tokens += cost
    if cur_videos:
        sessions.append({"index": len(sessions), "videos": cur_videos,
                         "video_count": len(cur_videos), "est_tokens": cur_tokens,
                         "status": "pending"})
    return sessions

def scan_chapters() -> dict:
    """扫描 videos/ 目录，返回按 course/day 分组的章节信息（含视频文件列表）。"""
    if not VIDEOS_DIR.exists():
        return {}

    chapters = {}
    for course_dir in sorted(VIDEOS_DIR.iterdir()):
        if not course_dir.is_dir() or course_dir.name.startswith('.'):
            continue
        for day_dir in sorted(course_dir.iterdir()):
            if not day_dir.is_dir() or day_dir.name.startswith('.'):
                continue
            videos = sorted([f for f in day_dir.iterdir() if f.suffix.lower() in VIDEO_EXTS])
            if not videos:
                continue

            total = len(videos)
            completed = preprocessed = 0
            video_details = []
            for v in videos:
                safe = _safe_dirname(v.stem)
                out_base = OUTPUT_DIR / course_dir.name / day_dir.name / safe
                prep_dir = out_base / "_preprocessing"
                has_knowledge = any(out_base.glob("knowledge_*.md")) if out_base.exists() else False
                if prep_dir.exists():
                    has_srt = (prep_dir / f"{safe}.srt").exists() or \
                              any(prep_dir.glob(f"{safe}_part*.srt"))
                else:
                    has_srt = False
                if has_knowledge:
                    status = "completed"
                    completed += 1
                elif has_srt:
                    status = "preprocessed"
                    preprocessed += 1
                else:
                    status = "pending"
                video_details.append({"name": v.stem, "status": status})

            synth_dir = OUTPUT_DIR / course_dir.name / day_dir.name
            has_synthesis = any(synth_dir.glob("CHAPTER_SYNTHESIS_*/CHAPTER_SYNTHESIS_*.md")) \
                            if synth_dir.exists() else False

            key = f"{course_dir.name}/{day_dir.name}"
            chapters[key] = {
                "course": course_dir.name,
                "day": day_dir.name,
                "path": str(day_dir),
                "total": total,
                "completed": completed,
                "preprocessed": preprocessed,
                "pending": total - completed - preprocessed,
                "has_synthesis": has_synthesis,
                "videos": video_details,
            }
    return chapters

# ── GUI ───────────────────────────────────────────────────────────────────────
class LauncherApp(tk.Tk):
    def __init__(self, chapters: dict):
        super().__init__()
        self.chapters = chapters
        self.env = CURRENT_ENV
        self.model_presets = _ENV_MODELS[self.env]
        self.selected_chapter_key: str | None = None
        self.result: dict | None = None
        self.selected_model = tk.StringVar(value=_ENV_DEFAULT[self.env])

        env_name = _ENV_BADGE[self.env][0]
        self.title(f"Java 学习工作流  —  选择处理目标  [{env_name}]")
        self.configure(bg=CLR_BG)
        self.resizable(True, True)
        self.minsize(1040, 560)

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1200, sw - 60), min(800, sh - 80)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._build_fonts()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.selected_model.trace_add("write", lambda *_: self._on_model_change())

    def _build_fonts(self):
        self.f_title   = tkfont.Font(family="Microsoft YaHei UI", size=14, weight="bold")
        self.f_course  = tkfont.Font(family="Microsoft YaHei UI", size=10, weight="bold")
        self.f_day     = tkfont.Font(family="Microsoft YaHei UI", size=10)
        self.f_count   = tkfont.Font(family="Consolas", size=9)
        self.f_btn     = tkfont.Font(family="Microsoft YaHei UI", size=9, weight="bold")
        self.f_status  = tkfont.Font(family="Microsoft YaHei UI", size=9)
        self.f_phead   = tkfont.Font(family="Microsoft YaHei UI", size=11, weight="bold")
        self.f_pbody   = tkfont.Font(family="Microsoft YaHei UI", size=9)
        self.f_pcode   = tkfont.Font(family="Consolas", size=9)
        self.f_psub    = tkfont.Font(family="Microsoft YaHei UI", size=8)
        self.f_model   = tkfont.Font(family="Microsoft YaHei UI", size=8, weight="bold")

    # ── 整体布局 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # 顶部标题栏
        hdr = tk.Frame(self, bg=CLR_SURFACE, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📚  Java 全栈学习工作流", font=self.f_title,
                 bg=CLR_SURFACE, fg=CLR_TEXT).pack(side="left", padx=20)
        # 环境徽章
        env_name, env_color = _ENV_BADGE[self.env]
        tk.Label(hdr, text=f" {env_name} ", font=self.f_model,
                 bg=env_color, fg=CLR_TEXT, padx=6, pady=3).pack(side="left", padx=4)
        total_prep = sum(c["preprocessed"] for c in self.chapters.values())
        total_v    = sum(c["total"]       for c in self.chapters.values())
        total_done = sum(c["completed"]   for c in self.chapters.values())
        total_pend = sum(c["pending"]     for c in self.chapters.values())
        tk.Label(hdr,
                 text=f"全部视频 {total_v}  |  已完成 {total_done}  已预处理 {total_prep}  待处理 {total_pend}",
                 font=self.f_status, bg=CLR_SURFACE, fg=CLR_MUTED).pack(side="right", padx=20)

        tk.Frame(self, bg=CLR_ACCENT, height=2).pack(fill="x")

        # 主体：左章节列表 + 右预览面板
        body = tk.Frame(self, bg=CLR_BG)
        body.pack(fill="both", expand=True)

        # ── 左侧 ──
        left_wrap = tk.Frame(body, bg=CLR_BG)
        left_wrap.pack(side="left", fill="both", expand=True)

        # 图例
        legend = tk.Frame(left_wrap, bg=CLR_BG, pady=5)
        legend.pack(fill="x", padx=14)
        tk.Label(legend, text="进度条：", fg=CLR_MUTED, bg=CLR_BG, font=self.f_psub).pack(side="left")
        for color, label in [(CLR_DONE, "已完成"), (CLR_PREP, "已预处理(有字幕)"), (CLR_PEND, "待处理")]:
            tk.Label(legend, text="■", fg=color, bg=CLR_BG, font=self.f_count).pack(side="left", padx=(4, 1))
            tk.Label(legend, text=label, fg=CLR_MUTED, bg=CLR_BG, font=self.f_psub).pack(side="left", padx=(0, 8))

        # 可滚动章节列表
        list_frame = tk.Frame(left_wrap, bg=CLR_BG)
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, bg=CLR_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=CLR_BG)
        self.scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._populate_chapters()

        # ── 分隔线 ──
        tk.Frame(body, bg=CLR_DIVIDER, width=1).pack(side="left", fill="y")

        # ── 右侧预览面板 ──
        self.panel = tk.Frame(body, bg=CLR_PANEL, width=400)
        self.panel.pack(side="left", fill="y")
        self.panel.pack_propagate(False)
        self._build_panel_idle()

        # ── 底部操作栏 ──
        bottom_wrap = tk.Frame(self, bg=CLR_SURFACE)
        bottom_wrap.pack(fill="x", side="bottom")

        # 模型选择行
        model_row = tk.Frame(bottom_wrap, bg=CLR_SURFACE, pady=5)
        model_row.pack(fill="x", padx=14)
        tk.Label(model_row, text="当前模型：", font=self.f_psub,
                 bg=CLR_SURFACE, fg=CLR_MUTED).pack(side="left")
        self._model_btns: dict[str, tk.Label] = {}
        for key_m, preset in self.model_presets.items():
            btn_m = tk.Label(model_row, text=preset["label"], font=self.f_model,
                             bg=CLR_MODEL, fg=CLR_TEXT, padx=8, pady=3, cursor="hand2")
            btn_m.bind("<Button-1>", lambda e, k=key_m: self.selected_model.set(k))
            btn_m.pack(side="left", padx=2)
            self._model_btns[key_m] = btn_m
        # 显示所选模型的上下文信息
        self._lbl_model_info = tk.Label(model_row, text="", font=self.f_psub,
                                        bg=CLR_SURFACE, fg=CLR_MUTED)
        self._lbl_model_info.pack(side="left", padx=6)
        self._refresh_model_btns()

        # 状态行 + 操作按钮
        bottom = tk.Frame(bottom_wrap, bg=CLR_SURFACE, pady=7)
        bottom.pack(fill="x", padx=14)
        self.lbl_sel = tk.Label(bottom, text="← 点击左侧章节行选择目标",
                                font=self.f_status, bg=CLR_SURFACE, fg=CLR_MUTED)
        self.lbl_sel.pack(side="left")

        btn_frame = tk.Frame(bottom, bg=CLR_SURFACE)
        btn_frame.pack(side="right")

        self.btn_a = self._make_btn(btn_frame, "▶  处理整章  A→C", CLR_BTN_A,
                                    self._action_process_chapter,
                                    hover_cb=lambda: self._update_panel("process"))
        self.btn_a.pack(side="left", padx=3)

        self.btn_r = self._make_btn(btn_frame, "♻  重新处理", "#5a3e6b",
                                    self._action_force_reprocess,
                                    hover_cb=lambda: self._update_panel("reprocess"))
        self.btn_r.pack(side="left", padx=3)

        self.btn_c = self._make_btn(btn_frame, "⚑  生成学习包  C", CLR_BTN_C,
                                    self._action_synthesis,
                                    hover_cb=lambda: self._update_panel("synthesis"))
        self.btn_c.pack(side="left", padx=3)

        self.btn_m = self._make_btn(btn_frame, "✎  手动指定", CLR_BTN_M,
                                    self._action_manual,
                                    hover_cb=lambda: self._update_panel("manual"))
        self.btn_m.pack(side="left", padx=3)

        self.btn_x = self._make_btn(btn_frame, "✕  取消", CLR_BTN_X,
                                    self._on_close,
                                    hover_cb=lambda: self._update_panel("cancel"))
        self.btn_x.pack(side="left", padx=3)

    # ── 模型选择 ──────────────────────────────────────────────────────────────
    def _refresh_model_btns(self):
        sel = self.selected_model.get()
        for key_m, btn_m in self._model_btns.items():
            btn_m.config(bg=CLR_MODEL_SEL if key_m == sel else CLR_MODEL)
        preset = self.model_presets.get(sel, {})
        ctx    = preset.get("ctx", 0)
        budget = preset.get("budget", 0)
        info   = f"  ctx {ctx//1000}K  →  Session 预算 {budget//1000}K tokens  （剩余留给系统提示 + 历史）"
        self._lbl_model_info.config(text=info)

    def _on_model_change(self):
        self._refresh_model_btns()
        if self.selected_chapter_key:
            self._build_panel_chapter(self.selected_chapter_key)

    def _make_btn(self, parent, text, color, cmd, hover_cb=None):
        btn = tk.Label(parent, text=text, font=self.f_btn, bg=color, fg=CLR_TEXT,
                       padx=14, pady=7, cursor="hand2", relief="flat")
        btn.bind("<Button-1>", lambda e: cmd())
        lighter = self._lighten(color, 30)
        btn.bind("<Enter>", lambda e: (btn.config(bg=lighter), hover_cb() if hover_cb else None))
        btn.bind("<Leave>", lambda e: (btn.config(bg=color), self._restore_panel()))
        return btn

    @staticmethod
    def _lighten(hex_color: str, amount: int) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        r = min(255, r + amount); g = min(255, g + amount); b = min(255, b + amount)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── 章节列表 ─────────────────────────────────────────────────────────────
    def _populate_chapters(self):
        by_course: dict[str, list] = {}
        for key, info in self.chapters.items():
            by_course.setdefault(info["course"], []).append((key, info))

        self.chapter_rows: dict[str, tk.Frame] = {}

        for course, items in by_course.items():
            hf = tk.Frame(self.scroll_frame, bg=CLR_BG)
            hf.pack(fill="x", padx=10, pady=(10, 2))
            tk.Label(hf, text=f"📁  {course}", font=self.f_course,
                     bg=CLR_BG, fg=CLR_ACCENT).pack(side="left")
            total_c = sum(i["total"] for _, i in items)
            done_c  = sum(i["completed"] for _, i in items)
            prep_c  = sum(i["preprocessed"] for _, i in items)
            tk.Label(hf, text=f"  已完成 {done_c}  已预处理 {prep_c}  共 {total_c}",
                     font=self.f_count, bg=CLR_BG, fg=CLR_MUTED).pack(side="left", padx=6)
            for key, info in items:
                self.chapter_rows[key] = self._build_chapter_row(key, info)

    def _build_chapter_row(self, key: str, info: dict) -> tk.Frame:
        outer = tk.Frame(self.scroll_frame, bg=CLR_BG, pady=1)
        outer.pack(fill="x", padx=20)

        card = tk.Frame(outer, bg=CLR_CARD, cursor="hand2")
        card.pack(fill="x")

        left = tk.Frame(card, bg=CLR_CARD)
        left.pack(side="left", fill="x", expand=True, padx=10, pady=7)

        name_frame = tk.Frame(left, bg=CLR_CARD)
        name_frame.pack(anchor="w")
        tk.Label(name_frame, text=f"📂  {info['day']}", font=self.f_day,
                 bg=CLR_CARD, fg=CLR_TEXT).pack(side="left")
        if info["has_synthesis"]:
            tk.Label(name_frame, text="  ✔ 学习包", font=self.f_psub,
                     bg=CLR_CARD, fg=CLR_DONE).pack(side="left", padx=4)

        bar_frame = tk.Frame(left, bg=CLR_CARD)
        bar_frame.pack(anchor="w", pady=(3, 0))
        self._draw_bar(bar_frame, info, width=240)

        right = tk.Frame(card, bg=CLR_CARD)
        right.pack(side="right", padx=12, pady=7)
        tk.Label(right,
                 text=f"共{info['total']}  ✔{info['completed']}  ◎{info['preprocessed']}  ○{info['pending']}",
                 font=self.f_count, bg=CLR_CARD, fg=CLR_MUTED).pack()

        def _enter(e, w=card):
            for c in _all_children(w): 
                try: c.config(bg=CLR_HOVER)
                except: pass
            w.config(bg=CLR_HOVER)
        def _leave(e, w=card):
            bg = CLR_SEL if key == self.selected_chapter_key else CLR_CARD
            for c in _all_children(w):
                try: c.config(bg=bg)
                except: pass
            w.config(bg=bg)
        def _click(e, k=key): self._select_chapter(k)

        for w in [card] + list(_all_children(card)):
            w.bind("<Enter>", _enter); w.bind("<Leave>", _leave); w.bind("<Button-1>", _click)

        return card

    def _draw_bar(self, parent: tk.Frame, info: dict, width: int = 240):
        total = max(info["total"], 1)
        h = 6
        cnv = tk.Canvas(parent, width=width, height=h, bg=CLR_CARD, highlightthickness=0)
        cnv.pack(side="left")
        x = 0
        for count, color in [(info["completed"], CLR_DONE),
                              (info["preprocessed"], CLR_PREP),
                              (info["pending"], CLR_PEND)]:
            w = int(width * count / total)
            if w > 0:
                cnv.create_rectangle(x, 0, x+w, h, fill=color, outline="")
            x += w

    # ── 章节选择 ──────────────────────────────────────────────────────────────
    def _select_chapter(self, key: str):
        for k, card in self.chapter_rows.items():
            bg = CLR_SEL if k == key else CLR_CARD
            for c in _all_children(card):
                try: c.config(bg=bg)
                except: pass
            card.config(bg=bg)

        self.selected_chapter_key = key
        info = self.chapters[key]
        self.lbl_sel.config(
            text=f"✔ 已选：{info['day']}（{info['total']} 个视频）  — 悬停按钮查看 Session 规划与操作说明",
            fg=CLR_TEXT)
        self._build_panel_chapter(key)

    # ── 右侧面板 ──────────────────────────────────────────────────────────────
    def _clear_panel(self):
        for w in self.panel.winfo_children():
            w.destroy()

    def _build_panel_idle(self):
        self._clear_panel()
        tk.Label(self.panel, text="\n\n\n点击左侧章节行\n查看详情与操作说明",
                 font=self.f_pbody, bg=CLR_PANEL, fg=CLR_MUTED,
                 justify="center").pack(expand=True)

    def _build_panel_chapter(self, key: str):
        self._clear_panel()
        info = self.chapters[key]

        # 章节标题
        tk.Label(self.panel, text=f"  {info['day']}", font=self.f_phead,
                 bg=CLR_PANEL, fg=CLR_TEXT, anchor="w").pack(fill="x", padx=14, pady=(14,4))
        tk.Label(self.panel, text=f"  {info['course']}", font=self.f_psub,
                 bg=CLR_PANEL, fg=CLR_MUTED, anchor="w").pack(fill="x", padx=14)

        tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=8)

        # 状态统计
        stats = tk.Frame(self.panel, bg=CLR_PANEL)
        stats.pack(fill="x", padx=14)
        for label, val, color in [
            ("已完成（有知识文档）", info["completed"],    CLR_DONE),
            ("已预处理（有字幕）",  info["preprocessed"], CLR_PREP),
            ("待处理（无字幕）",    info["pending"],       CLR_PEND),
            ("合计",               info["total"],          CLR_TEXT),
        ]:
            row = tk.Frame(stats, bg=CLR_PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"  {label}", font=self.f_pbody,
                     bg=CLR_PANEL, fg=color, width=22, anchor="w").pack(side="left")
            tk.Label(row, text=str(val), font=self.f_pcode,
                     bg=CLR_PANEL, fg=color).pack(side="left")

        # 进度条（大）
        bar_f = tk.Frame(self.panel, bg=CLR_PANEL)
        bar_f.pack(fill="x", padx=14, pady=(6,0))
        self._draw_bar(bar_f, info, width=360)

        tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=8)

        # Session 规划预览
        model_key  = self.selected_model.get()
        model_name = self.model_presets[model_key]["label"]
        budget     = self.model_presets[model_key]["budget"]
        sessions   = build_session_plan(info, model_key)

        if not sessions:
            if info["preprocessed"] == 0 and info["completed"] < info["total"]:
                tk.Label(self.panel, text="  ⚠ 无字幕视频，请先用 portable-gpu-worker 预处理",
                         font=self.f_pbody, bg=CLR_PANEL, fg=CLR_WARN, anchor="w").pack(fill="x", padx=14)
            else:
                tk.Label(self.panel, text=f"  ✔ 已预处理视频均已完成（共{info['completed']}个）",
                         font=self.f_pbody, bg=CLR_PANEL, fg=CLR_DONE, anchor="w").pack(fill="x", padx=14)
                if info["completed"] > 0:
                    tk.Label(self.panel, text="  ♻ 需重新生成？点击底部「♻ 重新处理」按钮",
                             font=self.f_psub, bg=CLR_PANEL, fg="#b08fd4", anchor="w").pack(fill="x", padx=14)
        else:
            tk.Label(self.panel, text=f"  Session 规划（{model_name} · {budget//1000}k budget）",
                     font=self.f_pbody, bg=CLR_PANEL, fg=CLR_INFO, anchor="w").pack(fill="x", padx=14)

            nxt_idx = 0
            for s in sessions:
                is_next = s["index"] == nxt_idx
                bg      = CLR_SESSION if is_next else CLR_PANEL
                icon    = "▶" if is_next else "○"
                badge_clr = CLR_PREP if is_next else CLR_MUTED
                pct       = s["est_tokens"] / budget * 100

                sf = tk.Frame(self.panel, bg=bg)
                sf.pack(fill="x", padx=14, pady=1)
                hl = tk.Frame(sf, bg=bg)
                hl.pack(fill="x", padx=6, pady=(3,1))
                tk.Label(hl, text=f" {icon} Session {s['index']+1}",
                         font=self.f_pcode, bg=bg, fg=badge_clr).pack(side="left")
                tk.Label(hl, text=f"  {s['video_count']} 视频  ~{s['est_tokens']//1000}k/{budget//1000}k ({pct:.0f}%)",
                         font=self.f_psub, bg=bg, fg=CLR_MUTED).pack(side="left")
                for vname in s["videos"][:4]:
                    short = vname if len(vname) <= 30 else vname[:28] + "…"
                    tk.Label(sf, text=f"    · {short}",
                             font=self.f_psub, bg=bg, fg=CLR_MUTED, anchor="w").pack(fill="x", padx=6)
                if len(s["videos"]) > 4:
                    tk.Label(sf, text=f"    … 还有 {len(s['videos'])-4} 个",
                             font=self.f_psub, bg=bg, fg=CLR_PEND, anchor="w").pack(fill="x", padx=6)

            # 跳过摘要
            skip_parts = []
            if info["completed"]:  skip_parts.append(f"✔ 跳过 {info['completed']} 个已完成")
            if info["pending"]:    skip_parts.append(f"○ 跳过 {info['pending']} 个待预处理")
            if skip_parts:
                tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=3)
                for part in skip_parts:
                    clr = CLR_DONE if part.startswith("✔") else CLR_PEND
                    tk.Label(self.panel, text=f"  {part}",
                             font=self.f_psub, bg=CLR_PANEL, fg=clr, anchor="w").pack(fill="x", padx=14)

        if info["has_synthesis"]:
            tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=4)
            tk.Label(self.panel, text="  ✔  章节学习包已生成",
                     font=self.f_pbody, bg=CLR_PANEL, fg=CLR_DONE, anchor="w").pack(fill="x", padx=14)

        tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=(6,4))
        tk.Label(self.panel, text="  将鼠标悬停在底部按钮上查看操作说明",
                 font=self.f_psub, bg=CLR_PANEL, fg=CLR_MUTED, justify="left").pack(fill="x", padx=14)

    def _restore_panel(self):
        if self.selected_chapter_key:
            self._build_panel_chapter(self.selected_chapter_key)
        else:
            self._build_panel_idle()

    def _update_panel(self, action: str):
        """悬停按钮时，在右侧面板显示该操作的详细说明。"""
        self._clear_panel()
        info = self.chapters.get(self.selected_chapter_key) if self.selected_chapter_key else None

        configs = {
            "process": {
                "icon": "▶", "color": CLR_BTN_A,
                "title": "处理整章  （流程 A → C）",
                "subtitle": "逐视频生成知识文档，全部完成后自动生成章节学习包",
            },
            "reprocess": {
                "icon": "♻", "color": "#5a3e6b",
                "title": "强制重新处理（含已完成视频）",
                "subtitle": "忽略已完成状态，重新生成所有有字幕视频的知识文档",
            },
            "synthesis": {
                "icon": "⚑", "color": CLR_BTN_C,
                "title": "仅生成章节学习包  （流程 C）",
                "subtitle": "跳过视频处理，直接整合已有知识文档生成章节学习包",
            },
            "manual": {
                "icon": "✎", "color": CLR_BTN_M,
                "title": "手动指定目标",
                "subtitle": "以文字对话方式灵活指定处理范围",
            },
            "cancel": {
                "icon": "✕", "color": CLR_BTN_X,
                "title": "取消",
                "subtitle": "关闭此窗口，不启动任何处理",
            },
        }
        cfg = configs.get(action, configs["manual"])

        # 标题块
        title_f = tk.Frame(self.panel, bg=cfg["color"])
        title_f.pack(fill="x")
        tk.Label(title_f, text=f"  {cfg['icon']}  {cfg['title']}",
                 font=self.f_phead, bg=cfg["color"], fg=CLR_TEXT,
                 anchor="w", pady=10).pack(fill="x", padx=14)

        tk.Label(self.panel, text=f"  {cfg['subtitle']}",
                 font=self.f_psub, bg=CLR_PANEL, fg=CLR_MUTED,
                 anchor="w", pady=4).pack(fill="x", padx=14)

        tk.Frame(self.panel, bg=CLR_DIVIDER, height=1).pack(fill="x", padx=14, pady=6)

        def section(title, lines, title_color=CLR_TEXT):
            tk.Label(self.panel, text=f"  {title}", font=self.f_pbody,
                     bg=CLR_PANEL, fg=title_color, anchor="w").pack(fill="x", padx=14, pady=(6,2))
            for line in lines:
                color = CLR_MUTED
                if line.startswith("✔"): color = CLR_DONE
                elif line.startswith("◎"): color = CLR_PREP
                elif line.startswith("○"): color = CLR_PEND
                elif line.startswith("⚠"): color = CLR_WARN
                elif line.startswith("📄") or line.startswith("📘") or line.startswith("📝") or line.startswith("🃏"): color = CLR_INFO
                tk.Label(self.panel, text=f"    {line}", font=self.f_pbody,
                         bg=CLR_PANEL, fg=color, anchor="w").pack(fill="x", padx=14)

        # ── 各操作详细说明 ────────────────────────────────────────────────
        if action == "process":
            model_key  = self.selected_model.get()
            model_name = self.model_presets[model_key]["label"]
            budget     = self.model_presets[model_key]["budget"]
            if info:
                sessions = build_session_plan(info, model_key)
                n_sess   = len(sessions)

                if n_sess == 0:
                    section("无可处理视频", [
                        "⚠ 所有视频均已完成或尚无字幕。",
                        "  已完成 → 直接跳过",
                        "  无字幕 → 需先用 portable-gpu-worker 预处理",
                    ], CLR_WARN)
                else:
                    # Session 规划摘要
                    section(f"Session 规划（{model_name} · {budget//1000}k token 预算）", [
                        f"◎ 共 {info['preprocessed']} 个可处理视频 → 拆为 {n_sess} 个 Session",
                        f"✔ 跳过 {info['completed']} 个已完成",
                        f"○ 跳过 {info['pending']} 个待预处理",
                    ])
                    for s in sessions:
                        pct = s["est_tokens"] / budget * 100
                        icon = "▶" if s["index"] == 0 else "○"
                        status_txt = "本次处理" if s["index"] == 0 else "待续"
                        clr = CLR_PREP if s["index"] == 0 else CLR_MUTED
                        tk.Label(self.panel,
                                 text=f"    {icon} S{s['index']+1}：{s['video_count']} 视频  ~{s['est_tokens']//1000}k ({pct:.0f}%)  [{status_txt}]",
                                 font=self.f_psub, bg=CLR_PANEL, fg=clr, anchor="w").pack(fill="x", padx=14)

                section("每个视频将生成", [
                    "📄 knowledge_*.md    知识文档",
                ])
                section("全章完成后统一生成（多轮对话）", [
                    "📘 CHAPTER_SYNTHESIS_*.md   章节学习手册（Pass 2a）",
                    "📝 CHAPTER_EXERCISES_*.md   全章练习题集（Pass 2b）",
                    "🃏 CHAPTER_ANKI_*.apkg      全章 Anki 卡包（Pass 2c）",
                ])
                section("本 Session 完成后", [
                    "  AI 告知本次 Session 结束并提示下一 Session",
                    "  重新运行 GUI，每次启动实时扫描最新进度",
                    "  全部 Session 完成后自动触发流程 C",
                ])
                if info["pending"] > 0:
                    section("注意", [
                        f"⚠ {info['pending']} 个视频尚无字幕，将被跳过",
                    ], CLR_WARN)
            else:
                section("操作步骤", [
                    "1. 选中左侧章节",
                    "2. AI 按差量模式逐 Session 处理",
                    "3. 全部完成后自动生成章节学习包",
                ])

        elif action == "synthesis":
            if info:
                ok_ratio = info["completed"] / max(info["total"], 1)
                section("前提与当前状态", [
                    f"✔ 已完成 {info['completed']} / {info['total']} 个视频（{ok_ratio:.0%}）",
                ], CLR_TEXT)
                if info["completed"] == 0:
                    section("⚠ 当前无可整合内容", [
                        "还没有任何视频完成知识文档，",
                        "建议先用「处理整章」完成视频处理。",
                    ], CLR_WARN)
                elif ok_ratio < 0.5:
                    section("⚠ 建议完成更多视频后再整合", [
                        f"当前仅完成 {ok_ratio:.0%}，章节学习包内容会不完整。",
                        "可继续处理后再运行流程 C。",
                    ], CLR_WARN)
                else:
                    section("将整合已完成的知识文档，生成", [
                        "📘 CHAPTER_SYNTHESIS_*.md   连贯完整的章节学习手册",
                        "📝 CHAPTER_EXERCISES_*.md   全章综合练习题集",
                        "🃏 CHAPTER_ANKI_*.apkg      全章 Anki 卡包（基于章节综合从零生成）",
                        "📄 chapter_completeness_audit.md   待补全清单",
                    ], CLR_DONE)
                    section("⚠ 生成方式：多轮对话（非一次完成）", [
                        "  Pass 2a → SYNTHESIS（保存后等确认）",
                        "  Pass 2b → EXERCISES（读磁盘 synthesis，保存后等确认）",
                        "  Pass 2c → ANKI（读磁盘 synthesis，生成 CSV + apkg）",
                        "  标准章节额外先做：Pass 1 → outline.json",
                    ], CLR_INFO)
            else:
                section("说明", [
                    "请先选中左侧章节，再查看本操作的具体效果。",
                ])

        elif action == "reprocess":
            model_key  = self.selected_model.get()
            model_name = self.model_presets[model_key]["label"]
            budget     = self.model_presets[model_key]["budget"]
            if info:
                sessions = build_session_plan(info, model_key, force_reprocess=True)
                section(f"Session 规划（强制模式，{model_name}）", [
                    f"◎ 共 {info['preprocessed'] + info['completed']} 个视频（含已完成）→ 拆为 {len(sessions)} 个 Session",
                    f"✔ 已完成 {info['completed']} 个（将被重新生成）",
                    f"○ 跳过 {info['pending']} 个待预处理",
                ])
                section("⚠ 注意", [
                    "会覆盖已有的视频级知识文档（knowledge_*.md），",
                    "知识图谱中相关概念的深度/摘要也将被重新更新。",
                    "章节学习包（SYNTHESIS / EXERCISES / ANKI）不受影响；",
                    "如需重新生成学习包，Flow A 完成后再用「⚑ 生成学习包」。",
                ])
            else:
                section("说明", ["请先选中左侧章节再查看此操作效果。"])

        elif action == "manual":
            section("适用场景", [
                "● 只处理某个 / 某几个视频",
                "● 重新处理已完成的视频",
                "● 自定义处理范围或参数",
            ])
            section("操作方式", [
                "点击此按钮后，直接在 AI 对话框输入需求，",
                "例如：「处理 day01 第 3 到第 5 个视频」",
            ])

        elif action == "cancel":
            section("说明", [
                "关闭此窗口，不执行任何处理。",
                "重新打开项目时会再次弹出此界面。",
            ])

    # ── 操作响应 ──────────────────────────────────────────────────────────────
    def _action_process_chapter(self, force_reprocess: bool = False):
        if not self.selected_chapter_key:
            self.lbl_sel.config(text="⚠ 请先点击左侧章节行选择目标", fg=CLR_WARN)
            return
        info      = self.chapters[self.selected_chapter_key]
        model_key = self.selected_model.get()
        sessions  = build_session_plan(info, model_key, force_reprocess=force_reprocess)

        if not sessions:
            self.lbl_sel.config(text="⚠ 没有可处理的视频（全部已完成或无字幕）", fg=CLR_WARN)
            return

        # 每次 GUI 启动都是全新扫描，cur_idx 始终从 0（当前计划第一个 Session）开始
        cur_idx     = 0
        cur_session = sessions[cur_idx]

        self.result = {
            "action": "process_chapter",
            "env": self.env,
            "chapter_key": self.selected_chapter_key,
            "course": info["course"],
            "day": info["day"],
            "day_path": info["path"],
            "chapter_output_dir": str(OUTPUT_DIR / info["course"] / info["day"]),
            "total": info["total"],
            "completed": info["completed"],
            "preprocessed": info["preprocessed"],
            "pending": info["pending"],
            # Session 信息
            "model": model_key,
            "token_budget": self.model_presets[model_key]["budget"],
            "total_sessions": len(sessions),
            "current_session_index": cur_idx,
            "current_session_videos": cur_session["videos"],
            "current_session_est_tokens": cur_session["est_tokens"],
            "is_resume": info["completed"] > 0 and not force_reprocess,
            "force_reprocess": force_reprocess,
        }
        _write_result_file(self.result)
        self.destroy()

    def _action_force_reprocess(self):
        """强制重新处理所有已完成 + 已预处理的视频（忽略 completed 状态）。"""
        self._action_process_chapter(force_reprocess=True)

    def _action_synthesis(self):
        if not self.selected_chapter_key:
            self.lbl_sel.config(text="⚠ 请先点击左侧章节行选择目标", fg=CLR_WARN)
            return
        info = self.chapters[self.selected_chapter_key]
        self.result = {
            "action": "synthesis",
            "env": self.env,
            "chapter_key": self.selected_chapter_key,
            "course": info["course"],
            "day": info["day"],
            "day_path": info["path"],
            "total": info["total"],
            "completed": info["completed"],
            "preprocessed": info["preprocessed"],
            "pending": info["pending"],
            "chapter_output_dir": str(OUTPUT_DIR / info["course"] / info["day"]),
        }
        _write_result_file(self.result)   # 立即写文件
        self.destroy()

    def _action_manual(self):
        self.result = {"action": "manual", "env": self.env}
        _write_result_file(self.result)   # 立即写文件
        self.destroy()

    def _on_close(self):
        self.result = {"action": "cancelled"}
        _write_result_file(self.result)   # 立即写文件
        self.destroy()


def _write_result_file(result: dict) -> None:
    """将结果立即写入文件，供 await_terminal 提前返回时 AI 轮询读取。"""
    try:
        RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _all_children(widget) -> list:
    children = list(widget.winfo_children())
    for child in list(children):
        children.extend(_all_children(child))
    return children

# ── 入口 ──────────────────────────────────────────────────────────────────────
def main():
    # ── 解析参数 ────────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env", choices=["copilot", "cursor", "claude-code", "codex", "generic"],
                        default=None, help="AI 环境标识，由调用方传入以覆盖自动探测")
    parser.add_argument("--wait", type=int, nargs="?", const=600, default=None,
                        metavar="TIMEOUT_SECONDS",
                        help="（兼容模式，主要用于 Claude Code/Cursor 等非 Copilot 环境）"
                             "自动启动 GUI 子进程，主进程阻塞轮询结果，打印 JSON 后退出。"
                             "Copilot Chat 请用不带 --wait 的命令（isBackground=true）+ 读 _gui_result.json。默认 600 秒。")
    parser.add_argument("--poll-result", type=int, nargs="?", const=600, default=None,
                        metavar="TIMEOUT_SECONDS",
                        help="（兼容旧流程）轮询 _gui_result.json 并打印，不启动 GUI。")
    parser.add_argument("--skip-cleanup", action="store_true",
                        help="跳过启动时清除 _gui_result.json（由 --wait 模式的子进程使用）")
    args, _ = parser.parse_known_args()

    if args.env:
        global CURRENT_ENV, MODEL_PRESETS, DEFAULT_MODEL
        CURRENT_ENV = args.env
        MODEL_PRESETS = _ENV_MODELS[CURRENT_ENV]
        DEFAULT_MODEL = _ENV_DEFAULT[CURRENT_ENV]

    # ── --wait 模式：阻塞轮询（适用于 Claude Code/Cursor 等跨 turn 不断链的环境） ──
    # 使用方式：.venv\Scripts\python scripts/gui_launcher.py --env claude-code --wait 600
    # Copilot Chat 请直接用不带 --wait 的命令（isBackground=true），用户确认后读 _gui_result.json
    # 进程自动打开 GUI 窗口（子进程），同时阻塞轮询 _gui_result.json，直到用户点确认或超时
    if args.wait is not None:
        import subprocess, time
        env_arg = args.env or CURRENT_ENV
        RESULT_FILE.unlink(missing_ok=True)   # 清除旧结果，确保读到本次的
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--env", env_arg, "--skip-cleanup"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # 立刻向 stdout 打印等待标识——AI 必须看到此行才能确认命令仍在运行
        print(f"GUI_WAITING: 窗口已弹出，等待用户选择（最多 {args.wait} 秒）… 请勿重新运行命令。", flush=True)
        print("GUI_WAITING: 用户在 GUI 界面点击确认后，本行会自动输出 GUI_JSON_RESULT: 开头的 JSON。", flush=True)
        deadline = time.time() + args.wait
        last_heartbeat = time.time()
        while time.time() < deadline:
            if RESULT_FILE.exists() and RESULT_FILE.stat().st_size > 5:
                result_text = RESULT_FILE.read_text(encoding="utf-8")
                print("GUI_JSON_RESULT:")
                print(result_text)
                sys.stdout.flush()
                sys.exit(0)
            # 每 30 秒打印一次心跳，证明进程仍在阻塞等待
            if time.time() - last_heartbeat >= 30:
                elapsed = int(time.time() - (deadline - args.wait))
                remaining = int(deadline - time.time())
                print(f"GUI_WAITING: 已等待 {elapsed}s，剩余 {remaining}s… 请用户在 GUI 中作出选择。", flush=True)
                last_heartbeat = time.time()
            time.sleep(2)
        print("GUI_JSON_RESULT:")
        print(json.dumps({"action": "cancelled", "reason": f"wait timeout after {args.wait}s"},
                         ensure_ascii=False))
        sys.stdout.flush()
        sys.exit(0)

    # ── --poll-result 模式（兼容旧流程，不推荐新用） ────────────────────────────
    if args.poll_result is not None:
        import time
        timeout_s = args.poll_result
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if RESULT_FILE.exists() and RESULT_FILE.stat().st_size > 5:
                print(RESULT_FILE.read_text(encoding="utf-8"))
                sys.stdout.flush()
                sys.exit(0)
            time.sleep(2)
        print(json.dumps({"action": "cancelled", "reason": f"poll-result timeout after {timeout_s}s"},
                         ensure_ascii=False))
        sys.stdout.flush()
        sys.exit(0)

    # 清除上次遗留的结果文件（--skip-cleanup 时跳过，因 --wait 父进程已清除）
    if not args.skip_cleanup:
        RESULT_FILE.unlink(missing_ok=True)

    chapters = scan_chapters()
    if not chapters:
        print(json.dumps({"action": "error", "message": f"未找到视频目录: {VIDEOS_DIR}"}, ensure_ascii=False))
        sys.exit(1)

    app = LauncherApp(chapters)

    # 等待标记输出到 stderr（不干扰 stdout 的 JSON 输出）
    print("# GUI_WAITING: 窗口已弹出，等待用户在 GUI 中选择并点击确认按钮...", file=sys.stderr, flush=True)
    print("# AI: 不要重新运行命令。用户点击按钮后，_gui_result.json 会立即出现；stdout 也会输出 JSON。", file=sys.stderr, flush=True)

    app.mainloop()

    result = app.result or {"action": "cancelled"}
    # 再次写文件（mainloop 正常返回时的保证路径）
    _write_result_file(result)
    # 只有 JSON 进入 stdout（不混入任何其它输出）
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    # GUI 写入 JSON 后立即退出；状态由下次启动时实时扫描 output/ 目录获取


if __name__ == "__main__":
    main()
