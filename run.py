#!/usr/bin/env python3
"""
論文 PDF を 1 コマンドで「抽出 → 音声化 → タグ付け →（任意）配信」まで一気通貫で処理する.

これ 1 つで extract.py / speak.py / tag.py（と serve.py）を順番に呼び出す。

使い方:
    # 最小: PDF を渡すだけ（出力は <PDF 名>/ ディレクトリ）
    python run.py paper.pdf

    # 声は --voice auto がデフォルトなので、英語論文なら英語の声・日本語なら日本語の声を自動選択
    python run.py paper.pdf --backend edge

    # 処理後にそのまま Podcast 配信まで起動
    python run.py paper.pdf --serve

各オプションは個別スクリプトにそのまま渡される。
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_step(label: str, cmd: list) -> None:
    """1 ステップをサブプロセスで実行. 失敗したらそこで中断."""
    cmd = [str(c) for c in cmd]
    print(f"\n===== {label} =====")
    print("  $ " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nError: 「{label}」が失敗しました (exit {result.returncode})。中断します。",
              file=sys.stderr)
        sys.exit(result.returncode)


def main() -> int:
    p = argparse.ArgumentParser(
        description="論文 PDF を抽出→音声化→タグ付け→(任意)配信まで一括処理")
    p.add_argument("pdf", type=Path, help="入力 PDF")
    p.add_argument("-o", "--output", type=Path,
                   help="出力ディレクトリ (省略時は <PDF 名>/)")

    # --- extract.py 用 ---
    p.add_argument("--keep-refs", action="store_true", help="参考文献を残す")
    p.add_argument("--keep-authors", action="store_true", help="著者ブロックを残す")

    # --- speak.py 用 ---
    p.add_argument("--backend", choices=["edge", "say", "voicevox"], default="edge",
                   help="TTS バックエンド (デフォルト: edge)")
    p.add_argument("--voice", default="auto",
                   help="ボイス名。auto でテキストの言語に応じて自動選択 (デフォルト)")
    p.add_argument("--rate", default="+0%", help="話速 (edge: +20%%, say: 200 等)")
    p.add_argument("--ext", default="mp3", choices=["mp3", "wav", "aiff"],
                   help="出力音声の拡張子 (デフォルト: mp3)")
    p.add_argument("--speaker", type=int, default=3, help="VOICEVOX のスピーカー ID")

    # --- tag.py 用 ---
    p.add_argument("--title", help="アルバム名 (省略時は 00_title.txt またはフォルダ名)")
    p.add_argument("--artist", default="論文読み上げ", help="アーティスト名")
    p.add_argument("--genre", default="Speech", help="ジャンル")
    p.add_argument("--no-tag", action="store_true", help="タグ付けステップをスキップ")

    # --- serve.py 用 ---
    p.add_argument("--serve", action="store_true",
                   help="処理後に Podcast 配信 (serve.py) を起動")
    p.add_argument("--port", type=int, default=8080, help="配信ポート (デフォルト: 8080)")

    args = p.parse_args()

    if not args.pdf.exists():
        print(f"Error: {args.pdf} not found", file=sys.stderr)
        return 1

    out_dir = args.output or args.pdf.with_suffix("")
    py = sys.executable

    # 1) テキスト抽出（セクション分割）
    cmd = [py, HERE / "extract.py", args.pdf, "--split", "-o", out_dir, "--stats"]
    if args.keep_refs:
        cmd.append("--keep-refs")
    if args.keep_authors:
        cmd.append("--keep-authors")
    run_step("1/3 テキスト抽出", cmd)

    # 2) 音声化（ディレクトリを丸ごとバッチ処理）
    cmd = [py, HERE / "speak.py", out_dir, "-o", out_dir,
           "--backend", args.backend, "--voice", args.voice,
           "--rate", args.rate, "--ext", args.ext, "--speaker", args.speaker]
    run_step("2/3 音声化", cmd)

    # 3) ID3 タグ付け（mp3 のときのみ）
    if args.no_tag:
        print("\n(タグ付けはスキップしました)")
    elif args.ext != "mp3":
        print(f"\n注: 出力が .{args.ext} のため ID3 タグ付けはスキップします (mp3 のみ対応)")
    else:
        cmd = [py, HERE / "tag.py", out_dir, "--artist", args.artist, "--genre", args.genre]
        if args.title:
            cmd += ["--title", args.title]
        run_step("3/3 タグ付け", cmd)

    print(f"\n✅ 完了: {out_dir}/")

    # 4) (任意) Podcast 配信
    if args.serve:
        print("\nPodcast 配信を起動します (停止するには Ctrl-C)")
        subprocess.run([py, str(HERE / "serve.py"), str(out_dir), "--port", str(args.port)])

    return 0


if __name__ == "__main__":
    sys.exit(main())
