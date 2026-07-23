この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_WebApp_v2

**対象**: DeltaEngine 全機能統合 WebApp 層の実装  
**前提**: MarketData拡張_v1 完了（221 tests passed）。`src/acquisition/binance_rest.py` に `fetch_open_interest` / `fetch_premium_index` / `fetch_ticker_24hr` 実装済み。`src/pipeline.py` に `on_trade` / `on_candle` / `on_analysis` / `on_liquidation` broadcast フック実装済み（Optional[Callable]、デフォルト None）。  
**正本（ArchitectureRepository/）は無変更。**  
**既存 221 テストは無影響。**

---

## 0. 設計決定（逸脱禁止）

| # | 決定 | 内容 |
|---|------|------|
| 1 | OI/Funding/MarkPrice/Ticker ポーリング | `webapp/market_poller.py` 単一ループ。`oi_poll_interval_sec`（デフォルト 10）で OI + premiumIndex + ticker_24hr を同時取得し broker broadcast。config.yaml に `webapp` セクションを追加 |
| 2 | Liquidation in-memory 参照 | pipeline の `liquidation_buffer` / `long_liq_notional` / `short_liq_notional` をブロードキャスト。永続化なし（ADR-008 厳守） |
| 3 | Order Book スナップショット配信 | `on_candle` コールバック時に `pipeline.book_state.snapshot()` を取得し `bids` / `asks` 上位 10 レベルを CANDLE メッセージに同梱 |
| 4 | MT5 制御 | config の `mt5.enabled` を `/api/config` でブラウザから参照のみ（動的切替なし。変更は config.yaml 再起動で対応） |
| 5 | 履歴照会 | DuckDB の `trades` / `candles` / `signals` テーブルを REST で照会。接続は `duckdb.connect(read_only=True)` |
| 6 | config 書き換え API | 実装しない。起動パラメータはブラウザ表示のみ |
| 7 | Replay | FastAPI startup 時に `config.replay.enabled` を確認し、`true` なら `ReplayPipeline` を起動 |
| 8 | float 禁則 | `webapp/` 全域で `float()` 呼び出し 0 件。Decimal → `str()` でシリアライズ |

---

## 1. 追加ファイル構成

```text
（プロジェクトルート）/
├── webapp/
│   ├── __init__.py          # 空
│   ├── main.py              # FastAPI アプリ本体
│   ├── broker.py            # PushBroker（WebSocket broadcast）
│   ├── market_poller.py     # OI/Funding/MarkPrice/Ticker ポーリングループ
│   ├── history.py           # DuckDB 履歴照会ヘルパー
│   └── static/
│       └── index.html       # ブラウザダッシュボード（単一ファイル）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt         # 既存に fastapi / uvicorn[standard] を追記
```

`config/config.yaml` に `webapp` セクションを追加（§2.1）。

---

## 2. config.yaml 追記

`mt5:` セクションの直後に追加:

```yaml
webapp:
  host: 0.0.0.0
  port: 8080
  oi_poll_interval_sec: 10
```

`config.py` の `WebAppConfig` dataclass を追加:

```python
@dataclass
class WebAppConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    oi_poll_interval_sec: int = 10
```

`AppConfig` に `webapp: WebAppConfig = field(default_factory=WebAppConfig)` を追加。  
既存 config 読み込みロジックに `webapp` セクション読み込みを追加（他セクションと同一パターン）。

---

## 3. PushBroker（`webapp/broker.py`）

```python
from __future__ import annotations
import asyncio
from fastapi import WebSocket

class PushBroker:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, msg: dict) -> None:
        """JSON シリアライズして全クライアントへ送信。切断済みは自動除去。"""
        import json
        text = json.dumps(msg, ensure_ascii=False)
        dead: list[WebSocket] = []
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
```

---

## 4. Market Poller（`webapp/market_poller.py`）

```python
async def market_polling_loop(
    broker: PushBroker,
    symbol: str,
    interval_sec: int,
) -> None:
    """
    fetch_open_interest + fetch_premium_index + fetch_ticker_24hr を
    interval_sec 毎に同時呼び出し。

    broadcast メッセージ形式:
    {
        "type": "MARKET",
        "open_interest": str,         # Decimal → str
        "mark_price": str,
        "funding_rate": str,
        "next_funding_time": int,     # epoch ms
        "price_change_pct": str,      # 24h 変動率
        "volume_24h": str,            # 24h 出来高
        "quote_volume_24h": str,      # 24h 出来高 USDT
    }
    失敗時は warning log して継続（ループ停止しない）。
    """
```

`fetch_open_interest` / `fetch_premium_index` / `fetch_ticker_24hr` は `src/acquisition/binance_rest.py` の実装をそのまま import する。数値フィールドは `Decimal(str(v))` 経由で変換し str() でシリアライズ（float() 禁止）。

