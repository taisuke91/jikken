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

- `GET /api/health` — 動作確認。`accumulator_state` にサーバ内の累積状態（0〜3）が含まれます。
- `POST /api/score-text` — JSON: `{"transcript":"…"}`
- `POST /api/score-audio` — multipart: フィールド `file`（WebM 録音など）
- `POST /api/mcu-push` — JSON: `{"state": 0-3}` … Gemini なしで蓄積状態をその値にセットしてシリアル送信（配線テスト用）。画面の「テスト（マイコンのみ）」ボタンからも送信可。

`score-text` / `score-audio` の応答フィールド:

- `score`: Gemini が返した値（整数 `-1` または `0`〜`3`）。JSON スキーマは `score` のみ。
- `state`: **送信後**の累積レベル（0〜3）。マイコンにもこの値が送られます。
- `label`: `state` に対応する日本語ラベル。
- `raw_json`: モデル生データ（デバッグ用）。

**状態の更新ルール（サーバ側・LLM は足し算しない）**

1. `score === -1`（謝罪・強いデエスカレーションと判定されたとき）→ **`state` は必ず 0**（減算ではなくフルリセット）。
2. `score` が `0`〜`3` のとき → `state = max(0, min(3, 前回のstate + score))`。

プロセス再起動で累積は 0 に戻ります。

## マイコンと PC をつなぐ（初心者向け）

### 1. 物理的なつながり

- 大多数の開発用ボード（Arduino Uno, ESP32 等）は USB ケーブルで PC につなぎます。
- PC 側には **シリアルポート**（COM ポート / tty デバイス）が現れます。macOS では ` /dev/cu.usbmodem*` や ` /dev/cu.usbserial-*` の名前が多いです。
- **重要**: 同じ USB 線で **マイコンと Arduino スケッチを同時に開くとポート競合する** ので、通常は判定 API を動かしている間は Arduino IDE のシリアルモニタを閉じるか、**2 台の PC** または **ESP32 の Wi-Fi 経由** で分離すると楽です。

### 2. このプロジェクトでの流れ

1. Arduino に `firmware/arduino_flame_toy/arduino_flame_toy.ino` を書き込み、通信速度 115200 でアップロード。
2. `.env` に `SERIAL_PORT=` （上記のデバイスパス）と `SERIAL_SIMPLE=1` を設定。
3. API を起動したままブラウザから録音判定すると、判定直後に `FLAME <0-3>` がシリアルで送られます。

4. スケッチはその文字列を読んで LED を点滅します（サンプルは点滅回数で強さを表現）。

### 3. トラブルシュート

| 現象 | 対処 |
|---------|--------|
| ポートが見つからない | USB 差し直し、別のケーブル、ドライバ（CH340 等）のインストール |
| Permission denied | macOS/Linux でユーザを `dialout`/`uucp` に入れる、または `cu.` 側を使う |
| 音声 API が失敗する | ブラウザのコンソールとレスポンス本文を確認する。録音は WebM（Opus）送出が多く、モデル・MIME の組み合わせによっては未対応のことがある |

## 注意

暴言分析のため、API は Gemini の安全フィルタを緩めています。公開サービスにする場合は利用規約・法令を確認してください。
