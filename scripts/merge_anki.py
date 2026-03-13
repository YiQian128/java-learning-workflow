#!/usr/bin/env python3
"""
merge_anki.py - 合并多个 Anki CSV 文件并生成章节级 .apkg

用法：
  python scripts/merge_anki.py --chapter-dir "portable-gpu-worker/output/Java基础-视频上/day01-Java入门"
  python scripts/merge_anki.py --csvs anki_01.csv anki_07.csv --output CHAPTER_ANKI.csv --apkg CHAPTER_ANKI.apkg
  python scripts/merge_anki.py --chapter-dir ... --deck "Java全栈::Java基础-视频上::day01-Java入门"
"""

import argparse
import csv
import hashlib
import io
import sys
from pathlib import Path


def detect_csv_format(csv_path: Path) -> tuple[str, list[str], dict[str, int]]:
    """
    检测 CSV 的分隔符和列名映射。
    返回 (delimiter, header_names, col_map)
    col_map: {"deck": idx, "type": idx, "tags": idx, "front": idx, "back": idx}
    """
    delimiter = "\t"
    col_map = {"deck": None, "type": None, "tags": None, "front": 0, "back": 1}
    header_row = []

    with open(csv_path, encoding="utf-8", newline="") as f:
        for line in f:
            stripped = line.rstrip("\n")
            if stripped.startswith("#separator:"):
                sep = stripped.split(":", 1)[1].strip().lower()
                if sep in ("comma", ","):
                    delimiter = ","
                elif sep in ("tab", "\t"):
                    delimiter = "\t"
            elif stripped.startswith("#"):
                continue
            else:
                reader = csv.reader(io.StringIO(stripped), delimiter=delimiter)
                row = next(reader)
                lowered = [c.strip().lower() for c in row]
                if "front" in lowered and "back" in lowered:
                    header_row = lowered
                    col_map["front"] = lowered.index("front")
                    col_map["back"] = lowered.index("back")
                    if "deck" in lowered:
                        col_map["deck"] = lowered.index("deck")
                    if "type" in lowered:
                        col_map["type"] = lowered.index("type")
                    if "tags" in lowered:
                        col_map["tags"] = lowered.index("tags")
                break

    return delimiter, header_row, col_map


def read_csv_cards(csv_path: Path) -> list[dict]:
    """读取 CSV 中的所有卡片，返回标准化格式的列表。"""
    delimiter, header_row, col_map = detect_csv_format(csv_path)
    cards = []
    header_skipped = False

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row_num, row in enumerate(reader, 1):
            if not row:
                continue
            if row[0].startswith("#"):
                continue
            # 跳过列头行
            if not header_skipped and col_map["front"] is not None:
                cell = row[col_map["front"]].strip().lower() if len(row) > col_map["front"] else ""
                if cell == "front":
                    header_skipped = True
                    continue

            front_idx = col_map["front"] if col_map["front"] is not None else 0
            back_idx = col_map["back"] if col_map["back"] is not None else 1
            deck_idx = col_map.get("deck")
            type_idx = col_map.get("type")
            tags_idx = col_map.get("tags")

            if len(row) <= max(filter(lambda x: x is not None, [front_idx, back_idx])):
                continue

            front = row[front_idx].strip() if len(row) > front_idx else ""
            back = row[back_idx].strip() if len(row) > back_idx else ""
            deck = row[deck_idx].strip() if deck_idx is not None and len(row) > deck_idx else ""
            card_type = row[type_idx].strip() if type_idx is not None and len(row) > type_idx else "定义"
            tags = row[tags_idx].strip() if tags_idx is not None and len(row) > tags_idx else ""

            if not front or not back:
                continue

            cards.append({
                "front": front,
                "back": back,
                "deck": deck,
                "type": card_type,
                "tags": tags,
                "source_file": str(csv_path)
            })

    return cards


def deduplicate_cards(cards: list[dict]) -> list[dict]:
    """
    去重：正面内容相同的卡片只保留一张（优先保留背面更完整的）。
    使用正面内容的 hash 作为唯一键。
    """
    seen: dict[str, dict] = {}
    for card in cards:
        key = hashlib.md5(card["front"].strip().lower().encode("utf-8")).hexdigest()
        if key not in seen:
            seen[key] = card
        else:
            existing = seen[key]
            # 保留背面更长（内容更完整）的那张
            if len(card["back"]) > len(existing["back"]):
                seen[key] = card

    return list(seen.values())