---

## 5. 履歴照会（`webapp/history.py`）

```python
import duckdb
from pathlib import Path

def query_candles(db_path: str, symbol: str, limit: int = 200) -> list[dict]:
    """
    candles テーブルから最新 limit 件を取得。
    返り値: [{bar_time, open, high, low, close, volume, delta, cvd}, ...]
    全数値は str 型（Decimal→str）。
    """

def query_signals(db_path: str, symbol: str, limit: int = 200) -> list[dict]:
    """
    signals テーブルから最新 limit 件を取得。
    返り値: [{signal_time, signal, confidence, reason}, ...]
    """

def query_trades(db_path: str, symbol: str, limit: int = 500) -> list[dict]:
    """
    trades テーブルから最新 limit 件を取得。
    返り値: [{event_time, price, quantity, side}, ...]
    """
```

接続は `duckdb.connect(db_path, read_only=True)` を使用。接続は関数呼び出し毎に open/close（ロック競合回避）。

---

## 6. FastAPI アプリ（`webapp/main.py`）

### 6.1 起動フロー（`@asynccontextmanager lifespan`）

```
1. AppConfig.from_yaml("config/config.yaml") 読み込み
2. PushBroker 初期化
3. replay.enabled に応じて LivePipeline or ReplayPipeline を選択
4. コールバック登録（§6.2）
5. asyncio.create_task(pipeline.run_async())          # Live
   または asyncio.create_task(_run_replay(pipeline))  # Replay
6. asyncio.create_task(market_polling_loop(broker, symbol, interval_sec))
7. （yield — FastAPI サービング）
8. shutdown: pipeline タスク cancel → join
```

### 6.2 コールバック登録

| フック | type | 主要フィールド |
|--------|------|---------------|
| `on_trade` | `TICK` | event_time, price, quantity, side, tick_cvd, tick_delta |
| `on_candle` | `CANDLE` | bar_time, open, high, low, close, volume, delta, cvd, imbalance_buy, imbalance_sell, stacked_imbalances, absorption_direction, absorption_strength, signal, confidence, signal_reason, market_state, risk_level, analysis_confidence, book_bids（上位10）, book_asks（上位10）, volume_ref |
| `on_analysis` | `ANALYSIS` | analysis_time, market_state, risk_level, summary, confidence |
| `on_liquidation` | `LIQUIDATION` | event_time, side, price, quantity, long_liq_notional, short_liq_notional, buffer_size |

全フィールドは Decimal → `str()` 変換後 JSON シリアライズ。コールバック内で `asyncio.create_task(broker.broadcast(msg))` を呼ぶ。

`on_candle` で Order Book スナップショットを取得する方法:  
`pipeline.book_manager.snapshot()` が存在すれば上位 10 件（bid 降順 / ask 昇順）を dict list に変換して同梱。存在しなければ空リスト。

`on_candle` で volume_ref を取得する方法:  
`pipeline.volume_ref_tracker.current()` が None でなければ str() 変換して同梱。None なら `null`。

### 6.3 エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| `GET` | `/` | `webapp/static/index.html` を返す |
| `WS` | `/ws` | PushBroker.connect() → 接続維持 → disconnect() |
| `GET` | `/health` | `{"status": "ok", "tests_passed": 221}` |
| `GET` | `/api/stats` | pipeline の LiveStats / ReplayStats 現在値（JSON）。Decimal → str |
| `GET` | `/api/config` | AppConfig を JSON で返す（パスワード等のフィールドなし） |
| `GET` | `/api/history/candles` | `?symbol=BTCUSDT&limit=200` → candles 一覧 |
| `GET` | `/api/history/signals` | `?symbol=BTCUSDT&limit=200` → signals 一覧 |
| `GET` | `/api/history/trades` | `?symbol=BTCUSDT&limit=500` → trades 一覧 |

`StaticFiles` で `webapp/static/` を `/static` にマウント。

---

## 7. index.html（`webapp/static/index.html`）

単一 HTML ファイル。外部 CDN 不使用（ネットワーク依存排除）。Canvas 2D で Footprint を描画。CSS は `<style>` 内インライン。

### 7.1 3カラム固定レイアウト

人間工学に基づく判断フロー（マクロ環境認識 → 圧力確認 → エントリー判断）に沿った縦動線:

