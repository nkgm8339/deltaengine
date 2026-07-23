# DeltaEngine ユースケース集

---

## ユースケース 1: 今の相場の勢いを知りたい

**やりたいこと**: BTCUSDT が今買われているのか売られているのかを知りたい。

**手順**:

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_verify --duration 60
```

**見るところ**: 出力の `final_cvd` の値。

- **プラスなら買い優勢**（例: `final_cvd: 12.5` → 60 秒間で買いが 12.5 BTC 多い）
- **マイナスなら売り優勢**（例: `final_cvd: -8.3` → 売りが 8.3 BTC 多い）

---

## ユースケース 2: 売買シグナルを出したい

**やりたいこと**: CVD・Footprint・Imbalance・Absorption を総合判定して、BUY / SELL / WAIT のシグナルを自動生成したい。

**手順**:

1. `config\config.yaml` をテキストエディタで開く
2. `signal:` セクションの `enabled` を `true` に変更して保存

```yaml
signal:
  enabled: true
```

3. ライブ実行する

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_verify --duration 300
```

**見るところ**: 出力の `signals_stored` が 1 以上なら、シグナルが生成されています。

**シグナルの中身を確認する**:

```
python -c "import duckdb; print(duckdb.connect('data/duckdb/orderflow.duckdb').sql('SELECT * FROM signals ORDER BY bar_time DESC LIMIT 10').df())"
```

各行に BUY / SELL / WAIT と confidence（確信度）が表示されます。

---

## ユースケース 3: 大口の吸収パターンを検出したい

**やりたいこと**: 大量の売り注文が出ているのに価格が下がらない（= 誰かが買い吸収している）パターンを検出したい。

**手順**: ユースケース 2 と同じ（シグナルを有効にしてライブ実行）。

**見るところ**: 出力の `absorption_events_detected`。

- `0` → 検出なし（検出窓の 10 秒間に条件を満たす動きがなかった）
- `1 以上` → 吸収パターンを検出。シグナルの `risk_level` が `MEDIUM` になり、BUY/SELL 判定に veto がかかる場合がある

吸収が検出されると、シグナルの `reasons` に `ABSORPTION_ACTIVE` が追加されます。

---

## ユースケース 4: 過去のデータを何度も分析したい

**やりたいこと**: 気になる時間帯のデータを記録しておいて、後から条件を変えて再分析したい。

**手順**:

まず記録する（ネットワーク接続が必要）:

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_capture --duration 600 --record data\recordings\session1.jsonl
```

10 分間のデータが `session1.jsonl` に保存されます。

次に再分析する（ネットワーク不要）:

```python
from src.config import load_config
from src.pipeline import ReplayPipeline, load_profile

config = load_config("config/config.yaml")
profile = load_profile("config/profiles/binance.yaml")
pipeline = ReplayPipeline.from_config(config, profile, "data/parquet", "data/duckdb/of.duckdb")
stats = pipeline.run("data/recordings/session1.jsonl")

print(f"約定数:     {stats.trades_stored}")
print(f"シグナル数: {stats.signals_stored}")
print(f"最終 CVD:   {stats.final_cvd}")
```

`config.yaml` の `signal.confidence_threshold` や `imbalance.ratio_threshold` を変えて再実行すれば、異なる条件での結果を比較できます。同じファイルなら何度やっても同じ結果になるので、条件の違いだけを純粋に比較できます。

---

## ユースケース 5: MT5 のチャート上にシグナルを表示したい

**やりたいこと**: DeltaEngine のシグナルを MetaTrader 5 にリアルタイム配信し、チャート上に表示したい。

**手順**:

1. `config\config.yaml` で 2 箇所を `true` に変更

```yaml
signal:
  enabled: true

mt5:
  enabled: true
```

2. DeltaEngine をライブ起動

```
cd C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web
python -m tools.live_verify --duration 3600
```

3. MT5 側で Expert Advisor またはインジケーターを作成し、`127.0.0.1:5555` に TCP 接続

受信する JSON の `payload.market_state` を見て表示を切り替えます:

| market_state | 意味 | チャート表示例 |
|-------------|------|-------------|
| STRONG_BULL | 強い買い | 緑の太矢印 ↑ |
| BULL | 買い | 緑の矢印 ↑ |
| NEUTRAL | 中立 | 表示なし |
| BEAR | 売り | 赤の矢印 ↓ |
| STRONG_BEAR | 強い売り | 赤の太矢印 ↓ |

`payload.risk_level` が `MEDIUM`（Absorption 検出中）や `HIGH`（確信度不足）の場合は、シグナルの信頼度が低いことを示しています。

---

## ユースケース 6: ETHUSDT など別の通貨ペアを分析したい

**やりたいこと**: BTCUSDT 以外の通貨ペアを分析したい。

**手順**: `config\config.yaml` の 2 箇所を書き換える。

```yaml
market:
  symbol: ETHUSDT

websocket:
  subscribe_streams:
    - "ethusdt@aggTrade"
    - "ethusdt@depth@100ms"
```

ストリーム名は全て小文字で書いてください。書き換えたら §2 以降の手順はそのまま使えます。
