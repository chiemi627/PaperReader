#!/usr/bin/env python3
"""
論文の音声ファイル群に ID3 タグを付ける.

これをやっておくと:
- iPhone のミュージックアプリで「アルバム」として表示される
- Podcast アプリ・VLC で章タイトルが見える
- Apple Books で audiobook として読み込める

使い方:
    python tag.py paper/                          # 自動判定
    python tag.py paper/ --title "論文タイトル"     # タイトル指定
    python tag.py paper/ --artist "研究室"          # アーティスト名指定
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TRCK, TCON, ID3NoHeaderError
    from mutagen.mp3 import MP3
except ImportError:
    print("Error: pip install mutagen が必要です", file=sys.stderr)
    sys.exit(1)


def read_paper_title(audio_dir: Path) -> str:
    """00_title.txt があれば読み取る."""
    title_file = audio_dir / "00_title.txt"
    if title_file.exists():
        # 改行を整理してタイトル文字列にまとめる
        text = title_file.read_text(encoding="utf-8").strip()
        return re.sub(r"\s+", " ", text)
    return audio_dir.name


def parse_section_name(stem: str) -> tuple[int | None, str]:
    """ファイル名から (トラック番号, 章名) を取り出す.

    例:  "02_introduction" → (2, "Introduction")
         "05_related_work" → (5, "Related Work")
         "01_提案手法"      → (1, "提案手法")
    """
    m = re.match(r"^(\d+)[_\-](.+)$", stem)
    if m:
        track_num = int(m.group(1))
        section = m.group(2).replace("_", " ")
        # 英語のセクション名は Title Case に
        if re.match(r"^[a-z\s]+$", section):
            section = section.title()
        return track_num, section
    return None, stem


def tag_directory(audio_dir: Path, paper_title: str, artist: str, genre: str) -> None:
    """ディレクトリ内の MP3 にタグを付ける."""
    mp3_files = sorted(audio_dir.glob("*.mp3"))
    if not mp3_files:
        print(f"Error: {audio_dir} に MP3 がありません", file=sys.stderr)
        sys.exit(1)

    total = len(mp3_files)
    print(f"論文: {paper_title}")
    print(f"アーティスト: {artist}")
    print(f"トラック数: {total}")
    print()

    for mp3_path in mp3_files:
        track_num, section = parse_section_name(mp3_path.stem)
        # ファイル名の番号は 0 始まり (00_title, 01_abstract, ...) なので
        # iPhone での表示用に 1 始まりにずらす
        track_num = track_num + 1 if track_num is not None else mp3_files.index(mp3_path) + 1

        audio = MP3(mp3_path)
        try:
            audio.add_tags()
        except Exception:
            pass  # すでにタグがある

        tags = audio.tags
        tags.delall("TIT2")
        tags.delall("TALB")
        tags.delall("TPE1")
        tags.delall("TPE2")
        tags.delall("TRCK")
        tags.delall("TCON")

        tags.add(TIT2(encoding=3, text=section))                     # 曲名 = 章名
        tags.add(TALB(encoding=3, text=paper_title))                 # アルバム = 論文タイトル
        tags.add(TPE1(encoding=3, text=artist))                      # アーティスト
        tags.add(TPE2(encoding=3, text=artist))                      # アルバムアーティスト
        tags.add(TRCK(encoding=3, text=f"{track_num}/{total}"))      # トラック番号
        tags.add(TCON(encoding=3, text=genre))                       # ジャンル

        audio.save()
        print(f"  {mp3_path.name}  →  {track_num:02d}/{total} {section}")

    print()
    print("完了. iPhone のミュージックアプリでアルバムとして表示されます.")


def main() -> int:
    p = argparse.ArgumentParser(description="論文音声ファイルに ID3 タグを付ける")
    p.add_argument("audio_dir", type=Path, help="MP3 を含むディレクトリ")
    p.add_argument("--title", help="アルバム名 (省略時は 00_title.txt またはフォルダ名)")
    p.add_argument("--artist", default="論文読み上げ", help="アーティスト名 (デフォルト: 論文読み上げ)")
    p.add_argument("--genre", default="Speech", help="ジャンル (デフォルト: Speech)")
    args = p.parse_args()

    if not args.audio_dir.is_dir():
        print(f"Error: {args.audio_dir} はディレクトリではありません", file=sys.stderr)
        return 1

    title = args.title or read_paper_title(args.audio_dir)
    tag_directory(args.audio_dir, title, args.artist, args.genre)
    return 0


if __name__ == "__main__":
    sys.exit(main())
