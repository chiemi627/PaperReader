#!/usr/bin/env python3
"""
論文 MP3 ディレクトリをローカル Podcast フィードとして配信する.

これを起動して iPhone の Podcast アプリで feed URL を購読すると、
論文1本 = 番組1個、章 = エピソード として聴けるようになる.

使い方:
    python serve.py paper/                # 自動で IP 検出
    python serve.py paper/ --port 8080    # ポート指定
    python serve.py papers/ --multi       # 複数論文のディレクトリを配信

iPhone Podcast アプリでの購読方法:
    1. アプリ起動 → 検索タブ
    2. 検索バーにフィード URL を入力
    3. もし表示されないときは「ライブラリ」→「...」→「番組をURLから追加」
       (英語版: "Add a Show by URL")

Mac とスマホは同じ Wi-Fi に接続している必要があります.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import io
import socket
import socketserver
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


def get_local_ip() -> str:
    """LAN 内で他端末から見える IP アドレスを推定."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def read_paper_title(directory: Path) -> str:
    """00_title.txt があれば読み取る."""
    title_file = directory / "00_title.txt"
    if title_file.exists():
        import re
        text = title_file.read_text(encoding="utf-8").strip()
        return re.sub(r"\s+", " ", text)
    return directory.name


def generate_feed(directory: Path, base_url: str, paper_title: str) -> str:
    """1つのディレクトリ向けに RSS フィードを生成."""
    import re

    mp3_files = sorted(directory.glob("*.mp3"))
    items = []
    base_time = datetime.now(timezone.utc)

    for i, mp3 in enumerate(mp3_files):
        # 章の順番で並ぶよう pubDate を細工: 最初の章を最も古く
        # (Podcast アプリは新しい順表示が多いので、ライブラリ追加後に並び替えで対応)
        pub_date = base_time - timedelta(seconds=(len(mp3_files) - i) * 60)

        m = re.match(r"^(\d+)[_\-](.+)$", mp3.stem)
        if m:
            track_num = int(m.group(1)) + 1  # 1-indexed display
            section = m.group(2).replace("_", " ")
            if re.match(r"^[a-z\s]+$", section):
                section = section.title()
            title = f"{track_num:02d}. {section}"
        else:
            title = mp3.stem

        size = mp3.stat().st_size
        url = f"{base_url}/{quote(directory.name)}/{quote(mp3.name)}"
        guid = hashlib.md5(f"{paper_title}/{mp3.name}".encode()).hexdigest()
        # 推定再生時間 (バイト数 / ビットレート概算 128kbps)
        duration_sec = max(int(size / (128_000 / 8)), 5)
        duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}"

        items.append(f"""    <item>
      <title>{escape(title)}</title>
      <description>{escape(f"{paper_title} - {title}")}</description>
      <enclosure url="{url}" length="{size}" type="audio/mpeg"/>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{format_datetime(pub_date)}</pubDate>
      <itunes:duration>{duration_str}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(paper_title)}</title>
    <description>{escape(f'論文読み上げ: {paper_title}')}</description>
    <language>ja</language>
    <itunes:author>paper_to_speech</itunes:author>
    <itunes:summary>{escape(paper_title)}</itunes:summary>
    <itunes:category text="Education"/>
    <itunes:explicit>false</itunes:explicit>
    <link>{base_url}/{quote(directory.name)}/feed.xml</link>
{chr(10).join(items)}
  </channel>
</rss>
"""


def generate_qr_svg(url: str, scale: int = 6) -> bytes | None:
    """指定 URL の QR コードを SVG バイト列で返す. segno がなければ None."""
    try:
        import segno
    except ImportError:
        return None
    qr = segno.make(url, error="M")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, xmldecl=False, omitsize=False,
            dark="#111", light="#fff", border=2)
    return buf.getvalue()


def make_handler(root_dir: Path, base_url: str):
    """HTTP リクエストハンドラを生成."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root_dir), **kwargs)

        def do_GET(self):
            parts = self.path.strip("/").split("/")
            # /<paper>/feed.xml → フィード動的生成
            if len(parts) == 2 and parts[1] == "feed.xml":
                paper_dir = root_dir / parts[0]
                if paper_dir.is_dir():
                    self.send_feed(paper_dir)
                    return
                self.send_error(404)
                return
            # /<paper>/qr.svg → 当該フィードの QR コード
            if len(parts) == 2 and parts[1] == "qr.svg":
                paper_dir = root_dir / parts[0]
                if paper_dir.is_dir():
                    self.send_qr(parts[0])
                    return
                self.send_error(404)
                return
            # / → 利用可能な論文のインデックス
            if self.path in ("/", "/index.html"):
                self.send_index()
                return
            super().do_GET()

        def send_feed(self, paper_dir: Path):
            title = read_paper_title(paper_dir)
            body = generate_feed(paper_dir, base_url, title).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_qr(self, paper_name: str):
            # Podcast アプリで直接開くため podcast:// スキームを使う
            feed_url = f"{base_url}/{quote(paper_name)}/feed.xml"
            podcast_url = feed_url.replace("http://", "podcast://", 1)
            svg = generate_qr_svg(podcast_url, scale=8)
            if svg is None:
                self.send_error(501, "segno not installed (pip install segno)")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(svg)))
            self.end_headers()
            self.wfile.write(svg)

        def send_index(self):
            papers = sorted([d for d in root_dir.iterdir()
                             if d.is_dir() and list(d.glob("*.mp3"))])

            # segno が利用可能かチェック
            try:
                import segno  # noqa: F401
                has_qr = True
            except ImportError:
                has_qr = False

            html = ["""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>論文 Podcast フィード</title>
