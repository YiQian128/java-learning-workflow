#!/usr/bin/env python3
"""
estimate_cost.py - 转写 API 费用估算工具

扫描 videos/ 目录，统计待处理视频总时长，按所有支持的 API 提供商给出精确报价对比。
自动读取 config/config.yaml 中当前配置的提供商并高亮显示。
自动跳过已完成预处理（存在 SRT 文件）的视频。

用法：
  python scripts/estimate_cost.py          # 估算全部待处理视频
  python scripts/estimate_cost.py --all    # 包含已处理视频一并估算
  python scripts/estimate_cost.py --dir "day01-Java入门"  # 仅估算指定目录
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # portable-gpu-worker/
VIDEOS_DIR   = ROOT / "videos"
OUTPUT_DIR   = ROOT / "output"
CONFIG_PATH  = ROOT / "config" / "config.yaml"
FFMPEG_BIN   = ROOT / "_env" / "ffmpeg" / "bin"

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".ts"}

# 参考汇率（人民币/美元），仅供估算
CNY_PER_USD = 7.30

# ─── 各提供商定价表（截至 2026 年初，仅供参考，以各官方页面为准） ─────────────
# price_usd_min    : 美元/分钟；price_cny_min : 人民币/分钟（二选一）
# timestamps       : 是否返回时间戳（段落级或词级）
# is_free          : 完全免费（不受用量限制）
# free_monthly_min : 每月免费额度（分钟），超出后按单价计费
PROVIDERS: list[dict] = [
    # ── 完全免费 ──────────────────────────────────────────────────────────────
    {
        "id":              "siliconflow",
        "display":         "SiliconFlow",
        "model":           "SenseVoiceSmall",
        "model_key":       "FunAudioLLM/SenseVoiceSmall",
        "provider_key":    "siliconflow",
        "price_cny_min":   0.0,
        "price_usd_min":   None,
        "is_free":         True,
        "timestamps":      False,
        "free_monthly_min": None,
        "tag":             "中文最佳，无时间戳，目前完全免费",
        "zh_quality":      "★★★★★",
        "url":             "https://siliconflow.cn/pricing",
    },
    # ── 国内云厂商（中文专项） ─────────────────────────────────────────────────
    {
        "id":              "aliyun_paraformer",
        "display":         "阿里云",
        "model":           "paraformer-v2",
        "model_key":       "paraformer-realtime-v2",
        "provider_key":    "aliyun",
        "price_cny_min":   0.288 / 60,   # ¥0.288/小时 = ¥0.0048/分钟；仅对语音内容计费
        "price_usd_min":   None,
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": 600,         # 每月免费 10 小时（主账号）
        "tag":             "中文专项，仅语音内容计费，词级时间戳，10h/月免费",
        "zh_quality":      "★★★★★",
        "url":             "https://help.aliyun.com/zh/isi/developer-reference/metering-and-billing",
    },
    # ── 国际云服务（Whisper 系） ───────────────────────────────────────────────
    {
        "id":              "groq_turbo",
        "display":         "Groq",
        "model":           "whisper-large-v3-turbo",
        "model_key":       "whisper-large-v3-turbo",
        "provider_key":    "groq",
        "price_cny_min":   None,
        "price_usd_min":   0.04 / 60,    # $0.04/小时，最低计费 10s/请求
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "rate_limit_asd":  28800,        # 速率上限：28800 音频秒/天 = 480 分钟/天
        "tag":             "228x 实时速度，段落时间戳，最低计费 10s/请求，上限 480min/天",
        "zh_quality":      "★★★☆☆",
        "url":             "https://groq.com/pricing/",
    },
    {
        "id":              "groq_large",
        "display":         "Groq",
        "model":           "whisper-large-v3",
        "model_key":       "whisper-large-v3",
        "provider_key":    "groq",
        "price_cny_min":   None,
        "price_usd_min":   0.111 / 60,   # $0.111/小时，最低计费 10s/请求
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "rate_limit_asd":  28800,
        "tag":             "217x 实时速度，质量更高，上限 480min/天",
        "zh_quality":      "★★★★☆",
        "url":             "https://groq.com/pricing/",
    },
    {
        "id":              "openai_whisper1",
        "display":         "OpenAI",
        "model":           "whisper-1",
        "model_key":       "whisper-1",
        "provider_key":    "openai",
        "price_cny_min":   None,
        "price_usd_min":   0.006,        # $0.006/分钟
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "tag":             "稳定，词级+段落时间戳",
        "zh_quality":      "★★★☆☆",
        "url":             "https://openai.com/api/pricing/",
    },
    {
        "id":              "openai_gpt4o",
        "display":         "OpenAI",
        "model":           "gpt-4o-transcribe",
        "model_key":       "gpt-4o-transcribe",
        "provider_key":    "openai",
        "price_cny_min":   None,
        "price_usd_min":   0.006,
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "tag":             "更高准确率，同价格",
        "zh_quality":      "★★★★☆",
        "url":             "https://openai.com/api/pricing/",
    },
    {
        "id":              "deepgram_nova3",
        "display":         "Deepgram",
        "model":           "nova-3",
        "model_key":       "nova-3",
        "provider_key":    "deepgram",
        "price_cny_min":   None,
        "price_usd_min":   0.0043,       # $0.0043/分钟
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "tag":             "低延迟，词级时间戳",
        "zh_quality":      "★★★☆☆",
        "url":             "https://deepgram.com/pricing",
    },
    {
        "id":              "assemblyai_nano",
        "display":         "AssemblyAI",
        "model":           "nano",
        "model_key":       "nano",
        "provider_key":    "assemblyai",
        "price_cny_min":   None,
        "price_usd_min":   0.002,        # $0.002/分钟
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "tag":             "经济型，词级时间戳",
        "zh_quality":      "★★☆☆☆",
        "url":             "https://www.assemblyai.com/pricing",
    },
    {
        "id":              "assemblyai_best",
        "display":         "AssemblyAI",
        "model":           "best",
        "model_key":       "best",
        "provider_key":    "assemblyai",
        "price_cny_min":   None,
        "price_usd_min":   0.0062,       # $0.0062/分钟
        "is_free":         False,
        "timestamps":      True,
        "free_monthly_min": None,
        "tag":             "高准确率，说话人分离，词级时间戳",
        "zh_quality":      "★★★☆☆",
        "url":             "https://www.assemblyai.com/pricing",
    },
]


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _ensure_utf8() -> None:
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _setup_ffmpeg_path() -> None:
    """将便携 ffmpeg 注入 PATH，使 ffprobe 可用。"""
    if FFMPEG_BIN.exists():
        os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")


def _safe_stem(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')


def load_config() -> dict:
    try:
        import yaml  # type: ignore
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_duration(path: Path) -> float:
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def fmt_dur(s: float) -> str:
    h, m = int(s // 3600), int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def srt_exists(video: Path) -> bool:
    """检查该视频是否已有预处理产物（SRT 文件）。"""
    try:
        rel = video.parent.relative_to(VIDEOS_DIR)
    except ValueError:
        rel = Path(".")
    parts = [_safe_stem(p) for p in rel.parts if p != "."]
    prefix = OUTPUT_DIR
    for p in parts:
        prefix = prefix / p
    srt = prefix / _safe_stem(video.stem) / "_preprocessing" / f"{_safe_stem(video.stem)}.srt"
    return srt.exists()


def calc_cost(provider: dict, total_min: float) -> tuple[float | None, float | None]:
    """返回 (usd, cny)，已扣除月免费额度；None 表示该货币不直接适用。"""
    free_min = provider.get("free_monthly_min") or 0.0
    billable_min = max(0.0, total_min - free_min)

    if provider["price_usd_min"] is not None:
        usd = provider["price_usd_min"] * billable_min
        cny = usd * CNY_PER_USD
        return usd, cny
    if provider["price_cny_min"] is not None:
        cny = provider["price_cny_min"] * billable_min
        usd = cny / CNY_PER_USD
        return usd, cny
    return None, None


# ─── 主逻辑 ───────────────────────────────────────────────────────────────────

def main() -> None:
    _ensure_utf8()
    _setup_ffmpeg_path()

    import argparse
    parser = argparse.ArgumentParser(description="转写 API 费用估算工具")
    parser.add_argument("--all",  action="store_true", help="包含已处理视频一并统计")
    parser.add_argument("--dir",  default="", help="仅统计指定子目录（支持模糊匹配，如 day01）")
    parser.add_argument("--no-scan", action="store_true",
                        help="跳过时长扫描（仅显示价格表），适合快速查看")
    args = parser.parse_args()

    config = load_config()
    api_cfg = config.get("api", {})
    cur_provider = api_cfg.get("provider", "openai")
    cur_model    = api_cfg.get("model", "")

    W = 78

    print("=" * W)
    print("  便携式 GPU 预处理包 · 转写 API 费用估算")
    print("=" * W)

    # ── 当前配置 ──────────────────────────────────────────────────────────────
    print(f"\n【当前配置】")
    print(f"  provider : {cur_provider}")
    print(f"  model    : {cur_model or '(使用提供商默认值)'}")
    api_enabled = api_cfg.get("enabled", False)
    print(f"  enabled  : {api_enabled}")

    # ── 扫描视频 ─────────────────────────────────────────────────────────────
    if not VIDEOS_DIR.exists():
        print(f"\n错误: videos/ 目录不存在 ({VIDEOS_DIR})")
        sys.exit(1)

    all_videos: list[Path] = sorted(
        f for f in VIDEOS_DIR.rglob("*")
        if f.suffix.lower() in VIDEO_EXTENSIONS and not f.name.startswith(".")
    )

    if args.dir:
        kw = args.dir.lower()
        all_videos = [v for v in all_videos if kw in str(v).lower()]

    if not all_videos:
        print(f"\n未在 videos/ 中找到视频文件。")
        return

    done_videos    = [v for v in all_videos if srt_exists(v)]
    pending_videos = [v for v in all_videos if not srt_exists(v)]

    print(f"\n【视频扫描结果】")
    print(f"  总计    : {len(all_videos)} 个")
    print(f"  已处理  : {len(done_videos)} 个（SRT 已存在，将跳过）")
    print(f"  待处理  : {len(pending_videos)} 个")

    target = all_videos if args.all else pending_videos
    target_label = "全部视频" if args.all else "待处理视频"

    if not target:
        print(f"\n所有视频均已完成预处理，无需估算费用。")
        print(f"若要重新估算全部视频，请使用 --all 参数。")
        return

    # ── 按目录分组 ────────────────────────────────────────────────────────────
    dir_groups: dict[str, list[Path]] = {}
    for v in target:
        try:
            rel = v.parent.relative_to(VIDEOS_DIR)
        except ValueError:
            rel = Path(".")
        top = rel.parts[0] if rel.parts and rel.parts[0] != "." else "(根目录)"
        dir_groups.setdefault(top, []).append(v)

    # ── 时长扫描 ──────────────────────────────────────────────────────────────
    print(f"\n【时长扫描】正在读取 {len(target)} 个{target_label}的时长...")
    print(f"  (ffprobe 路径: {FFMPEG_BIN / 'ffprobe.exe' if platform.system() == 'Windows' else FFMPEG_BIN / 'ffprobe'})")

    if args.no_scan:
        print("  已跳过（--no-scan）。以下费用基于预估值，不准确。")
        total_sec = len(target) * 600.0   # 假设每个 10 分钟
    else:
        total_sec = 0.0
        dir_durations: dict[str, float] = {}
        failed = 0

        for i, v in enumerate(target, 1):
            dur = get_duration(v)
            if dur <= 0:
                failed += 1
            total_sec += dur
            try:
                rel = v.parent.relative_to(VIDEOS_DIR)
            except ValueError:
                rel = Path(".")
            top = rel.parts[0] if rel.parts and rel.parts[0] != "." else "(根目录)"
            dir_durations[top] = dir_durations.get(top, 0.0) + dur

            # 进度
            pct = i / len(target) * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"  [{bar}] {pct:5.1f}%  {i}/{len(target)}", end="\r", flush=True)

        print(f"  扫描完成{' ' * 40}")
        if failed:
            print(f"  警告: {failed} 个视频无法读取时长（已按 0 计入）")

    total_min  = total_sec / 60
    total_hour = total_sec / 3600

    print(f"\n  总时长  : {fmt_dur(total_sec)}")
    print(f"  合计    : {total_min:.1f} 分钟 / {total_hour:.2f} 小时")

    # ── 按目录明细 ───────────────────────────────────────────────────────────
    if not args.no_scan and len(dir_groups) > 1:
        print(f"\n【目录时长明细】")
        col_w = max(len(k) for k in dir_durations) + 2
        print(f"  {'目录':<{col_w}}  {'视频数':>5}  {'时长':>10}  {'完成':>4}")
        print(f"  {'-' * col_w}  {'-----':>5}  {'----------':>10}  {'----':>4}")
        for dname, dur in sorted(dir_durations.items()):
            n_done = sum(1 for v in dir_groups.get(dname, []) if srt_exists(v)) if args.all \
                     else 0  # pending 模式时全为未完成
            n_total = len(dir_groups.get(dname, []))
            done_str = f"{n_done}/{n_total}" if args.all else f"0/{n_total}"
            print(f"  {dname:<{col_w}}  {n_total:>5}  {fmt_dur(dur):>10}  {done_str:>4}")

    # ── 费用对比表 ────────────────────────────────────────────────────────────
    W = 78
    print(f"\n{'=' * W}")
    print(f"  {target_label} · API 转写费用对比（参考汇率 1 USD ≈ {CNY_PER_USD} CNY）")
    print(f"{'=' * W}")

    # 计算每个提供商的费用
    rows: list[dict] = []
    for p in PROVIDERS:
        usd, cny = calc_cost(p, total_min)
        is_current = (p["provider_key"] == cur_provider and
                      (not cur_model or cur_model == p["model_key"] or
                       cur_model == p["model"]))
        rows.append({**p, "usd": usd, "cny": cny, "is_current": is_current})

    # 排序：完全免费 > 按人民币费用升序
    rows.sort(key=lambda r: (-int(r.get("is_free", False)), r["cny"] if r["cny"] is not None else 9999))

    # 表头
    print(f"\n  {'#':>2}  {'提供商':<8} {'模型':<28} {'中文':^5} {'时间戳':^4}  {'费用（CNY）':>10}  {'费用（USD）':>10}  {'免费额度'}")
    print(f"  {'--':>2}  {'-'*8} {'-'*28} {'-'*5} {'-'*4}  {'-'*10}  {'-'*10}  {'-'*12}")

    for i, r in enumerate(rows, 1):
        ts_mark  = "✓" if r["timestamps"] else "✗"
        cur_mark = " ◀ 当前" if r["is_current"] else ""
        zh_q     = r.get("zh_quality", "")
        free_tag = ""

        if r.get("is_free"):
            cny_str = "★ 完全免费"
            usd_str = "★ 完全免费"
        else:
            free_min = r.get("free_monthly_min") or 0
            if free_min > 0:
                free_tag = f"{free_min//60}h/月"
                # 显示超出免费额度后的费用（若总量 > 免费额度）
                if total_min > free_min:
                    usd, cny = r["usd"], r["cny"]
                    cny_str = f"¥{cny:.2f}" if cny is not None else "—"
                    usd_str = f"${usd:.2f}" if usd is not None else "—"
                else:
                    cny_str = "在免费额度内"
                    usd_str = "在免费额度内"
            else:
                cny_str = f"¥{r['cny']:.2f}" if r["cny"] is not None else "—"
                usd_str = f"${r['usd']:.2f}" if r["usd"] is not None else "—"

        prefix = f"  {i:>2}  " if not r.get("is_free") else f"  {i:>2}★ "
        print(f"{prefix}{r['display']:<8} {r['model']:<28} {zh_q:^5} {ts_mark:^4}  "
              f"{cny_str:>10}  {usd_str:>10}  {free_tag}{cur_mark}")

    # ── 推荐方案 ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * W}")
    print(f"  推荐方案（针对中文 Java 教程视频）")
    print(f"{'=' * W}")

    aliyun_free_min = 600
    if total_min <= aliyun_free_min:
        aliyun_cost_note = f"总时长 {total_min:.0f}min ≤ 免费额度 {aliyun_free_min}min，本次完全免费"
    else:
        exceed = total_min - aliyun_free_min
        cny_exceed = exceed * (0.288 / 60)
        aliyun_cost_note = f"超出免费 {exceed:.0f}min，追加费用约 ¥{cny_exceed:.2f}"

    groq_row = next(r for r in rows if r["id"] == "groq_turbo")
    groq_cny = groq_row["cny"] or 0.0
    sf_row   = next(r for r in rows if r["id"] == "siliconflow")

    print(f"""
  ┌─ 方案 A（零成本，中文最佳）─────────────────────────────────────────────┐
  │  提供商 : SiliconFlow · FunAudioLLM/SenseVoiceSmall                     │
  │  费用   : ★ 完全免费                                                    │
  │  优点   : 中文识别质量最高，专为普通话 / 方言设计，无需担心计费            │
  │  缺点   : ✗ 无时间戳，Anki 卡片无法精确定位视频时间点                    │
  │  适合   : 以文字内容为主、不需要视频跳转的学习场景                         │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─ 方案 B（低成本，时间戳+中文专项）★ 综合最优 ────────────────────────────┐
  │  提供商 : 阿里云 · paraformer-v2 / paraformer-realtime-v2               │
  │  费用   : 每月 10h 完全免费，超出 ¥0.288/h；{aliyun_cost_note[:50]}  │
  │  优点   : ✓ 词级时间戳；中文/方言专项模型，质量极高；仅语音内容计费       │
  │  缺点   : 需配置 OSS 凭证（见 config/config.yaml → api.aliyun_oss）      │
  │  适合   : 既要高质量中文识别，又要时间戳定位的场景                         │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─ 方案 C（当日完成，有时间戳）──────────────────────────────────────────┐
  │  提供商 : Groq · whisper-large-v3-turbo                                 │
  │  费用   : ¥{groq_cny:.2f}（全部视频）                                       │
  │  优点   : ✓ 段落时间戳；228x 实时速度；OpenAI 兼容 API，当前已支持        │
  │  缺点   : 无中文专项优化；速率上限 480min/天；无免费额度                   │
  │  适合   : 急需时间戳、不在意中文准确率小幅损失的场景                        │
  └─────────────────────────────────────────────────────────────────────────┘

  【当前建议】
  · 零成本/无时间戳 → 切换 SiliconFlow（方案 A），config 填 siliconflow
  · 最优长期（已配置）→ 阿里云 Paraformer（方案 B），每月 10h 免费，词级时间戳
  · 快速完成全部 → 切换 Groq turbo（方案 C），约 ¥{groq_cny:.0f} 一次搞定，config 填 groq""")

    # ── Groq 速率限制说明 ─────────────────────────────────────────────────────
    asd_min = groq_row.get("rate_limit_asd", 28800) // 60
    if total_min > 0:
        days_at_limit = total_min / asd_min
        print(f"\n【Groq 速率限制说明】")
        print(f"  计费        : 按量，$0.04/小时，最低计费 10 秒/请求")
        print(f"  每日上限    : {asd_min} 分钟/天（= 28,800 音频秒）")
        if days_at_limit < 1:
            print(f"  耗时估算    : 单日内可完成全部（总 {total_min:.0f}min ≤ {asd_min}min/天）")
        else:
            print(f"  耗时估算    : 满速约需 {days_at_limit:.1f} 天完成")
        print(f"  全部费用    : ${groq_row['usd']:.2f} ≈ ¥{groq_cny:.2f}")

    # ── 本地模型提示 ─────────────────────────────────────────────────────────
    print(f"\n【本地模型（完全免费 + 完整时间戳）】")
    print(f"  faster-whisper medium   - 推荐，中文质量好，段落+词级时间戳")
    print(f"  faster-whisper large-v3 - 最高质量，需 6GB+ 显存")
    print(f"  运行 0_开始使用.bat → [3] 开始预处理，选择本地模型")

    # ── 注意事项 ──────────────────────────────────────────────────────────────
    print(f"\n【注意事项】")
    print(f"  · 价格截至 2026 年初，以各官方页面为准（URL 见下方）")
    print(f"  · 汇率为参考值（1 USD = {CNY_PER_USD} CNY），实际以付款时为准")
    print(f"  · 阿里云 Paraformer 仅对语音内容计费，静音部分不收费，实际费用更低")
    print(f"  · SiliconFlow 无时间戳，但识别文字质量在国产模型中最优")
    print(f"  · 带 ✓ 时间戳的服务支持 Anki 卡片精确跳转到视频时间点")
    print(f"\n  定价参考页面：")
    seen_urls: set[str] = set()
    for p in PROVIDERS:
        if p["url"] not in seen_urls:
            print(f"    {p['display']:<12} {p['url']}")
            seen_urls.add(p["url"])
    print(f"    {'Groq 限速':<12} https://console.groq.com/docs/rate-limits")

    print(f"\n{'=' * W}")
    print(f"  提示：切换提供商请编辑 config/config.yaml 的 api.provider 字段")
    print(f"{'=' * W}")


if __name__ == "__main__":
    main()
