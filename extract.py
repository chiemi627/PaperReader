#!/usr/bin/env python3
"""
論文PDFから読み上げ用のテキストを抽出するスクリプト

使い方:
    python extract.py input.pdf [-o output.txt] [--keep-refs] [--lang ja|en|auto]

主な処理:
1. PyMuPDF で本文を抽出（2段組対応のためブロック順を y, x でソート）
2. ヘッダー・フッター（ページ番号・誌名等）を除去
3. 行末ハイフネーション結合（英語論文用）
4. 引用番号 [1], [2,3], (Smith 2020) 等を削除
5. 図表キャプション (Figure 1, 図 1, Table 2 等で始まる段落) を除去
6. 参考文献セクション以降を切り落とし
7. 数式記号の多い行を除去
"""

import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF


# --- Cleaning patterns ----------------------------------------------------

# 参考文献セクションの開始を示す見出し（日英）
REFERENCE_HEADERS = re.compile(
    r"^\s*(references?|bibliography|works?\s+cited|参考文献|引用文献|文\s*献)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# 図表キャプションの開始パターン
CAPTION_START = re.compile(
    r"^\s*("
    r"fig(?:ure)?\.?\s*\d+"
    r"|table\s*\d+"
    r"|図\s*\d+"
    r"|表\s*\d+"
    r"|Algorithm\s*\d+"
    r")[\.\:\s]",
    re.IGNORECASE,
)

# 引用パターン
CITATION_BRACKET = re.compile(r"\[\s*\d+(?:\s*[,\-–]\s*\d+)*\s*\]")  # [1], [1, 2], [1-3]
# (Smith et al., 2020), (Smith, 2020), (Smith and Jones, 2020), (Smith 2020; Jones 2021) など
CITATION_AUTHOR_YEAR = re.compile(
    r"\([^()]*?\b\d{4}[a-z]?\b[^()]*?\)"
)

# 行末ハイフネーション（develop-\nment → development、UN-\nDERSTANDING → UNDERSTANDING）
HYPHEN_BREAK = re.compile(r"([A-Za-z])-\s*\n\s*([A-Za-z])")

# 大文字→大文字小文字混合 / 小文字→大文字 の境界（タイトル末尾と著者名の境界等）
CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z][a-z])")
CAPS_BOUNDARY = re.compile(r"([A-Z]{2,})([A-Z][a-z])")

# URL と DOI（読み上げに不向き）
URL_PATTERN = re.compile(r"https?://\S+|doi:\s*\S+", re.IGNORECASE)

# 数式記号が多い行（記号比率で判定）
MATH_CHARS = set("∑∫∂∇√≤≥≠≈±∈∉⊂⊃∪∩∀∃→←↔⇒⇔αβγδεζηθικλμνξπρστυφχψω")

# 著者ブロックの判定材料
AUTHOR_KEYWORDS = re.compile(
    r"\b(authors?|affiliations?|department|university|institute|laboratory|"
    r"college|school\s+of|graduate|orcid|correspond)\b",
    re.IGNORECASE,
)
AUTHOR_EMAIL = re.compile(r"\S+@\S+\.\S+")
AUTHOR_SUPERSCRIPT = re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰†‡§¶]")
# 姓+名 のカンマ区切り列挙: "John Smith, Jane Doe, ..."
AUTHOR_NAME_LIST = re.compile(
    r"[A-Z][a-zA-Z\-']+\s+[A-Z][a-zA-Z\-']+\s*(?:,\s*(?:and\s+)?[A-Z][a-zA-Z\-']+\s+[A-Z][a-zA-Z\-']+){1,}"
)

# Abstract セクションの見出し（日英）
ABSTRACT_HEADER_PATTERN = re.compile(
    r"^\s*(abstract|概\s*要|要\s*約|要\s*旨)\s*[\.\:：]?\s*$",
    re.IGNORECASE,
)

