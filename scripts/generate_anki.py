#!/usr/bin/env python3
"""
generate_anki.py - 将 CSV 格式的卡片打包为 .apkg（可直接导入 Anki）
CSV 格式：正面\t背面\t标签（制表符分隔）
"""
import argparse
import csv
import hashlib
import os
import re
import sys
from pathlib import Path


CSS_STYLE = """
.card {
  font-family: 'Noto Sans SC', Arial, sans-serif;
  font-size: 16px;
  text-align: left;
  color: #2c3e50;
  background-color: #fff;
  padding: 20px;
  max-width: 700px;
  margin: 0 auto;
}
.question {
  font-size: 18px;
  font-weight: 600;
  color: #1a252f;
  margin-bottom: 8px;
  line-height: 1.5;
}
.answer {
  font-size: 16px;
  color: #2c3e50;
  line-height: 1.7;
  margin-bottom: 12px;
}
.meta {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #ecf0f1;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.source {
  font-size: 12px;
  color: #7f8c8d;
  background: #ecf0f1;
  padding: 2px 8px;
  border-radius: 10px;
}
.version {
  font-size: 12px;
  color: #2980b9;
  background: #ebf5fb;
  padding: 2px 8px;
  border-radius: 10px;
}
code {
  font-family: 'Fira Code', 'Courier New', monospace;
  background: #f8f9fa;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 14px;
  color: #c0392b;
}
pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  font-family: 'Fira Code', 'Courier New', monospace;
  font-size: 13px;
  overflow-x: auto;
  line-height: 1.5;
  margin: 8px 0;
}
hr {
  border: none;
  border-top: 2px solid #3498db;
  margin: 16px 0;
}
"""


def _detect_csv_format(csv_path: Path):
    """
    Detect CSV separator and column layout from Anki-style header directives.
    Returns (delimiter, col_map) where col_map = {"deck", "front", "back", "tags"} → column index.
    Supports two layouts:
      - Anki extended: Deck,Type,Tags,Front,Back  (with #separator:Comma)
      - Simple legacy:  Front\tBack\tTags         (tab-separated, no header)
    """
    delimiter = "\t"
    col_map = {"front": 0, "back": 1, "tags": 2, "deck": None}

    with open(csv_path, encoding="utf-8", newline="") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#separator:"):
                sep = line.split(":", 1)[1].strip().lower()
                if sep in ("comma", ","):
                    delimiter = ","
                elif sep in ("tab", "\t"):
                    delimiter = "\t"
            elif line.startswith("#"):
                continue  # Other directives, skip
            else:
                # First non-comment line: detect column header if present
                reader = csv.reader([line], delimiter=delimiter)
                headers = [h.strip().lower() for h in next(reader)]
                if "front" in headers and "back" in headers:
                    col_map["front"] = headers.index("front")
                    col_map["back"] = headers.index("back")
                    col_map["tags"] = headers.index("tags") if "tags" in headers else None
                    col_map["deck"] = headers.index("deck") if "deck" in headers else None
                break

    return delimiter, col_map


