# 暴言ランク / 炎上指数（Gemini + 構造化 JSON）

## 必要環境

- Python 3.10+
- Google AI Studio で取得した API キー（`GEMINI_API_KEY`）
- マイク付き PC（ブラウザは Chrome 推奨）

## 起動手順

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env に GEMINI_API_KEY を記載
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

ブラウザで http://127.0.0.1:8000/ を開く。

## API

- `GET /api/health` — 動作確認
- `POST /api/score-text` — JSON: `{"transcript":"…"}`
- `POST /api/score-audio` — multipart: フィールド `file`（WebM 録音など）
- `POST /api/mcu-push` — JSON: `{"score": 1-10}` … Gemini なしでシリアルのみ（配線テスト用）。画面の「テスト（マイコンのみ）」ボタンからも送信可。

出力は `score` (1-10), `label` (日本語ランク名), `raw_json` 。Gemini 側は `response_mime_type=application/json` + `response_schema` （`score: int`）で安定化。

## マイコンと PC をつなぐ（初心者向け）

### 1. 物理的なつながり

- 大多数の開発用ボード（Arduino Uno, ESP32 等）は USB ケーブルで PC につなぎます。
- PC 側には **シリアルポート**（COM ポート / tty デバイス）が現れます。macOS では ` /dev/cu.usbmodem*` や ` /dev/cu.usbserial-*` の名前が多いです。
- **重要**: 同じ USB 線で **マイコンと Arduino スケッチを同時に開くとポート競合する** ので、通常は判定 API を動かしている間は Arduino IDE のシリアルモニタを閉じるか、**2 台の PC** または **ESP32 の Wi-Fi 経由** で分離すると楽です。

### 2. このプロジェクトでの流れ

1. Arduino に `firmware/arduino_flame_toy/arduino_flame_toy.ino` を書き込み、通信速度 115200 でアップロード。
2. `.env` に `SERIAL_PORT=` （上記のデバイスパス）と `SERIAL_SIMPLE=1` を設定。
3. API を起動したままブラウザから録音判定すると、判定直後に `FLAME <1-10>` がシリアルで送られます。

4. スケッチはその文字列を読んで LED を点滅します（サンプルは点滅回数で強さを表現）。

### 3. トラブルシュート

| 現象 | 対処 |
|---------|--------|
| ポートが見つからない | USB 差し直し、別のケーブル、ドライバ（CH340 等）のインストール |
| Permission denied | macOS/Linux でユーザを `dialout`/`uucp` に入れる、または `cu.` 側を使う |
| 音声 API が失敗する | 先に **ブラウザ認識 → テキスト判定** を試す。音声は WebM でモデルによって未対応のことあり |

## 注意

暴言分析のため、API は Gemini の安全フィルタを緩めています。公開サービスにする場合は利用規約・法令を確認してください。