# 既知のセクション見出し（数字なしでも検出する）
KNOWN_SECTIONS_EN = {
    "abstract", "introduction", "background", "motivation",
    "related work", "related works", "previous work", "prior work",
    "method", "methods", "methodology", "approach", "proposed method",
    "proposed approach", "system overview", "model", "architecture",
    "experiments", "experimental setup", "experimental design",
    "experimental results", "evaluation", "results", "analysis",
    "discussion", "limitations", "future work",
    "conclusion", "conclusions", "concluding remarks",
    "acknowledgment", "acknowledgments", "acknowledgements",
}
KNOWN_SECTIONS_JA = {
    "概要", "要約", "要旨",
    "はじめに", "緒言", "序論", "背景",
    "関連研究", "関連する研究", "従来研究", "従来の研究",
    "提案手法", "手法", "提案", "提案方式", "提案システム",
    "実験", "実験設定", "実験方法", "評価実験", "評価",
    "結果", "実験結果", "考察", "議論",
    "結論", "おわりに", "むすび", "まとめ", "謝辞",
}

# 番号付きセクション見出し: "1. Introduction", "2 Related Work", "1.1 Setup" (1.1 等は下位)
NUMBERED_SECTION = re.compile(
    r"^\s*(\d+)(?:\.0)?\.?\s+([A-Za-z一-龯ぁ-んァ-ヶ][^\n]{1,60})\s*$"
)


def extract_blocks(pdf_path: Path) -> tuple[list[str], list[str]]:
    """PyMuPDF で各ページからテキストブロックを抽出.

    Returns:
        (本文ブロック列, 位置で検出したヘッダー/フッター候補列)
    """
    doc = fitz.open(pdf_path)
    all_blocks: list[str] = []
    header_footer_candidates: list[str] = []

    for page in doc:
        width = page.rect.width
        height = page.rect.height
        mid_x = width / 2
        # ヘッダー領域: 上 8%、フッター領域: 下 8%
        header_y = height * 0.08
        footer_y = height * 0.92

        blocks = page.get_text("blocks")
        text_blocks = [b for b in blocks if b[6] == 0]

        # 位置によるヘッダー・フッター分離
        body_blocks = []
        for b in text_blocks:
            y0, y1 = b[1], b[3]
            text = b[4].strip()
            if not text:
                continue
            # 短い行 & 上下端 → ヘッダー/フッター候補
            if len(text) < 100 and "\n" not in text and (y1 < header_y or y0 > footer_y):
                header_footer_candidates.append(text)
                continue
            body_blocks.append(b)

        # 2段組判定（本文ブロックのみで）
        left_blocks = [b for b in body_blocks if b[2] < mid_x + 20]
        right_blocks = [b for b in body_blocks if b[0] > mid_x - 20]
        is_two_column = len(left_blocks) >= 2 and len(right_blocks) >= 2

        if is_two_column:
            left_blocks.sort(key=lambda b: b[1])
            right_blocks.sort(key=lambda b: b[1])
            ordered = left_blocks + right_blocks
        else:
            ordered = sorted(body_blocks, key=lambda b: (b[1], b[0]))

        for b in ordered:
            text = b[4].strip()
            if text:
                all_blocks.append(text)

    doc.close()
    return all_blocks, header_footer_candidates


def looks_like_math(line: str) -> bool:
    """記号比率が高い行を数式と判定."""
    if len(line) < 5:
        return False
    math_count = sum(1 for ch in line if ch in MATH_CHARS)
    nonalpha = sum(1 for ch in line if not ch.isalnum() and not ch.isspace())
    if math_count >= 2:
        return True
    if len(line) < 60 and nonalpha / len(line) > 0.4:
        return True
    return False


def is_author_block(text: str) -> bool:
    """著者ブロックの可能性が高いか判定."""
    if AUTHOR_KEYWORDS.search(text):
        return True
    if AUTHOR_EMAIL.search(text):
        return True
    if AUTHOR_SUPERSCRIPT.search(text):
        return True
    if AUTHOR_NAME_LIST.search(text):
        return True
    return False