def generate_apkg(
    csv_path: str,
    output_path: str,
    deck_name: str = "Java 全栈学习",
    images_dir: str = None
) -> int:
    try:
        import genanki
    except ImportError:
        print("ERROR: genanki not installed.", file=sys.stderr)
        print("Run: pip install genanki", file=sys.stderr)
        return 1

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        return 1

    delimiter, col_map = _detect_csv_format(csv_file)

    # Build per-deck structures so one CSV can populate multiple decks
    decks: dict[str, genanki.Deck] = {}
    notes_per_deck: dict[str, list] = {}
    media_files = []
    note_count = 0

    def _get_or_create_deck(name: str) -> genanki.Deck:
        if name not in decks:
            d_id = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
            decks[name] = genanki.Deck(d_id, name)
            notes_per_deck[name] = []
        return decks[name]

    def _make_model(name: str) -> "genanki.Model":
        m_id = int(hashlib.md5((name + "_model_v2").encode()).hexdigest()[:8], 16)
        return genanki.Model(
            m_id,
            "Java学习卡片",
            fields=[
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Source"},
                {"name": "JavaVersion"},
            ],
            templates=[
                {
                    "name": "Java Card",
                    "qfmt": '<div class="card-front"><div class="question">{{Front}}</div></div>',
                    "afmt": (
                        "{{FrontSide}}<hr id=answer>"
                        '<div class="card-back"><div class="answer">{{Back}}</div>'
                        '<div class="meta">'
                        "{{#Source}}<span class=\"source\">📚 {{Source}}</span>{{/Source}}"
                        "{{#JavaVersion}}<span class=\"version\">☕ {{JavaVersion}}</span>{{/JavaVersion}}"
                        "</div></div>"
                    ),
                }
            ],
            css=CSS_STYLE,
        )

    # Parse CSV — skip Anki directive lines and the header row
    header_skipped = False
    with open(csv_file, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row_num, row in enumerate(reader, 1):
            if not row:
                continue
            if row[0].startswith("#"):
                continue  # Anki directive line
            # Skip the column-header row (contains "Front", "Back", etc.)
            if not header_skipped and col_map["front"] is not None:
                cell = row[col_map["front"]].strip().lower() if len(row) > col_map["front"] else ""
                if cell == "front":
                    header_skipped = True
                    continue

            front_idx = col_map["front"] if col_map["front"] is not None else 0
            back_idx = col_map["back"] if col_map["back"] is not None else 1
            tags_idx = col_map["tags"]
            deck_idx = col_map["deck"]

            if len(row) <= max(front_idx, back_idx):
                print(f"  Warning: Row {row_num} has too few columns, skipping")
                continue

            front = row[front_idx].strip()
            back = row[back_idx].strip()
            if not front or not back:
                print(f"  Warning: Row {row_num} has empty front or back, skipping")
                continue

            tags_raw = row[tags_idx].strip() if tags_idx is not None and len(row) > tags_idx else ""
            row_deck = row[deck_idx].strip() if deck_idx is not None and len(row) > deck_idx else deck_name
            if not row_deck:
                row_deck = deck_name

            _get_or_create_deck(row_deck)

            # Extract source and version from back content
            source = ""
            java_version = ""
            if "来源：" in back:
                src_part = back.split("来源：", 1)[1].split("。")[0].split("\n")[0]
                source = src_part[:50]
            for v in ["Java 21", "Java 17", "Java 11", "Java 8"]:
                if v in back:
                    java_version = v + "+"
                    break

            tags = [t.replace(" ", "_") for t in tags_raw.split() if t]
            model = _make_model(row_deck)
            note = genanki.Note(model=model, fields=[front, back, source, java_version], tags=tags)
            decks[row_deck].add_note(note)
            note_count += 1

            if images_dir:
                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', back)
                imgs += re.findall(r'!\[[^\]]*\]\(([^)]+)\)', back)
                for img in imgs:
                    img_path = Path(images_dir) / img
                    if img_path.exists():
                        media_files.append(str(img_path))

    # Write package — one .apkg contains all decks
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    all_decks = list(decks.values())
    if not all_decks:
        # No data: create an empty placeholder deck
        fallback_id = int(hashlib.md5(deck_name.encode()).hexdigest()[:8], 16)
        all_decks = [genanki.Deck(fallback_id, deck_name)]

    package = genanki.Package(all_decks)
    if media_files:
        package.media_files = list(set(media_files))
        print(f"  Including {len(package.media_files)} media files")

    package.write_to_file(str(out))
    print(f"Anki package created: {out}")
    print(f"  Cards: {note_count}")
    print(f"  Decks ({len(decks)}): {', '.join(decks.keys()) or deck_name}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="CSV → Anki .apkg 打包工具")
    parser.add_argument("--csv", required=True, help="CSV 文件路径（制表符分隔）")
    parser.add_argument("--output", required=True, help=".apkg 输出路径")
    parser.add_argument("--deck", default="Java 全栈学习", help="Anki 牌组名称")
    parser.add_argument("--images-dir", help="卡片中引用的图片所在目录")
    args = parser.parse_args()

    sys.exit(generate_apkg(args.csv, args.output, args.deck, args.images_dir))


if __name__ == "__main__":
    main()
