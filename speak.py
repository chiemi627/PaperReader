#!/usr/bin/env python3
"""
テキストを音声に変換するスクリプト（複数バックエンド対応）

使い方:
    # Edge TTS（推奨・無料・高品質）
    python speak.py input.txt -o output.mp3 --backend edge --voice ja-JP-NanamiNeural

    # --voice を省略 (auto) するとテキストの言語を判定して声を自動選択
    #   日本語 → ja-JP-NanamiNeural / 英語 → en-US-AriaNeural (edge)
    #   日本語 → Kyoko / 英語 → Samantha (say)
    python speak.py input.txt -o output.mp3

    # macOS の say コマンド（ローカル完結）
    python speak.py input.txt -o output.aiff --backend say --voice Kyoko

    # VOICEVOX エンジン（要起動: localhost:50021）
    python speak.py input.txt -o output.wav --backend voicevox --speaker 3

バックエンドごとの特徴:
- edge: 無料・クラウド・高品質・日英多言語。要 pip install edge-tts
- say: macOS 標準。完全オフライン。Kyoko (ja), Samantha (en) など
- voicevox: 日本語特化。要 VOICEVOX エンジン起動。最高品質の日本語
"""

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
from pathlib import Path


# Edge TTS の代表的なボイス
EDGE_VOICES = {
    "ja-natural-f": "ja-JP-NanamiNeural",   # 日本語 女性 自然
    "ja-natural-m": "ja-JP-KeitaNeural",    # 日本語 男性 自然
    "en-natural-f": "en-US-AriaNeural",     # 英語 女性
    "en-natural-m": "en-US-GuyNeural",      # 英語 男性
}

# --voice auto のとき、言語判定の結果で選ぶデフォルトボイス（backend 別）
DEFAULT_VOICES = {
    "edge": {"ja": "ja-JP-NanamiNeural", "en": "en-US-AriaNeural"},
    "say": {"ja": "Kyoko", "en": "Samantha"},
}


def detect_language(text: str) -> str:
    """テキストが日本語か英語かを判定 (extract.py と同じ基準).

    かな・漢字の文字数とラテン文字数を比較し、日本語文字が一定割合
    以上あれば 'ja'、そうでなければ 'en' を返す。
    """
    ja = len(re.findall(r"[ぁ-んァ-ヶ一-龯]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    if ja + en == 0:
        return "en"
    return "ja" if ja / (ja + en) > 0.2 else "en"


def resolve_voice(voice: str, backend: str, text: str) -> str:
    """--voice auto のとき、テキストの言語に応じたボイスを返す."""
    if voice != "auto":
        return voice
    lang = detect_language(text)
    table = DEFAULT_VOICES.get(backend, DEFAULT_VOICES["edge"])
    chosen = table[lang]
    print(f"  言語判定: {lang} → ボイス {chosen}")
    return chosen


async def speak_edge(text: str, out: Path, voice: str, rate: str = "+0%"):
    """Edge TTS（Microsoft）でテキストを音声化."""
    try:
        import edge_tts
    except ImportError:
        print("Error: pip install edge-tts が必要です", file=sys.stderr)
        sys.exit(1)

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out))


def speak_say(text: str, out: Path, voice: str, rate: int = 200):
    """macOS の say コマンドでテキストを音声化."""
    if not shutil.which("say"):
        print("Error: say コマンドが見つかりません (macOS でのみ動作)", file=sys.stderr)
        sys.exit(1)

    # 入力テキストを一時ファイルに書く（長文対応のため）
    tmp = out.with_suffix(".tmp.txt")
    tmp.write_text(text, encoding="utf-8")
    try:
        cmd = ["say", "-v", voice, "-r", str(rate), "-f", str(tmp), "-o", str(out)]
        subprocess.run(cmd, check=True)
    finally:
        tmp.unlink(missing_ok=True)