def find_abstract_index(blocks: list[str]) -> int:
    """Abstract 見出しを含むブロックの index を返す. 見つからなければ -1."""
    for i, block in enumerate(blocks):
        first_line = block.strip().split("\n")[0].strip()
        if ABSTRACT_HEADER_PATTERN.match(first_line):
            return i
    return -1


def drop_authors(blocks: list[str]) -> list[str]:
    """Abstract までの著者ブロックを除去し、タイトルだけ残す."""
    abstract_idx = find_abstract_index(blocks)
    if abstract_idx < 0:
        return blocks  # Abstract が見つからない → 何もしない

    # タイトル候補: Abstract より前で、著者っぽくないブロック
    title_blocks = []
    for i in range(abstract_idx):
        if is_author_block(blocks[i]):
            break  # 著者ブロックが出てきたら、それ以降は捨てる
        title_blocks.append(blocks[i])

    return title_blocks + blocks[abstract_idx:]


def normalize_section_name(raw: str) -> str:
    """セクション名をファイル名に使える形に正規化."""
    s = raw.strip().lower().rstrip(".:：")
    # 句読点を _ に
    s = re.sub(r"[\s\-/\\]+", "_", s)
    s = re.sub(r"[^\w一-龯ぁ-んァ-ヶ]+", "", s)
    return s or "section"


def detect_section_header(line: str) -> tuple[bool, str]:
    """1行が（トップレベルの）セクション見出しかを判定.

    Returns:
        (見出しか, 正規化された名前)
    """
    s = line.strip()
    if not s or len(s) > 80:
        return False, ""

    # 番号付き: "1. Introduction", "3 Method"
    m = NUMBERED_SECTION.match(s)
    if m:
        title = m.group(2).strip()
        return True, normalize_section_name(title)

    # 番号なし: Abstract / Introduction / 概要 / はじめに ...
    lower = s.lower().rstrip(".:：")
    if lower in KNOWN_SECTIONS_EN:
        return True, normalize_section_name(s)
    if s.rstrip(".:：") in KNOWN_SECTIONS_JA:
        return True, normalize_section_name(s)

    return False, ""


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """クリーンなテキストをセクションに分割.

    Returns:
        [(section_name, section_content), ...]
        最初の要素はタイトル ("title", タイトル文字列)
    """
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_name = "title"
    current_lines: list[str] = []

    for line in lines:
        is_header, name = detect_section_header(line)
        if is_header:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append((current_name, content))
            current_name = name
            current_lines = []
            # 見出し自体は本文に含めない
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()
    if content:
        sections.append((current_name, content))

    return sections


