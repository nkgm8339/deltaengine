# DeltaEngine 利用マニュアル

Binance Futures の約定・板情報をリアルタイム分析し、売買シグナルを生成するシステムです。

---

## 1. セットアップ

### 手順

コマンドプロンプトを開き、以下を順番に実行してください。

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
pip install -r requirements.txt
python -m pytest -q
```

最後のコマンドで `204 passed` と表示されればセットアップ完了です。

---

## 2. 動かしてみる

設定はデフォルトのまま、すぐに動かせます。

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_verify --duration 60
```

60 秒間 Binance から BTCUSDT のデータを受信し、全ての分析パイプラインを実行します。終了後に以下のような統計が表示されます。

```
=== LiveStats ===
  raw_out                          : 1523
  normalized                       : 842
  trades_stored                    : 842
  candles_stored                   : 1
  signals_stored                   : 1

=== OrderBook Stats ===
  book_snapshots_applied           : 1
  book_diffs_applied               : 681

=== Absorption Stats ===
  absorption_events_detected       : 0
```

`book_snapshots_applied` が `1` になっていれば、板情報の取得も正常です。

---

## 3. データを記録する

後からオフラインで再分析できるよう、受信データを記録できます。

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_capture --duration 300 --record data\recordings\session1.jsonl
```

これで 5 分間のデータが `data\recordings\session1.jsonl` に保存されます。

`--duration` の代わりに `--max-trades 1000` で約定数を指定することもできます。どちらか一方は必ず指定してください。

---

## 4. 記録したデータを再分析する

ネットワーク接続なしで、記録済みデータを再処理できます。Python スクリプトとして実行します。

```python
from src.config import load_config
from src.pipeline import ReplayPipeline, load_profile

config = load_config("config/config.yaml")
profile = load_profile("config/profiles/binance.yaml")
pipeline = ReplayPipeline.from_config(config, profile, "data/parquet", "data/duckdb/of.duckdb")
stats = pipeline.run("data/recordings/session1.jsonl")

print(f"約定数:     {stats.trades_stored}")
print(f"バー数:     {stats.candles_stored}")
print(f"シグナル数: {stats.signals_stored}")
print(f"最終 CVD:   {stats.final_cvd}")
```

同じファイルを何度実行しても、完全に同じ結果になります。

---

## 5. シグナル生成を有効にする

デフォルトではシグナル生成は無効です。有効にするには `config\config.yaml` をテキストエディタで開き、以下の 1 行を変更してください。

変更前:
```yaml
signal:
  enabled: false
```

変更後:
```yaml
signal:
  enabled: true
```

保存したら、§2 または §3 のコマンドを再実行してください。シグナルが生成され、`data\duckdb\orderflow.duckdb` に保存されます。

保存されたシグナルは以下のコマンドで確認できます。

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -c "import duckdb; print(duckdb.connect('data/duckdb/orderflow.duckdb').sql('SELECT * FROM signals ORDER BY bar_time DESC LIMIT 10').df())"
```

---

## 6. 通貨ペアを変更する

デフォルトは BTCUSDT です。例えば ETHUSDT に変更するには、`config\config.yaml` の以下の 2 箇所を書き換えてください。

```yaml
market:
  symbol: ETHUSDT

websocket:
  subscribe_streams:
    - "ethusdt@aggTrade"
    - "ethusdt@depth@100ms"
```

ストリーム名は全て小文字です。

---

## 7. MT5 にシグナルを配信する

### プラットフォーム側の設定

`config\config.yaml` を開き、以下の 1 行を変更してください。

変更前:
```yaml
mt5:
  enabled: false
```

変更後:
```yaml
mt5:
  enabled: true
```

保存後、§2 のコマンドでライブモードを起動すると、TCP サーバーが自動的に起動します（ポート 5555）。

### MT5 側の接続

Expert Advisor またはインジケーターに以下のコードを追加してください。

```mql5
int socket = SocketCreate();
if (socket != INVALID_HANDLE)
{
    if (SocketConnect(socket, "127.0.0.1", 5555, 5000))
    {
        char buf[];
        while (SocketIsReadable(socket))
        {
            int len = SocketRead(socket, buf, 4096, 100);
            if (len > 0)
            {
                string json = CharArrayToString(buf, 0, len);
                // json を改行で分割し、各行を JSON パースして利用
            }
        }
    }
    SocketClose(socket);
}
```

### 受信するメッセージ

改行区切りの JSON が届きます。

```json
{"type":"SIGNAL","time":"2026-01-01T00:01:00+00:00","symbol":"BTCUSDT","payload":{"market_state":"BULL","confidence":"0.82","risk_level":"LOW","summary":"BULL: BUY signal at 82% confidence","reasons":["CVD_POSITIVE"]}}
```

| type | 内容 |
|------|------|
| SIGNAL | 売買シグナル |
| HEARTBEAT | 死活監視（5 秒間隔） |
| CVD | CVD 値の更新 |
| IMBALANCE | Imbalance 検出イベント |
| ABSORPTION | Absorption 検出イベント |

HEARTBEAT を受信したら ACK を返してください。3 回連続で返さないと切断されます。

```mql5
string ack = "{\"type\":\"ACK\"}\n";
char ack_buf[];
StringToCharArray(ack, ack_buf);
SocketSend(socket, ack_buf, ArraySize(ack_buf));
```

---

## 8. データフロー

```
Binance Futures
  │
  ├── aggTrade（約定）
  │     ▼
  │   正規化 → CVD → Footprint → Imbalance
  │                                    │
  │                                    ▼
  │                              SignalEngine → AI Analysis → 保存 / MT5 配信
  │
  └── depth（板情報）
        ▼
      正規化 → OrderBook → Absorption → SignalEngine（veto 判定）
```

---

## 9. うまく動かないとき

| 症状 | 対処 |
|------|------|
| `pip install` で `requirements.txt` が見つからない | `cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web` を実行してから再試行 |
| WebSocket 接続エラー | インターネット接続を確認。Binance メンテナンス中の可能性あり。自動再接続するので待ってください |
| シグナルが出ない | `config\config.yaml` の `signal.enabled` を `true` に変更してください |
| MT5 から接続できない | `config\config.yaml` の `mt5.enabled` を `true` に変更してください。ポート 5555 が他のソフトに使われていないか確認 |
| MT5 接続が途中で切れる | HEARTBEAT に対して ACK を返していない可能性あり（§7 参照） |
| `204 passed` にならない | Python 3.12 以上であることを `python --version` で確認 |