<style>
  body { font-family: -apple-system, "Hiragino Sans", sans-serif;
         max-width: 720px; margin: 2em auto; padding: 0 1em;
         color: #222; background: #fafafa; line-height: 1.6; }
  h1 { font-size: 1.5em; border-bottom: 2px solid #555; padding-bottom: 0.3em; }
  .paper { background: #fff; border: 1px solid #ddd; border-radius: 8px;
           padding: 1.2em; margin: 1.2em 0;
           box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .paper h2 { margin: 0 0 0.6em; font-size: 1.15em; color: #333; }
  .qr { display: inline-block; vertical-align: top;
        width: 200px; padding: 8px; background: #fff;
        border: 1px solid #eee; border-radius: 6px; }
  .qr img { display: block; width: 100%; height: auto; }
  .info { display: inline-block; vertical-align: top;
          margin-left: 1.5em; max-width: 420px; }
  .info p { margin: 0.4em 0; }
  .url { font-family: ui-monospace, "SF Mono", monospace;
         font-size: 0.85em; word-break: break-all;
         background: #f0f0f0; padding: 4px 8px; border-radius: 4px;
         display: inline-block; }
  .step { color: #555; font-size: 0.92em; }
  .step b { color: #c33; }
  .warn { background: #fff8d6; border: 1px solid #e0c060;
          padding: 0.8em 1em; border-radius: 6px; }
  @media (max-width: 600px) {
    .info { margin-left: 0; margin-top: 1em; }
    .qr { width: 240px; }
  }
</style>
</head>
<body>
<h1>論文 Podcast フィード</h1>
<p class="step">スマホで QR をスキャンすると Podcast アプリで開きます.
購読すると章ごとに位置を覚えてくれます.</p>
"""]

            if not has_qr:
                html.append(
                    '<p class="warn">QR コード表示には '
                    '<code>pip install segno</code> が必要です. '
                    '今は URL 文字列のみ表示します.</p>'
                )

            if not papers:
                html.append('<p>配信中の論文がありません.</p>')

            for p in papers:
                title = read_paper_title(p)
                http_url = f"{base_url}/{quote(p.name)}/feed.xml"
                qr_src = f"/{quote(p.name)}/qr.svg"

                html.append(f'<div class="paper">')
                html.append(f'<h2>{escape(title)}</h2>')
                if has_qr:
                    html.append(f'<div class="qr"><img src="{qr_src}" alt="QR for {escape(p.name)}"></div>')
                html.append(f'<div class="info">')
                html.append(
                    '<p class="step">'
                    '① iPhone のカメラで QR をスキャン<br>'
                    '② 通知をタップ → <b>Podcast アプリで開く</b><br>'
                    '③ 番組ページで「フォロー」を押す'
                    '</p>'
                )
                html.append(f'<p>フィード URL:<br><span class="url">{escape(http_url)}</span></p>')
                html.append(f'</div>')
                html.append('</div>')

            html.append("</body></html>")
            body = "\n".join(html).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            # アクセスログは出さない (静かに)
            pass

    return Handler


def main() -> int:
    p = argparse.ArgumentParser(description="MP3 ディレクトリを Podcast フィードとして配信")
    p.add_argument("path", type=Path,
                   help="論文フォルダ または 複数論文フォルダを含む親ディレクトリ")
    p.add_argument("--port", type=int, default=8080, help="ポート番号 (デフォルト: 8080)")
    p.add_argument("--multi", action="store_true",
                   help="(任意) 強制的に複数論文モードにする")
    args = p.parse_args()

    if not args.path.is_dir():
        print(f"Error: {args.path} はディレクトリではありません", file=sys.stderr)
        return 1

    # 自動判定:
    #   指定ディレクトリに MP3 が直接ある → 単一論文モード
    #   無くて、サブディレクトリに MP3 がある → 複数論文モード
    has_direct_mp3 = bool(list(args.path.glob("*.mp3")))
    sub_papers = sorted([d for d in args.path.iterdir()
                         if d.is_dir() and list(d.glob("*.mp3"))])

    if args.multi:
        multi_mode = True
    elif has_direct_mp3:
        multi_mode = False
    elif sub_papers:
        multi_mode = True
        print(f"(サブフォルダに MP3 を {len(sub_papers)} 本検出 → 複数論文モード)")
    else:
        print(f"Error: {args.path} とそのサブフォルダに MP3 が見つかりません",
              file=sys.stderr)
        print(f"先に speak.py で MP3 を生成してください.", file=sys.stderr)
        return 1

    # root_dir の設定
    if multi_mode:
        root_dir = args.path.resolve()
    else:
        root_dir = args.path.resolve().parent

    ip = get_local_ip()
    base_url = f"http://{ip}:{args.port}"

    print(f"配信開始: {root_dir}")
    print()
    print("=" * 60)
    print(f"  Mac のブラウザで開いてください:")
    print(f"    {base_url}/")
    print(f"  → ページに表示される QR コードを iPhone でスキャン")
    print("=" * 60)
    print()

    if multi_mode:
        papers = sorted([d for d in root_dir.iterdir()
                         if d.is_dir() and list(d.glob("*.mp3"))])
        print(f"配信中の論文 ({len(papers)} 本):")
        for p_dir in papers:
            print(f"  - {p_dir.name}")
    else:
        paper_name = args.path.name
        print(f"配信中: {paper_name}")

    print()
    print("(Mac と iPhone は同じ Wi-Fi に接続している必要があります)")
    print("停止するには Ctrl+C")
    print()

    handler = make_handler(root_dir, base_url)
    try:
        with socketserver.ThreadingTCPServer(("0.0.0.0", args.port), handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