def clean_text(
    blocks: list[str],
    header_candidates: list[str],
    keep_refs: bool = False,
    keep_authors: bool = False,
) -> str:
    """ブロック列に対してクリーニング処理を適用."""
    # 図表キャプション除去
    blocks = [b for b in blocks if not CAPTION_START.match(b.strip())]

    # 著者ブロック除去（タイトル → Abstract に飛ばす）
    if not keep_authors:
        blocks = drop_authors(blocks)

    # 結合
    full = "\n\n".join(blocks)

    # 参考文献以降を切り落とし
    if not keep_refs:
        match = REFERENCE_HEADERS.search(full)
        if match:
            full = full[: match.start()]

    # ハイフネーション結合
    full = HYPHEN_BREAK.sub(r"\1\2", full)

    # 単語境界の修復: "SCALEZecheng" → "SCALE Zecheng", "fooBar" → "foo Bar"
    full = CAPS_BOUNDARY.sub(r"\1 \2", full)
    full = CAMEL_BOUNDARY.sub(r"\1 \2", full)

    # 引用削除
    full = CITATION_BRACKET.sub("", full)
    full = CITATION_AUTHOR_YEAR.sub("", full)

    # URL / DOI 削除
    full = URL_PATTERN.sub("", full)

    # 引用削除で生じた余分な空白・括弧の片割れを整理
    full = re.sub(r"\s+([.,;:])", r"\1", full)         # 句読点前のスペース
    full = re.sub(r"\(\s*\)", "", full)                 # 空の括弧
    full = re.sub(r"\(\s*[.,;]\s*", "(", full)          # 括弧内の先頭の句読点
    full = re.sub(r"  +", " ", full)                    # 連続スペース

    # 行レベル処理
    cleaned_lines = []
    for line in full.split("\n"):
        s = line.strip()
        if not s:
            cleaned_lines.append("")
            continue
        if looks_like_math(s):
            continue
        # 句読点・括弧のみの行を除去
        if re.fullmatch(r"[\s\.\,\;\:\(\)\[\]\{\}\-—–\"'`、。「」（）]+", s):
            continue
        cleaned_lines.append(s)

    # 連続空行を 1 つに
    result = []
    prev_empty = False
    for line in cleaned_lines:
        if not line:
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    # 段落単位での再結合
    text = "\n".join(result)
    text = re.sub(r"([a-z,])\n([a-z])", r"\1 \2", text)
    text = re.sub(r"([、。」])\n([ぁ-んァ-ヶ一-龯])", r"\1\2", text)
    text = re.sub(r"([ぁ-んァ-ヶ一-龯])\n([ぁ-んァ-ヶ一-龯])", r"\1\2", text)

    return text.strip() + "\n"


def write_split_files(text: str, out_dir: Path) -> list[Path]:
    """テキストをセクションに分割してファイル出力."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sections = split_into_sections(text)
    written = []
    for idx, (name, content) in enumerate(sections):
        # ファイル名: 00_title.txt, 01_abstract.txt, ...
        filename = f"{idx:02d}_{name}.txt"
        path = out_dir / filename
        path.write_text(content + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    p = argparse.ArgumentParser(description="論文 PDF から読み上げ用テキストを抽出")
    p.add_argument("pdf", type=Path, help="入力 PDF")
    p.add_argument("-o", "--output", type=Path,
                   help="出力先 (省略時は <pdf>.txt または --split 時 <pdf>/)")
    p.add_argument("--split", action="store_true",
                   help="セクションごとに分割してディレクトリに出力")
    p.add_argument("--keep-refs", action="store_true", help="参考文献を残す")
    p.add_argument("--keep-authors", action="store_true",
                   help="著者ブロックを残す (デフォルトは除去)")
    p.add_argument("--stats", action="store_true", help="統計を表示")
    args = p.parse_args()

    if not args.pdf.exists():
        print(f"Error: {args.pdf} not found", file=sys.stderr)
        return 1

    blocks, header_candidates = extract_blocks(args.pdf)
    text = clean_text(
        blocks, header_candidates,
        keep_refs=args.keep_refs,
        keep_authors=args.keep_authors,
    )

    if args.split:
        out_dir = args.output or args.pdf.with_suffix("")
        written = write_split_files(text, out_dir)
        print(f"分割: {len(written)} ファイル → {out_dir}/")
        for path in written:
            chars = len(path.read_text(encoding="utf-8"))
            if args.stats:
                ja_min = chars / 400
                print(f"  {path.name:40s} {chars:>6,} 字  (日本語 約 {ja_min:>4.1f} 分)")
            else:
                print(f"  {path.name}  ({chars:,} chars)")
    else:
        out = args.output or args.pdf.with_suffix(".txt")
        out.write_text(text, encoding="utf-8")
        if args.stats:
            chars = len(text)
            ja_min = chars / 400
            en_min = chars / 750
            print(f"抽出: {chars:,} 文字 → {out}")
            print(f"読み上げ概算: 日本語 約 {ja_min:.1f} 分 / 英語 約 {en_min:.1f} 分")
        else:
            print(f"→ {out} ({len(text):,} chars)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
