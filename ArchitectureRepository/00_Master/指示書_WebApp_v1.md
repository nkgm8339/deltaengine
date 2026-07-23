# 指示書_WebApp_v1

この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

---

## 0. 目的

DeltaEngine バックエンド（207 tests passed）に WebApp 層を追加する。  
`docker-compose up` 一発で `http://localhost:8080` からブラウザダッシュボードが使える状態にする。

**正本（ArchitectureRepository/）は無変更。**  
**既存 207 テストは無影響。**

---

## 1. 追加ファイル構成

```text
project/
├── webapp/
│   ├── main.py            # FastAPI アプリ + WebSocket エンドポイント
│   ├── broker.py          # PushBroker（Pipeline → WebSocket クライアント配信）
│   ├── oi_poller.py       # OI/Funding Rate 定期ポーリング（REST）
│   └── static/
│       └── index.html     # ブラウザダッシュボード（単一ファイル）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt       # webapp 依存追記（fastapi uvicorn[standard]）
```

---

## 2. PushBroker（`webapp/broker.py`）

```python
class PushBroker:
    """Pipeline コールバック → 接続中 WebSocket クライアント全員へ broadcast。"""

    def __init__(self): ...

    async def broadcast(self, msg: dict) -> None:
        """JSON シリアライズして全クライアントへ送信。切断済みは自動除去。"""

    async def connect(self, ws: WebSocket) -> None: ...
    async def disconnect(self, ws: WebSocket) -> None: ...
```

スレッドセーフ: `asyncio.Lock` で `_clients: set[WebSocket]` を保護。

---

## 3. OI Poller（`webapp/oi_poller.py`）

```python
async def oi_polling_loop(broker: PushBroker, symbol: str, interval_sec: int = 10) -> None:
    """
    fetch_open_interest() + fetch_premium_index() を interval_sec 毎に呼ぶ。
    取得成功時に broker.broadcast({
        "type": "OI",
        "open_interest": str,   # Decimal → str
        "funding_rate": str,
        "next_funding_time": int,
    }) を送信。
    失敗時は warning log して継続。
    """
```

---

## 4. FastAPI アプリ（`webapp/main.py`）

### 4.1 起動フロー

```
@app.on_event("startup")
1. Config + Profile 読み込み
2. PushBroker 初期化
3. LivePipeline 構築（コールバック登録：on_trade / on_candle / on_analysis / on_liquidation）
4. asyncio.create_task(pipeline.run_async())
5. asyncio.create_task(oi_polling_loop(broker, symbol))
```

### 4.2 コールバック → broadcast メッセージ形式

| コールバック | type | 主要フィールド |
|---|---|---|
| on_trade | `TICK` | price, quantity, side, event_time, cvd, footprint_snapshot |
| on_candle | `CANDLE` | bar_time, open, high, low, close, volume, delta, cvd, imbalance, signal, analysis |
| on_analysis | `ANALYSIS` | market_state, risk_level, confidence, reasons |
| on_liquidation | `LIQUIDATION` | side, price, quantity, long_liq_notional, short_liq_notional |
| oi_poller | `OI` | open_interest, funding_rate, next_funding_time |

全フィールドは Decimal → str 変換してから JSON シリアライズ。

### 4.3 エンドポイント

```
GET  /              → static/index.html
WS   /ws            → PushBroker.connect() → 接続維持 → disconnect()
GET  /health        → {"status": "ok", "tests_passed": 207}
GET  /api/stats     → pipeline の LiveStats 現在値（JSON）
```

### 4.4 静的ファイル配信

`fastapi.staticfiles.StaticFiles` で `webapp/static/` をマウント。

---

## 5. index.html（`webapp/static/index.html`）

`delta_command_center_v2.html`（UI設計済み）をベースに、以下を追加する。

### 5.1 WebSocket 接続

```javascript
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    dispatch(msg);
};
```

### 5.2 dispatch ルーティング

```javascript
function dispatch(msg) {
    switch (msg.type) {
        case "TICK":       updateTick(msg); break;
        case "CANDLE":     updateCandle(msg); break;
        case "ANALYSIS":   updateAnalysis(msg); break;
        case "LIQUIDATION": updateLiquidation(msg); break;
        case "OI":         updateOI(msg); break;
    }
}
```

### 5.3 各更新関数（最小実装）

| 関数 | 更新対象 DOM |
|---|---|
| `updateTick(msg)` | ヘッダー価格・CVD累積値・Footprintセル |
| `updateCandle(msg)` | OHLCV行・Delta値・Signal表示・AI市場状態 |
| `updateAnalysis(msg)` | AI Command パネル（market_state / risk_level / confidence / reasons） |
| `updateLiquidation(msg)` | Liquidation パネル（notional累計・直近リスト） |
| `updateOI(msg)` | OI パネル（open_interest / funding_rate / next_funding_time） |

DOM要素には `id` を付与して `document.getElementById` で直接更新。再描画は最小限。

---

## 6. Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 7. docker-compose.yml

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

## 8. requirements.txt 追記

既存の内容に以下を追記（既存行は変更しない）:

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
```

---

## 9. テスト

新規 `tests/webapp/test_broker.py`（3本）:

1. `PushBroker.broadcast` — 接続中クライアントに届く
2. `PushBroker.broadcast` — 切断済みクライアントは自動除去
3. `GET /health` → 200 + `{"status": "ok"}`

新規 `tests/webapp/test_oi_poller.py`（2本）:

1. `oi_polling_loop` — fetch 成功時に broker.broadcast が呼ばれる
2. `oi_polling_loop` — fetch 失敗時に例外を握り潰して継続

合計: 207 + 5 = **212 本以上 green**

---

## 10. 完了条件

- [ ] 212 本以上 green、既存 207 本無影響
- [ ] `docker-compose up` で起動し `http://localhost:8080` にアクセスできる
- [ ] ブラウザ上で価格・CVD・AI状態がリアルタイム更新される
- [ ] OI パネルが実数値を表示する（PENDING が消える）
- [ ] 正本（ArchitectureRepository/）無変更
- [ ] Decimal 禁則スキャン: `webapp/` に `float(` 呼び出し 0 件

---

## 11. 報告

`ArchitectureRepository/00_Master/CompletionLog.md` に完了エントリ追記。  
`DeltaEngine_WebApp_完了.zip`（プロジェクト全体、`__pycache__` / `.pytest_cache` / `data/` バイナリ除外）を提出。  
チャット報告: テスト件数・Docker起動確認・OI実数値確認・逸脱有無。