def speak_voicevox(text: str, out: Path, speaker: int = 3, host: str = "http://localhost:50021"):
    """VOICEVOX エンジンでテキストを音声化（要事前起動）."""
    try:
        import requests
    except ImportError:
        print("Error: pip install requests が必要です", file=sys.stderr)
        sys.exit(1)

    # 長文を句点で分割（VOICEVOX は一度に長文を投げると遅い・失敗する）
    sentences = [s.strip() + "。" for s in text.replace("\n", "").split("。") if s.strip()]

    import wave
    import io

    audio_parts = []
    for i, sent in enumerate(sentences):
        # audio_query
        q = requests.post(f"{host}/audio_query", params={"text": sent, "speaker": speaker})
        q.raise_for_status()
        # synthesis
        s = requests.post(
            f"{host}/synthesis",
            params={"speaker": speaker},
            json=q.json(),
        )
        s.raise_for_status()
        audio_parts.append(s.content)
        if (i + 1) % 10 == 0:
            print(f"  ... {i + 1}/{len(sentences)} 文")

    # WAV を連結（最初のヘッダを使い、フレームだけ追加していく）
    if not audio_parts:
        print("Error: 合成する文が見つかりません", file=sys.stderr)
        sys.exit(1)

    with wave.open(str(out), "wb") as outwav:
        for i, part in enumerate(audio_parts):
            with wave.open(io.BytesIO(part), "rb") as w:
                if i == 0:
                    outwav.setparams(w.getparams())
                outwav.writeframes(w.readframes(w.getnframes()))


def main() -> int:
    p = argparse.ArgumentParser(description="テキストを音声化")
    p.add_argument("text_file", type=Path,
                   help="入力テキストファイル または .txt を含むディレクトリ")
    p.add_argument("-o", "--output", type=Path,
                   help="出力音声ファイル (ファイル入力時) または出力ディレクトリ")
    p.add_argument(
        "--backend",
        choices=["edge", "say", "voicevox"],
        default="edge",
        help="TTS バックエンド",
    )
    p.add_argument("--voice", default="auto",
                   help="ボイス名 (backend依存)。auto でテキストの言語に応じて自動選択")
    p.add_argument("--speaker", type=int, default=3, help="VOICEVOX のスピーカー ID")
    p.add_argument("--rate", default="+0%", help="話速 (edge: +20%%, say: 200 等)")
    p.add_argument("--ext", default="mp3", choices=["mp3", "wav", "aiff"],
                   help="出力拡張子 (ディレクトリ処理時)")
    args = p.parse_args()

    if not args.text_file.exists():
        print(f"Error: {args.text_file} not found", file=sys.stderr)
        return 1

    # ディレクトリの場合は中の .txt をすべて処理
    if args.text_file.is_dir():
        txt_files = sorted(args.text_file.glob("*.txt"))
        if not txt_files:
            print(f"Error: {args.text_file} に .txt がありません", file=sys.stderr)
            return 1

        out_dir = args.output or args.text_file
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"バッチ処理: {len(txt_files)} ファイル")

        for txt in txt_files:
            out = out_dir / f"{txt.stem}.{args.ext}"
            print(f"  {txt.name} → {out.name}")
            text = txt.read_text(encoding="utf-8").strip()
            if not text:
                print(f"    (空のためスキップ)")
                continue
            _dispatch_backend(text, out, args)
        print("完了")
        return 0

    # 単一ファイル
    text = args.text_file.read_text(encoding="utf-8")
    print(f"テキスト: {len(text):,} 文字")
    print(f"バックエンド: {args.backend}")

    if not args.output:
        print("Error: 単一ファイル入力時は -o で出力先を指定してください", file=sys.stderr)
        return 1
    print(f"出力: {args.output}")
    _dispatch_backend(text, args.output, args)
    print(f"完了: {args.output}")
    return 0


def _dispatch_backend(text: str, out: Path, args) -> None:
    """バックエンドを選んで音声合成を実行."""
    if args.backend == "edge":
        voice = resolve_voice(args.voice, "edge", text)
        asyncio.run(speak_edge(text, out, voice, args.rate))
    elif args.backend == "say":
        voice = resolve_voice(args.voice, "say", text)
        try:
            rate = int(args.rate.replace("+", "").replace("%", "")) if "%" in args.rate else int(args.rate)
        except ValueError:
            rate = 200
        speak_say(text, out, voice, rate)
    elif args.backend == "voicevox":
        speak_voicevox(text, out, args.speaker)


if __name__ == "__main__":
    sys.exit(main())