```
┌────────────────────┬───────────────────────┬──────────────────┐
│ 【左】環境認識      │ 【中央】メイン注視      │ 【右】判断        │
├────────────────────┼───────────────────────┼──────────────────┤
│ OI パネル          │ Footprint Chart        │ Signal パネル    │
│  - open_interest   │  (Canvas 2D)           │  BUY/SELL/WAIT   │
│  - OI変化量        │  価格軸左固定           │  composite score │
│                    │  BUY=緑 SELL=赤         │  confidence bar  │
│ Funding パネル     │  Imbalance マーカー     │  veto 理由       │
│  - funding_rate    │  (Footprint に重畳)     │                  │
│  - next_funding    │                         │ AI Analysis      │
│  - mark_price      │ CVD ライン              │  market_state    │
│                    │  (Footprintと価格軸共有) │  risk_level      │
│ 24h Ticker         │                         │  summary         │
│  - price_change%   │ Stacked Imbalance       │  confidence      │
│  - volume_24h      │  マーカー               │                  │
│  - quote_vol_24h   │                         │ Absorption       │
│                    │                         │  direction       │
│ Mark Price         │                         │  strength bar    │
│                    │                         │                  │
│ Liquidation        │                         │ volume_ref       │
│  - long_liq_notional│                        │  現在値          │
│  - short_liq_notional│                       │                  │
│  - 直近リスト       │                        │ MT5 状態         │
│    (最新5件)        │                        │  (config 表示)   │
├────────────────────┼───────────────────────┼──────────────────┤
│ Order Book         │ 統計 / エラーログ       │ 制御パネル        │
│  Bid/Ask ヒートマップ│ normalized件数         │ Live/Stop ボタン │
│  (上位10レベル)     │ candles/signals         │ Replay モード    │
│  価格・数量         │ book_diffs_applied      │ config 表示      │
│                    │ liquidations_received   │                  │
│                    │ analysis_count          │                  │
│                    │ エラーログ（直近10件）   │                  │
└────────────────────┴───────────────────────┴──────────────────┘
```

### 7.2 DOM 構造（主要 ID）

```html
<!-- 左カラム -->
<div id="oi-value">       <!-- OI 数値 -->
<div id="oi-change">      <!-- OI 変化量（前回比） -->
<div id="funding-rate">
<div id="next-funding">
<div id="mark-price">
<div id="price-change-pct">
<div id="volume-24h">
<div id="quote-vol-24h">
<div id="long-liq-notional">
<div id="short-liq-notional">
<div id="liq-list">       <!-- 直近5件リスト -->

<!-- 中央カラム -->
<canvas id="footprint-canvas">   <!-- Footprint + Imbalance + CVD -->

<!-- 右カラム -->
<div id="signal-label">          <!-- BUY / SELL / WAIT -->
<div id="signal-composite">      <!-- composite score -->
<div id="confidence-bar">        <!-- <progress> で表現 -->
<div id="signal-reason">         <!-- LOW_CONFIDENCE / ABSORPTION_VETO / NO_INPUT -->
<div id="market-state">
<div id="risk-level">
<div id="analysis-summary">
<div id="analysis-confidence">
<div id="absorption-direction">
<div id="absorption-strength-bar">
<div id="volume-ref-value">
<div id="mt5-status">

<!-- 下段左 -->
<div id="book-bids">             <!-- Bid ヒートマップ（上位10） -->
<div id="book-asks">             <!-- Ask ヒートマップ（上位10） -->

<!-- 下段中央 -->
<div id="stats-normalized">
<div id="stats-candles">
<div id="stats-signals">
<div id="stats-book-diffs">
<div id="stats-liquidations">
<div id="stats-analysis">
<div id="error-log">             <!-- <ul> 直近10件 -->

<!-- 下段右 -->
<button id="btn-live">Live Start</button>  <!-- /api/control/start POST -->
<button id="btn-stop">Stop</button>        <!-- /api/control/stop POST (将来) -->
<div id="config-display">                  <!-- /api/config から取得して表示 -->
```

### 7.3 WebSocket 接続と dispatch

```javascript
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = (e) => dispatch(JSON.parse(e.data));

function dispatch(msg) {
    switch (msg.type) {
        case "TICK":        updateTick(msg);        break;
        case "CANDLE":      updateCandle(msg);      break;
        case "ANALYSIS":    updateAnalysis(msg);    break;
        case "LIQUIDATION": updateLiquidation(msg); break;
        case "MARKET":      updateMarket(msg);      break;
    }
}
```

### 7.4 各更新関数の責務

| 関数 | 更新対象 |
|------|---------|
| `updateTick(msg)` | tick_cvd / tick_delta のティッカー表示 |
| `updateCandle(msg)` | Footprint Canvas 再描画、CVD ライン更新、Imbalance マーカー、Signal・Absorption・AI Analysis パネル全更新、Order Book ヒートマップ、volume_ref、統計カウンタ |
| `updateAnalysis(msg)` | AI Analysis パネル（market_state / risk_level / summary / confidence）|
| `updateLiquidation(msg)` | long/short_liq_notional、直近リスト（最新5件 prepend、6件目以降 trim） |
| `updateMarket(msg)` | OI / OI変化量 / funding_rate / next_funding / mark_price / 24h 統計全更新 |

