この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_MarketData拡張_v1

**対象**: Binance から取得可能な市場データの追加 2 件
1. Liquidation ストリーム（`@forceOrder`）のパイプライン組み込み
2. REST 市場データ取得関数（OI・Funding・Mark Price・24h統計）

**スコープ外**: ウェブアプリ、FastAPI、ダッシュボード、Docker（すべて後続指示書）

**前提**: 直近の pytest 全数 green を起点とする

---

## 0. 設計決定（逸脱禁止）

| # | 決定 | 内容 |
|---|------|------|
| 1 | Liquidation 永続化 | しない。in-memory リングバッファ（直近 200 件）+ 累計統計のみ。DuckDB/Parquet スキーマ変更禁止 |
| 2 | REST 関数の位置づけ | 取得関数の実装とテストのみ。ポーリングループ・呼び出し側の組み込みは後続指示書（ウェブアプリ）で行う |
| 3 | broadcast フック | パイプラインに Optional コールバックを追加（デフォルト None、既存動作無変更）。後続のウェブアプリが接続する |

---

## 1. Liquidation ストリーム

### 1-1. `config/config.yaml`

`subscribe_streams` に追加:

```yaml
    - "btcusdt@forceOrder"
```

### 1-2. `src/acquisition/binance_ws.py`

`is_agg_trade_or_depth` を拡張:

```python
    return message.get("e") in ("aggTrade", "trade", "depthUpdate", "forceOrder")
```

docstring に forceOrder（清算注文ストリーム）を追記。関数名は互換性のため変更しない。

### 1-3. `src/normalization/normalizer.py`

Binance `forceOrder` ペイロードは `{"e":"forceOrder","E":...,"o":{...}}` 形式。`o` 内に `s`(symbol), `S`(side), `p`(price), `q`(qty), `T`(time) を持つ。

追加:
- `LiquidationEvent`（frozen dataclass）: `event_time: datetime, symbol: str, side: str, price: Decimal, quantity: Decimal`
- `classify_raw` に `"liquidation"` 分類を追加（`e == "forceOrder"`）
- `normalize_raw_liquidation(raw, profile) -> LiquidationEvent`

Decimal 禁則（float() 呼び出し禁止）を厳守。

`side` の意味をコード内コメントに明記: forceOrder の `S` は清算**注文**の売買方向。`SELL` = ロング清算、`BUY` = ショート清算。

### 1-4. `src/pipeline.py`（LivePipeline）

- `liquidation_buffer: deque(maxlen=200)` を追加
- 累計統計 `long_liq_notional: Decimal` / `short_liq_notional: Decimal`（price × quantity 累計）を追加
- normalized ループで classify が `"liquidation"` の場合、バッファ追加 + 統計更新（trade/depth 経路には流さない）
- `LiveStats` に `liquidations_received: int` を追加
- broadcast フック 4 本を追加: `on_trade`, `on_candle`, `on_analysis`, `on_liquidation`（各 `Optional[Callable]`、デフォルト None、None なら呼ばない、既存動作無変更）

---

## 2. REST 市場データ

### 2-1. `src/acquisition/binance_rest.py` に追加

```python
async def fetch_open_interest(symbol: str) -> dict      # GET /fapi/v1/openInterest
async def fetch_premium_index(symbol: str) -> dict      # GET /fapi/v1/premiumIndex
async def fetch_ticker_24hr(symbol: str) -> dict        # GET /fapi/v1/ticker/24hr
```

- 既存の `fetch_depth_snapshot` と同じ aiohttp パターン・エラーハンドリングに従う
- 数値は API が返す文字列のまま返す。float 変換禁止（呼び出し側で Decimal 化する）
- 呼び出し側への組み込みは行わない（決定 #2）

---

## 3. テスト

### 追加テスト（最低 8 本）

1. `tests/normalization/test_normalizer_liquidation.py`（新規 3 本）:
   - forceOrder 正常系（LiquidationEvent の全フィールド検証）
   - 必須フィールド欠損で NormalizationError
   - classify_raw が forceOrder を `"liquidation"` と分類
2. `tests/acquisition/test_binance_rest.py`（追記 3 本）:
   - fetch_open_interest / fetch_premium_index / fetch_ticker_24hr（mock aiohttp、既存 snapshot テストのパターン踏襲）
3. `tests/test_live_pipeline.py`（追記 2 本）:
   - 注入 forceOrder イベントがバッファ・統計・`liquidations_received` に反映される
   - `on_liquidation` フックが呼ばれる / None のとき何も起きない

既存テストは無変更（フックはデフォルト None のため影響なし）。

### 実ネットワーク確認

`python -m tools.live_verify --duration 60` を実行し、`liquidations_received` カウンタが機能していることを確認（60 秒で 0 件の場合は購読確立ログで代替可。ログに forceOrder ストリームが subscribe params に含まれることを示すこと）。

---

## 4. 制約

- 正本無変更
- DuckDB/Parquet スキーマ無変更
- Decimal 禁則: 新規コード全域で float() 呼び出し 0 件
- 既存テスト無影響

---

## 5. 報告

CompletionLog.md 追記 + `DeltaEngine_MarketData_完了.zip`（**プロジェクト全体**。差分のみは不可）+ pytest 全数ログ + live_verify 実行ログ
