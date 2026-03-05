r"""
write_anki_csv.py --- 将 Anki 卡片数据写入 UTF-8 无 BOM 的 CSV 文件

用途：解决 PowerShell/Windows 内联写入时产生 BOM 导致 generate_anki.py 解析失败的问题。
    AI 生成 CSV 内容后，将卡片数据通过本脚本写入，确保无 BOM。

推荐用法（AI 生成临时脚本）：
    AI 生成 _write_csv_{stem}.py，在脚本顶部直接定义 CARDS 和 OUTPUT，
    然后调用 write_anki_csv.write_csv(OUTPUT, CARDS) 写入，无需 CLI 参数。

    示例模板（_write_csv_demo.py）：
        import sys
        sys.path.insert(0, r"d:\APP\Code\Claude\java-learning-workflow\scripts")
        from write_anki_csv import write_csv

        OUTPUT = r"path\to\anki_demo.csv"
        CARDS = [
            ["什么是 CMD？", "Windows 内置的命令行工具，全称 Command Prompt。", "java::basics::cmd::定义"],
            ["如何打开 CMD？", "Win+R → 输入 cmd → 回车", "java::basics::cmd::操作"],
        ]
        write_csv(OUTPUT, CARDS)

    运行：.venv\Scripts\python _write_csv_demo.py

输出格式（固定）：
    第 1 行: #separator:Comma
    第 2 行: front,back,tags
    第 3 行起: 每行一张卡片（含英文逗号的字段自动加双引号）
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path


def escape_cell(value: str) -> str:
    """强制为含逗号或换行的单元格加双引号（csv.writer 已处理，此函数仅用于手动拼接时）。"""
    if "," in value or "\n" in value or '"' in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def write_csv(output_path: str, cards: list[list[str]]) -> None:
    """
    将卡片列表写入 UTF-8 无 BOM 的 Anki CSV 文件。

    Args:
        output_path: 输出文件路径
        cards: 卡片列表，每个元素为 [front, back, tags]。
               tags 为空字符串时，该列输出为空。
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("#separator:Comma\n")
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["front", "back", "tags"])
        for card in cards:
            if len(card) < 3:
                card = card + [""] * (3 - len(card))
            writer.writerow(card[:3])

    print(f"✅ 写入成功：{path}（{len(cards)} 张卡片）")


def main():
    parser = argparse.ArgumentParser(
        description="将 Anki 卡片写入 UTF-8 无 BOM 的 CSV 文件"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="输出 CSV 文件路径"
    )
    parser.add_argument(
        "--cards", "-c", default=None,
        help='JSON 数组格式的卡片数据，如：\'[["front","back","tag1 tag2"]]\''
    )
    args = parser.parse_args()

    if args.cards:
        # 方式 3：命令行 JSON
        try:
            cards = json.loads(args.cards)
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 方式 1：从 stdin 读取（跳过指令行和列头，只读数据行）
        raw = sys.stdin.read()
        reader = csv.reader(io.StringIO(raw))
        cards = []
        for row in reader:
            if not row:
                continue
            first = row[0].lstrip("\ufeff")  # 防 BOM
            if first.startswith("#") or first == "front":
                continue  # 跳过指令行和列头
            cards.append([first] + row[1:])

    write_csv(args.output, cards)


if __name__ == "__main__":
    main()