### 7.5 Footprint Canvas 描画仕様

- 直近 N 本（デフォルト 20）の `FootprintBar` を保持するリングバッファ（JS 配列）
- 各 bar: 縦軸 = 価格（上が高値）、横軸 = bar index
- セル: BUY 出来高（緑）/ SELL 出来高（赤）を左右に並べて表示
- Imbalance マーカー: qualify セルに矢印アイコン（▲買 / ▼売 / ◆スタック）を重畳
- CVD ライン: 同一 canvas に overlay（右軸 / 折れ線）
- セルサイズは canvas 高さ / 表示価格レベル数で自動計算
- `updateCandle` 毎に `ctx.clearRect` → 全再描画（部分更新なし、シンプル実装優先）

### 7.6 履歴ロード

ページ初期表示時に以下を順番に実行:

```javascript
fetch('/api/history/candles?symbol=BTCUSDT&limit=20')
    .then(r => r.json())
    .then(bars => { /* Footprint リングバッファ初期化 */ });

fetch('/api/history/signals?symbol=BTCUSDT&limit=5')
    .then(r => r.json())
    .then(sigs => { /* Signal 履歴テーブル表示 */ });

fetch('/api/config')
    .then(r => r.json())
    .then(cfg => { /* config-display DOM 更新 */ });
```

---

## 8. Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 9. docker-compose.yml

```yaml
version: "3.9"
services:
  deltaengine:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
```

`./data` をマウントすることで Parquet/DuckDB がコンテナ外に永続化される。

---

## 10. requirements.txt 追記

既存行は変更しない。末尾に追記:

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
```

---

## 11. テスト

新規ファイル `tests/webapp/` ディレクトリを作成し以下を実装:

### `tests/webapp/__init__.py`（空）

### `tests/webapp/test_broker.py`（3本）

1. `test_broadcast_reaches_connected_client` — connect 後 broadcast → client が受信
2. `test_broadcast_removes_dead_client` — 切断済み WebSocket が自動除去される
3. `test_disconnect_removes_client` — disconnect() 後 _clients から除去されている

### `tests/webapp/test_market_poller.py`（2本）

1. `test_market_polling_broadcasts_on_success` — fetch 関数 mock 成功時に broker.broadcast が MARKET メッセージで呼ばれる
2. `test_market_polling_continues_on_fetch_error` — fetch 関数が例外を発生させても次のポーリングが実行される（ループ停止しない）

### `tests/webapp/test_history.py`（3本）

1. `test_query_candles_returns_list` — インメモリ DuckDB にサンプルデータを insert して query_candles が list[dict] を返す
2. `test_query_signals_returns_list` — 同様に query_signals
3. `test_query_trades_returns_list` — 同様に query_trades

### `tests/webapp/test_api.py`（3本）

TestClient（`from fastapi.testclient import TestClient`）を使用。

1. `test_health_ok` — `GET /health` → 200、`{"status": "ok"}` を含む
2. `test_stats_ok` — `GET /api/stats` → 200、JSON レスポンス
3. `test_config_ok` — `GET /api/config` → 200、`webapp` キーを含む

TestClient 使用時は pipeline 起動を mock する（実 WebSocket 接続不要）。

**合計: 221 + 11 = 232 本以上 green**

---

## 12. 完了条件

- [ ] 232 本以上 green（既存 221 本無影響）
- [ ] `docker-compose up` で起動し `http://localhost:8080` にアクセスできる
- [ ] 3カラムレイアウトで全パネルが表示される
- [ ] Footprint Canvas に価格レベル別 BUY/SELL が描画される
- [ ] OI / Funding / Mark Price / Ticker パネルが数値を表示する（PENDING が消える）
- [ ] Liquidation パネルが long/short notional を表示する
- [ ] Signal（BUY/SELL/WAIT + veto 理由 + confidence）が表示される
- [ ] Order Book ヒートマップ（上位10）が表示される
- [ ] 履歴ロード（candles / signals）がページ初期表示時に実行される
- [ ] float() 禁則: `webapp/` に `float(` 呼び出し 0 件
- [ ] 正本（ArchitectureRepository/）無変更

---

## 13. 報告

`ArchitectureRepository/00_Master/CompletionLog.md` に完了エントリ追記。  
`DeltaEngine_WebApp_完了.zip`（プロジェクト全体、`__pycache__` / `.pytest_cache` / `data/` バイナリ除外）を提出。  
チャット報告: テスト件数・Docker起動確認・全パネル表示確認・逸脱有無。
