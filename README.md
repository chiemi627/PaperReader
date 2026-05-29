# paper_to_speech

論文 PDF から本文だけを取り出して、読み上げ用テキスト・音声ファイル・スマホ向けプレイリストに変換する試作品。

## できること

- 論文 PDF からタイトル + Abstract + 本文を抽出（著者・所属はデフォルトで除去）
- 2段組レイアウト・引用・図表キャプション・数式・参考文献を自動でクリーニング
- セクションごとに別ファイルに分割（`--split`）
- 複数バックエンドで音声化（Edge TTS / macOS `say` / VOICEVOX）
- 分割ディレクトリを丸ごとバッチ音声化
- ID3 タグ付け → iPhone でアルバム表示
- ローカル Podcast フィード配信 → iPhone Podcast アプリで購読

## 全体の流れ

```
論文.pdf
  ├─ extract.py --split ─→ 論文/00_title.txt, 01_abstract.txt, ...
  │                              │
  │                              ↓
  │                        speak.py 論文/
  │                              │
  │                              ↓
  │                        論文/00_title.mp3, 01_abstract.mp3, ...
  │                              │
  │                              ↓
  │                        tag.py 論文/   ←── iPhone 表示を整える
  │                              │
  │                              ↓
  │                        serve.py 論文/  ←── Podcast 配信
  ↓
  iPhone (Music / Podcast / Books / VLC)
```

## セットアップ

```bash
pip install pymupdf edge-tts mutagen   # 抽出・音声化・タグ付け
pip install segno                       # QR コード表示 (serve.py 用)
pip install requests                    # VOICEVOX を使う場合のみ
```

## 基本フロー

```bash
# 1. PDF からセクション分割テキストを抽出
python extract.py paper.pdf --split --stats

# 2. 全セクションを音声化
python speak.py paper/ --backend edge --voice ja-JP-NanamiNeural --ext mp3

# 3. ID3 タグを付ける（iPhone での表示を整える）
python tag.py paper/

# 4. (任意) Podcast 配信を起動
python serve.py paper/
```

## iPhone で聴く方法

### A. 一番簡単: iCloud Drive + Files アプリ

タグ付け後のフォルダごと iCloud Drive にドラッグするだけ。
iPhone の Files アプリから開いて再生できます。

**長所**: セットアップ不要
**短所**: 位置を記憶してくれない、速度調整が不便

### B. しっかり聴ける: VLC for Mobile（推奨・無料）

1. App Store で [VLC for Mobile](https://apps.apple.com/jp/app/vlc-for-mobile/id650377962) をインストール
2. VLC アプリ → 「ネットワーク」→「ローカルネットワーク」で同じ Wi-Fi の Mac を検出
3. または `python -m http.server` などで配信した URL を「URLを開く」で指定

**長所**: 速度調整 (0.5x〜2x)・位置記憶・バックグラウンド再生・フォルダ単位の自動連続再生
**短所**: 別アプリのインストールが必要

### C. ベストUX: Podcast アプリ + ローカル RSS（おすすめ）

`serve.py` で Mac から RSS フィードを配信し、QRコードを iPhone のカメラでスキャンするだけで Podcast アプリが自動で開きます。

```bash
# Mac 側で
python serve.py paper/
```

出力されるメッセージに従って Mac のブラウザで `http://<MacのIP>:8080/` を開くと、論文ごとに **QRコード付きの案内ページ**が表示されます。

iPhone 側の操作:
1. iPhone の **標準カメラアプリ** で QRコードを向ける
2. 上部に出てくる通知をタップ → **Podcast アプリで開く**
3. 番組ページで「フォロー」を押す

QRコードには `podcast://...` という URL スキームが埋め込まれているので、Safari ではなく Podcast アプリが直接開きます。

**長所**:
- 章ごとに「どこまで聞いたか」を完全に覚えてくれる
- 標準で 1.5x / 2x の速度切り替えが押しやすい場所にある
- AirPods のスキップボタンで章送り
- 1論文 = 1番組として整理される（複数論文も並ぶ）
- バックグラウンド再生・スリープタイマー

**注意点**:
- Mac とスマホは同じ Wi-Fi に接続が必要
- 出かける前に各エピソードを「ダウンロード」しておくと圏外でも聴ける
- Mac の `serve.py` を起動しっぱなしにする必要あり（普段使いするなら `launchd` で常駐化）

複数論文をまとめて配信する場合は、親ディレクトリを指定するだけです：

```bash
python serve.py ~/papers/
# 直下に MP3 がなく、サブフォルダに MP3 があれば自動で複数論文モードになる
```

QR コード付きの一覧ページが表示されます。

### D. オーディオブック風: Apple Books

タグ付けされた MP3 を Mac の Books アプリにドラッグするとオーディオブックとして取り込まれ、iCloud 経由で iPhone の Books アプリに同期されます。
ブックマーク・再生位置の同期・章スキップが利きます。

## オプション一覧

### `extract.py`

| オプション | 説明 |
|-----------|------|
| `-o`, `--output` | 出力先（ファイルまたはディレクトリ） |
| `--split` | セクションごとに分割して出力 |
| `--keep-authors` | 著者ブロックを残す（デフォルトは除去） |
| `--keep-refs` | 参考文献を残す |
| `--stats` | 文字数と読み上げ時間概算を表示 |

### `speak.py`

| オプション | 説明 |
|-----------|------|
| `-o`, `--output` | 出力音声ファイル または出力ディレクトリ |
| `--backend` | `edge` / `say` / `voicevox` |
| `--voice` | ボイス名（バックエンド依存） |
| `--rate` | 話速（edge: `+20%`、say: `220` 等） |
| `--ext` | 出力拡張子（ディレクトリ処理時） |

### `tag.py`

| オプション | 説明 |
|-----------|------|
| `--title` | アルバム名（省略時は 00_title.txt またはフォルダ名） |
| `--artist` | アーティスト名（デフォルト: 論文読み上げ） |
| `--genre` | ジャンル（デフォルト: Speech） |

### `serve.py`

| オプション | 説明 |
|-----------|------|
| `--port` | ポート番号（デフォルト: 8080） |
| `--multi` | 複数論文ディレクトリをまとめて配信 |

## セクション検出のルール

以下のいずれかにマッチする行を「セクション見出し」として認識します。

**番号付き**: `1. Introduction`, `2 Related Work`, `3. Method`, ...

**英語の既知見出し**（番号なしでも検出）:
Abstract, Introduction, Background, Related Work, Method(s), Methodology,
Approach, Experiments, Evaluation, Results, Analysis, Discussion,
Limitations, Conclusion, Acknowledgments

**日本語の既知見出し**:
概要, 要約, 要旨, はじめに, 緒言, 序論, 背景, 関連研究, 提案手法, 手法,
実験, 評価, 結果, 考察, 結論, おわりに, まとめ, 謝辞

## クリーニング処理の中身

1. 2段組の読み順を正す（左カラム → 右カラム）
2. ヘッダー・フッターを除去（ページ上下 8% にある短いテキスト）
3. 著者ブロックを除去（Abstract までの著者・所属を捨てる）
4. 図表キャプションを削除
5. 参考文献以降を切り落とし
6. 引用を削除
7. 数式行を除去
8. URL/DOI を削除
9. ハイフネーション結合・単語境界の修復

## 既知の限界

- スキャン PDF は OCR 前処理が必要（`ocrmypdf`）
- 数式が重要な論文には不向き
- 3段組や脚注の多い PDF は失敗する場合あり
- iPhone Podcast アプリのローカル feed 購読は同一 Wi-Fi 必須