def scan_chapter_csvs(chapter_dir: Path) -> list[Path]:
    """扫描章节目录下所有视频子目录中的 anki_*.csv（不含 CHAPTER_ 目录）。"""
    found = []
    for video_dir in sorted(chapter_dir.iterdir()):
        if not video_dir.is_dir():
            continue
        if video_dir.name.startswith(("CHAPTER_", "DAY", "_")):
            continue
        for csv_file in sorted(video_dir.glob("anki_*.csv")):
            found.append(csv_file)
    return found


def write_merged_csv(cards: list[dict], output_path: Path, deck_override: str | None = None) -> int:
    """将合并后的卡片写入 CSV 文件，返回写入的卡片数。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write("#separator:Comma\n")
        f.write("#html:true\n")
        f.write("#deck column:1\n")
        f.write("#notetype column:2\n")
        f.write("#tags column:3\n")
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["Deck", "Type", "Tags", "Front", "Back"])
        for card in cards:
            deck = deck_override or card.get("deck", "Java全栈")
            writer.writerow([deck, card["type"], card["tags"], card["front"], card["back"]])
    return len(cards)


def main():
    parser = argparse.ArgumentParser(description="合并多个 Anki CSV 并生成章节级 .apkg")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--chapter-dir", help="章节目录路径（自动扫描所有 anki_*.csv）")
    group.add_argument("--csvs", nargs="+", help="手动指定 CSV 文件列表")
    parser.add_argument("--output", help="合并后 CSV 的输出路径（默认自动命名）")
    parser.add_argument("--apkg", help=".apkg 输出路径（不指定则不生成）")
    parser.add_argument("--deck", help="Anki 牌组名称（覆盖 CSV 中的 Deck 列）")
    parser.add_argument("--no-dedup", action="store_true", help="不去重，保留所有卡片")
    args = parser.parse_args()

    # 收集输入 CSV
    if args.chapter_dir:
        chapter_dir = Path(args.chapter_dir)
        if not chapter_dir.exists():
            print(f"ERROR: Chapter directory not found: {chapter_dir}", file=sys.stderr)
            sys.exit(1)
        input_csvs = scan_chapter_csvs(chapter_dir)
        # 自动命名输出路径
        chapter_name = chapter_dir.name
        synthesis_dir = chapter_dir / f"CHAPTER_SYNTHESIS_{chapter_name}"
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        default_output = synthesis_dir / f"CHAPTER_ANKI_{chapter_name}.csv"
        default_apkg = synthesis_dir / f"CHAPTER_ANKI_{chapter_name}.apkg"
    else:
        input_csvs = [Path(p) for p in args.csvs]
        default_output = Path("merged_anki.csv")
        default_apkg = Path("merged_anki.apkg")

    if not input_csvs:
        print("ERROR: No CSV files found.", file=sys.stderr)
        sys.exit(1)

    output_csv = Path(args.output) if args.output else default_output
    output_apkg = Path(args.apkg) if args.apkg else (default_apkg if args.chapter_dir else None)

    # 读取所有卡片
    all_cards: list[dict] = []
    for csv_path in input_csvs:
        cards = read_csv_cards(csv_path)
        print(f"  {csv_path.name}: {len(cards)} 张卡片")
        all_cards.extend(cards)

    print(f"\n合并前总计：{len(all_cards)} 张")

    # 去重
    if not args.no_dedup:
        all_cards = deduplicate_cards(all_cards)
        print(f"去重后：{len(all_cards)} 张")

    # 写入合并 CSV
    written = write_merged_csv(all_cards, output_csv, deck_override=args.deck)
    print(f"\n已写入合并 CSV：{output_csv}（{written} 张）")

    # 生成 .apkg
    if output_apkg:
        apkg_path = str(output_apkg)
        # 调用 generate_anki.py
        generate_script = Path(__file__).parent / "generate_anki.py"
        if generate_script.exists():
            import subprocess
            import os
            venv_python = Path(__file__).parent.parent / ".venv"
            if os.name == "nt":
                python = venv_python / "Scripts" / "python.exe"
            else:
                python = venv_python / "bin" / "python"
            if not python.exists():
                python = Path(sys.executable)

            result = subprocess.run(
                [str(python), str(generate_script), "--csv", str(output_csv), "--output", apkg_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                print(f"已生成 .apkg：{output_apkg}")
                if result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        print(f"  {line}")
            else:
                print(f"WARNING: .apkg 生成失败: {result.stderr}", file=sys.stderr)
        else:
            print(f"WARNING: 未找到 generate_anki.py，跳过 .apkg 生成", file=sys.stderr)


if __name__ == "__main__":
    main()
