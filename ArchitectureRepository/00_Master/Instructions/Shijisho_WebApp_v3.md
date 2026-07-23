この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_WebApp_v3

**対象**: WebApp層（FastAPI + WebSocket + ブラウザUI + Docker）
**参照**: WebSocketPayload仕様_v1 / UI仕様書_CommandCenter_v1（本指示書と同時に提供される。3点セットで正とする）
**前提**: 221 passed。broadcast hooks（on_trade / on_candle / on_analysis / on_liquidation）実装済み。
**本指示書は 指示書_WebApp_v2 を全面的に置換する。v2は破棄。**

---

# 0. ミッションと三原則（全実装がこれに従属する）

> **本WebAppは「トレーダーが3秒以内に状況を把握し、売買判断できるコマンドセンター」である。データ表示ツールではない。**

1. **固定値・ダミー値禁止**: UIコード内に数値リテラルのダミー値を置かない。全値はWebSocket Payload由来。Payloadに無い値は「—」を描画する
2. **UI ≠ ドメインモデル**: signal / market_state / risk_level / veto はPayload文字列をそのまま描画。UI側の列挙・再分類・マッピング禁止
3. **SignalEngineが唯一の判定主体**: UIは判定計算を一切行わない。サーバー側派生値（confluence / scores.flow）はWebSocketPayload仕様_v1 §5 の固定式のみ

**禁則**: `float(` はwebapp/全域で禁止（Decimal→str変換のみ）。正本ドキュメント無変更。

---

# 1. スコープ

## 含む
- `webapp/` 新規実装（main.py / push_broker.py / oi_poller.py / static/index.html）
- pipeline への `on_flow_event` hook 追加（FLOW配信、v1はIMBALANCE/ABSORPTIONのみ）
- config `webapp` セクション追加
- Dockerfile / docker-compose.yml
- テスト14本（221 → **235**）

## 含まない（将来ADR。番号は予約済み。実装するな）

| 項目 | 決定の場 |
|---|---|
| signal 4値化（LONG/SHORT/WAIT/AVOID等） | ADR-008（予約） |
| market_state再定義 | ADR-009（予約） |
| Expected RR算出 | ADR-010（予約） |
| EconomicEventProvider（FOMC等） | ADR-011（予約） |
| DELTA / EXHAUSTION / ICEBERG Detector | ADR-012（予約） |
| MT5動的切替 | 別途整理タスク |

半年後に「なぜ実装されていないのか」と迷わないため、各項目の決定場所を上表で固定する。予約番号は起草時に正式採番と照合すること。

---

# 2. config 追加（config.yaml / config.py）

```yaml
webapp:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  depth_levels: 15
  flow_window_sec: 60
  alert_threshold: 0.85
  confluence:
    score_threshold: 40
    strength_threshold: 0.5
```

config.py に対応スキーマとバリデーション（port 1–65535、threshold 0–1 等）を追加。既存セクションは無変更。

---

# 3. pipeline: on_flow_event hook

既存 broadcast hooks と同形式で `on_flow_event: Callable[[FlowEvent], Awaitable[None]] | None` を追加する。

```python
@dataclass(frozen=True)
class FlowEvent:
    event_time: datetime
    symbol: str
    category: str    # "IMBALANCE" | "ABSORPTION"（v1）
    side: str        # "BUY" | "SELL"
    strength: Decimal  # 0–1
    detector: str    # "ImbalanceDetector" | "AbsorptionDetector"
    detail: str
```

発火点（2箇所のみ。他のDetector発火点を追加するな）:

1. **IMBALANCE**: `_evaluate_and_store` にて ImbalanceResult の stacked_imbalances が1件以上のとき、BUY方向・SELL方向それぞれについて `net = Σcount` を集計し、方向ごとに1イベント発火。`strength = min(net / stack_ref, 1)`（M11 決定10と同一分母）。`detail = f"stacked_count={net}"`
2. **ABSORPTION**: AbsorptionTracker の `events_detected` カウンタが増分した tick で発火（増分検知方式。ポーリングではなく update 戻り値/カウンタ比較で決定的に）。side は classification が BUY_ABSORPTION なら "BUY"、SELL_ABSORPTION なら "SELL"。strength は AbsorptionResult.strength。`detail = f"window_sec={window_sec}"`

hook未設定（None）時は完全に無害（既存リプレイ決定性に影響ゼロ）であること。

---

# 4. webapp/push_broker.py

```python
"""PushBroker: pipeline hooks → WebSocket clients. Payload組立の唯一の場所。

WebSocketPayload仕様_v1 に完全準拠。数値は全て str(Decimal)。float() 禁止。
"""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

PAYLOAD_VERSION = 1


def d2s(v: Optional[Decimal]) -> Optional[str]:
    """Decimal → str（None透過）。floatは受け付けない。"""
    if v is None:
        return None
    if not isinstance(v, (Decimal, int)):
        raise TypeError(f"d2s expects Decimal/int/None, got {type(v)}")
    return str(v)


def envelope(msg_type: str, time_: datetime, symbol: str, payload: dict) -> dict:
    return {
        "v": PAYLOAD_VERSION,
        "type": msg_type,
        "time": time_.astimezone(timezone.utc).isoformat(),
        "symbol": symbol,
        "payload": payload,
    }


def compute_value_area(levels: list[dict]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """POC/VAH/VAL（WebSocketPayload仕様_v1 §4.3）。levelsは価格降順、各要素 Decimal。

    Returns (poc_price, vah_price, val_price) as str or (None, None, None)."""
    if not levels:
        return None, None, None
    totals = [(lv["price"], lv["bid"] + lv["ask"]) for lv in levels]
    poc_i = 0
    for i, (_, tot) in enumerate(totals):
        if tot > totals[poc_i][1]:  # 同値なら先勝ち＝価格が高い方（降順のため）
            poc_i = i
    grand = sum(t for _, t in totals)
    target = grand * Decimal("0.7")
    lo = hi = poc_i
    acc = totals[poc_i][1]
    while acc < target and (hi > 0 or lo < len(totals) - 1):
        up = totals[hi - 1][1] if hi > 0 else Decimal("-1")
        dn = totals[lo + 1][1] if lo < len(totals) - 1 else Decimal("-1")
        if up >= dn:
            hi -= 1
            acc += up
        else:
            lo += 1
            acc += dn
    return str(totals[poc_i][0]), str(totals[hi][0]), str(totals[lo][0])


@dataclass
class _FlowRecord:
    event_time: datetime
    strength: Decimal


class PushBroker:
    """WebSocketクライアント管理とPayload配信。asyncio単一ループ（ADR-003）。"""

    def __init__(
        self,
        symbol: str,
        depth_levels: int = 15,
        flow_window_sec: int = 60,
        confluence_score_threshold: Decimal = Decimal("40"),
        confluence_strength_threshold: Decimal = Decimal("0.5"),
    ) -> None:
        self.symbol = symbol
        self.depth_levels = depth_levels
        self.flow_window_sec = flow_window_sec
        self.conf_score_th = confluence_score_threshold
        self.conf_strength_th = confluence_strength_threshold
        self._clients: set[Any] = set()  # WebSocket接続
        self._flow_history: list[_FlowRecord] = []
        self._lock = asyncio.Lock()

    # ---------- client管理 ----------
    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def _broadcast(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        async with self._lock:
            dead = []
            for ws in self._clients:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    # ---------- 派生値（WebSocketPayload仕様_v1 §5。UIに置かない） ----------
    def flow_score(self, now: datetime) -> Optional[Decimal]:
        cutoff = self.flow_window_sec
        num = Decimal("0")
        den = Decimal("0")
        kept: list[_FlowRecord] = []
        for rec in self._flow_history:
            age = (now - rec.event_time).total_seconds()
            if age <= cutoff:
                w = Decimal(str(math.pow(0.5, age / 30.0)))  # 定数指数のみ、市場値のfloat化ではない
                num += rec.strength * w
                den += w
                kept.append(rec)
        self._flow_history = kept
        if den == 0:
            return None
        return (num / den).quantize(Decimal("0.0001"))

    def confluence(
        self,
        signal: str,
        scores: dict[str, Optional[Decimal]],
    ) -> dict:
        if signal == "WAIT":
            flags = {k: False for k in ("cvd", "footprint", "imbalance", "absorption", "flow")}
            return {**flags, "count": 0}
        sign = Decimal("1") if signal == "BUY" else Decimal("-1")

        def directional(v: Optional[Decimal]) -> bool:
            return v is not None and v * sign >= self.conf_score_th

        flags = {
            "cvd": directional(scores.get("cvd")),
            "footprint": directional(scores.get("footprint")),
            "imbalance": directional(scores.get("imbalance")),
            "absorption": scores.get("absorption") is not None
            and scores["absorption"] >= self.conf_strength_th,
            "flow": scores.get("flow") is not None
            and scores["flow"] >= self.conf_strength_th,
        }
        return {**flags, "count": sum(flags.values())}

    # ---------- hooks（pipelineから呼ばれる） ----------
    async def on_trade(self, trade) -> None:
        await self._broadcast(envelope("TICK", trade.event_time, self.symbol, {
            "price": d2s(trade.price),
            "quantity": d2s(trade.quantity),
            "side": trade.side,
            "tick_delta": d2s(getattr(trade, "tick_delta", None)),
            "tick_cvd": d2s(getattr(trade, "tick_cvd", None)),
        }))

    async def on_candle(self, candle, footprint_levels, orderbook_snapshot) -> None:
        levels = [
            {"price": lv["price"], "bid": lv["bid"], "ask": lv["ask"]}
            for lv in footprint_levels
        ]
        poc, vah, val = compute_value_area(levels)
        book = {"last_update_id": None, "bids": [], "asks": [],
                "depth_levels": self.depth_levels}
        if orderbook_snapshot is not None:
            bids = sorted(orderbook_snapshot.bids.items(), key=lambda x: x[0], reverse=True)
            asks = sorted(orderbook_snapshot.asks.items(), key=lambda x: x[0])
            book = {
                "last_update_id": orderbook_snapshot.last_update_id,
                "bids": [{"price": str(p), "qty": str(q)} for p, q in bids[: self.depth_levels]],
                "asks": [{"price": str(p), "qty": str(q)} for p, q in asks[: self.depth_levels]],
                "depth_levels": self.depth_levels,
            }
        await self._broadcast(envelope("CANDLE", candle.bar_time, self.symbol, {
            "bar_time": candle.bar_time.astimezone(timezone.utc).isoformat(),
            "timeframe": candle.timeframe,
            "open": d2s(candle.open), "high": d2s(candle.high),
            "low": d2s(candle.low), "close": d2s(candle.close),
            "volume": d2s(candle.volume), "delta": d2s(candle.delta), "cvd": d2s(candle.cvd),
            "footprint": {
                "levels": [{"price": str(l["price"]), "bid": str(l["bid"]), "ask": str(l["ask"])} for l in levels],
                "poc_price": poc, "vah_price": vah, "val_price": val,
            },
            "orderbook": book,
        }))

    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result) -> None:
        """module_scores: {"cvd": Decimal|None, "footprint": ..., "imbalance": ...}（M11のスコア）"""
        now = analysis_result.analysis_time
        scores: dict[str, Optional[Decimal]] = {
            "cvd": module_scores.get("cvd"),
            "footprint": module_scores.get("footprint"),
            "imbalance": module_scores.get("imbalance"),
            "absorption": absorption_result.strength if absorption_result is not None else None,
            "flow": self.flow_score(now),
        }
        veto = "NONE"
        for r in signal_result.reasons:
            if "VETO" in r or r in ("ABNORMAL_BOOK", "EXTREME_DELTA", "MARKET_HALT", "DATA_ERROR"):
                veto = r
                break
        await self._broadcast(envelope("ANALYSIS", now, self.symbol, {
            "signal": signal_result.signal,                 # SignalEngine値をそのまま（SoT）
            "confidence": d2s(signal_result.confidence),
            "composite": d2s(getattr(signal_result, "composite", None)),
            "scores": {k: d2s(v) for k, v in scores.items()},
            "confluence": self.confluence(signal_result.signal, scores),
            "market_state": analysis_result.market_state,   # そのまま（UI側マッピング禁止）
            "risk_level": analysis_result.risk_level,
            "veto": veto,
            "reasons": list(analysis_result.reasons),
            "expected_rr": None,                            # v1は常にnull（捏造禁止）
        }))

    async def on_flow_event(self, ev) -> None:
        self._flow_history.append(_FlowRecord(ev.event_time, ev.strength))
        await self._broadcast(envelope("FLOW", ev.event_time, self.symbol, {
            "event_time": ev.event_time.astimezone(timezone.utc).isoformat(),
            "category": ev.category, "side": ev.side,
            "strength": d2s(ev.strength), "detector": ev.detector, "detail": ev.detail,
        }))

    async def on_liquidation(self, liq) -> None:
        await self._broadcast(envelope("LIQUIDATION", liq.event_time, self.symbol, {
            "side": liq.side, "price": d2s(liq.price), "quantity": d2s(liq.quantity),
        }))

    async def on_oi(self, event_time: datetime, open_interest: Decimal, prev: Optional[Decimal]) -> None:
        await self._broadcast(envelope("OI", event_time, self.symbol, {
            "open_interest": d2s(open_interest), "prev": d2s(prev),
        }))

    async def send_stats(self, event_time: datetime, stats: dict) -> None:
        await self._broadcast(envelope("STATS", event_time, self.symbol,
                                       {k: str(v) for k, v in stats.items()}))
```

（on_candle / on_analysis の引数は既存hooksの実シグネチャに合わせて配線せよ。**Payload形は仕様書が正**であり、引数側の都合でPayloadを変えるな。）

---

# 5. webapp/oi_poller.py

v2設計を踏襲: 既存REST fetch関数を用い `interval_sec`（デフォルト15）ごとに Open Interest を取得し `broker.on_oi` を呼ぶasyncタスク。取得失敗はwarningログ＋スキップ（例外握りつぶし禁止・停止もしない）。前回値を保持し `prev` として渡す。

---

# 6. webapp/main.py

```python
"""DeltaEngine WebApp — FastAPI + WebSocket。

起動: uvicorn webapp.main:app  /  docker-compose up
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import load_config
from webapp.push_broker import PushBroker, PAYLOAD_VERSION

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="DeltaEngine WebApp")


def build_broker(config) -> PushBroker:
    w = config.webapp
    return PushBroker(
        symbol=config.market.symbol,
        depth_levels=w.depth_levels,
        flow_window_sec=w.flow_window_sec,
        confluence_score_threshold=Decimal(str(w.confluence.score_threshold)),
        confluence_strength_threshold=Decimal(str(w.confluence.strength_threshold)),
    )


@app.on_event("startup")
async def startup() -> None:
    config = load_config("config/config.yaml")
    app.state.config = config
    app.state.broker = build_broker(config)
    # LivePipeline を hooks 付きで起動（既存 live 起動経路を使用）:
    #   on_trade / on_candle / on_analysis / on_liquidation / on_flow_event → broker
    # oi_poller / stats(5秒毎 send_stats) タスクを asyncio.create_task で開始
    app.state.tasks = []
    # …既存 LivePipeline 起動コードに合わせて配線（イベントループは単一、ADR-003）


@app.on_event("shutdown")
async def shutdown() -> None:
    for t in app.state.tasks:
        t.cancel()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    broker: PushBroker = app.state.broker
    config = app.state.config
    # HELLO（WebSocketPayload仕様_v1 §4.1）
    await ws.send_json({
        "v": PAYLOAD_VERSION, "type": "HELLO",
        "time": datetime.now(timezone.utc).isoformat(),
        "symbol": config.market.symbol,
        "payload": {
            "server": "DeltaEngine WebApp",
            "payload_version": PAYLOAD_VERSION,
            "bar_timeframe": config.market.bar_timeframe,
            "signal_enabled": config.signal.enabled,
        },
    })
    await broker.register(ws)
    try:
        while True:
            await ws.receive_text()  # クライアント→サーバーは読み捨て（一方向配信）
    except WebSocketDisconnect:
        pass
    finally:
        await broker.unregister(ws)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

---

# 7. webapp/static/index.html（全文。ビルド工程なしのVanilla JS）

**UI仕様書_CommandCenter_v1 が視覚上の正。** 以下コードを起点とし、仕様書との差異があれば仕様書に合わせよ。判定ロジック・固定値の追加は禁止。

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeltaEngine Command Center</title>
<style>
:root{
  --bg:#0A0D12;--panel:#11161F;--panel2:#151C27;--line:#1E2735;
  --buy:#00E676;--sell:#FF4D4D;--warn:#FFC400;--info:#9C7DFF;
  --dis:#5B6472;--text:#E8EDF4;--sub:#8A94A6;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--text);
  font-family:'SF Mono','Cascadia Code','Roboto Mono',ui-monospace,monospace;
  font-variant-numeric:tabular-nums;font-size:12px;user-select:none;overflow:hidden}
#appgrid{display:flex;flex-direction:column;gap:6px;height:100vh;padding:6px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  display:flex;flex-direction:column;overflow:hidden}
.phead{display:flex;align-items:center;justify-content:space-between;
  padding:5px 12px;border-bottom:1px solid var(--line);flex-shrink:0}
.ptitle{font-size:11px;font-weight:600;letter-spacing:.15em;color:var(--sub)}
.hint{font-size:9px;letter-spacing:.1em;color:var(--dis)}
.dash{color:var(--dis)}
/* top bar */
#topbar{display:flex;align-items:center;gap:18px;padding:0 16px;height:48px;flex-shrink:0}
#price{font-size:22px;font-weight:700}
#chg{font-size:13px;font-weight:600}
#sigchip{display:flex;align-items:center;gap:8px;padding:4px 12px;border-radius:6px;
  border:1px solid var(--line)}
#sigchip b{font-size:15px;letter-spacing:.15em}
.kv{display:flex;flex-direction:column;align-items:flex-end;line-height:1.15}
.kv .k{font-size:9px;letter-spacing:.15em;color:var(--dis)}
.kv .v{font-size:13px;font-weight:600}
#live{display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:6px;
  font-size:10px;font-weight:600}
#devbtn{background:none;border:none;color:var(--dis);cursor:pointer;font-size:15px;padding:6px}
#devbtn.on{color:var(--info)}
/* main */
#main{display:flex;gap:6px;flex:1;min-height:0}
#left{width:256px;flex-shrink:0}
#center{flex:2.2;display:flex;flex-direction:column;gap:6px;min-width:0}
#right{width:320px;flex-shrink:0;display:flex;flex-direction:column;gap:6px}
/* order book */
#bookbody{flex:1;display:flex;flex-direction:column;justify-content:center;
  padding:4px 6px;overflow:hidden}
.brow{position:relative;display:flex;align-items:center;gap:6px;flex:1;min-height:17px;
  border-radius:3px;margin:1px 0;padding:0 6px;transition:background .3s}
.brow .cum{position:absolute;left:0;top:0;bottom:0;pointer-events:none}
.brow span{position:relative;z-index:1}
.brow .qty{margin-left:auto;font-weight:600}
.brow .sig{width:44px;text-align:right;font-size:10px;color:var(--dis)}
#mid{display:flex;align-items:center;justify-content:center;gap:8px;margin:3px 0;
  padding:4px;border-radius:5px;background:var(--panel2);border:1px solid var(--line)}
#mid b{font-size:13px}
/* footprint */
#fphead,#fprow-template{display:flex;align-items:center}
#fpcols{display:flex;padding:4px 12px;font-size:9px;letter-spacing:.15em;color:var(--dis);
  border-bottom:1px solid var(--line);flex-shrink:0}
#fpbody{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 12px;overflow:hidden}
.fprow{display:flex;align-items:center;flex:1;max-height:34px;padding:2px 0;border-radius:4px}
.fprow.va{background:rgba(255,196,0,.025)}
.fprow.poc{background:rgba(255,196,0,.08)}
.fprow.vah{border-top:1px dashed rgba(255,196,0,.4)}
.fprow.val{border-bottom:1px dashed rgba(255,196,0,.4)}
.fp-price{width:110px;display:flex;align-items:center;gap:5px;color:var(--sub)}
.badge{font-size:8px;font-weight:700;padding:1px 4px;border-radius:3px}
.badge.poc{background:var(--warn);color:var(--bg)}
.badge.va{border:1px solid var(--warn);color:var(--warn)}
.fp-side{flex:1;display:flex;align-items:center;gap:5px}
.fp-side.bid{justify-content:flex-end;padding-right:8px}
.fp-side.ask{padding-left:8px}
.fp-bar{height:11px;border-radius:2px;transition:width .3s}
.fp-x{width:26px;text-align:center;color:var(--line)}
.fp-delta{width:60px;text-align:right;font-weight:600}
.fp-sig{width:44px;text-align:center;font-size:11px}
.ctl{display:flex;align-items:center;gap:3px}
.ctl button{background:none;border:none;color:var(--sub);cursor:pointer;padding:3px;font-size:12px}
.ctl button.lock{color:var(--warn)}
.ctl .idx{font-size:9px;color:var(--dis);width:52px;text-align:center}
/* flow */
#flowpanel{height:160px;flex-shrink:0}
#flowbody{flex:1;overflow-y:auto;padding:2px 12px}
.frow{display:flex;align-items:center;gap:10px;padding:3px 0;border-bottom:1px solid var(--line)}
.fcat{width:96px;text-align:center;font-size:9px;font-weight:700;letter-spacing:.08em;
  padding:2px 5px;border-radius:4px}
.fside{width:38px;font-weight:800}
.fdet{font-size:9px;color:var(--dis)}
.fblocks{margin-left:auto;letter-spacing:-1px;font-size:11px}
.fstr{width:38px;text-align:right;font-weight:600}
.legend{display:flex;gap:9px;font-size:8px;letter-spacing:.08em;color:var(--dis);align-items:center}
.legend i{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:3px}
/* right */
#mstate{padding:12px;display:flex}
#mschip{flex:1;display:flex;align-items:center;justify-content:center;padding:9px;
  border-radius:6px;font-size:17px;font-weight:900;letter-spacing:.15em;transition:all .3s}
#confl{padding:9px 14px}
#confstars{text-align:center;font-size:20px;letter-spacing:.2em;color:var(--warn);margin-bottom:7px}
#confgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}
.cchip{display:flex;flex-direction:column;align-items:center;padding:4px 0;border-radius:5px;
  background:var(--panel2);border:1px solid var(--line)}
.cchip.on{background:rgba(0,230,118,.08);border-color:rgba(0,230,118,.3)}
.cchip b{font-size:12px;color:var(--dis)}
.cchip.on b{color:var(--buy)}
.cchip span{font-size:7px;letter-spacing:.06em;color:var(--dis);margin-top:2px}
.cchip.on span{color:var(--text)}
#whypanel{flex:1}
#whybody{padding:10px 16px;display:flex;flex-direction:column;flex:1}
#whytop{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
#whysig{font-size:21px;font-weight:900;letter-spacing:.12em}
#vetobadge{display:none;margin-bottom:8px;padding:3px 8px;border-radius:5px;text-align:center;
  font-size:10px;font-weight:700;letter-spacing:.1em;color:var(--warn);
  background:rgba(255,196,0,.1);border:1px solid rgba(255,196,0,.35)}
.srow{margin-bottom:11px}
.srow .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}
.srow .name{font-size:12px;font-weight:600;letter-spacing:.08em}
.srow .val{font-size:18px;font-weight:900}
.srow .track{height:9px;border-radius:99px;background:var(--line);overflow:hidden}
.srow .fill{height:100%;border-radius:99px;transition:width .5s}
#whydivider{height:1px;background:var(--line);margin:2px 0 11px}
#whyfoot{margin-top:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:5px;text-align:center}
.mchip{padding:5px 0;border-radius:6px;background:var(--panel2);border:1px solid var(--line)}
.mchip .k{font-size:8px;letter-spacing:.15em;color:var(--dis)}
.mchip .v{font-size:11px;font-weight:700}
/* bottom */
#bottom{height:128px;flex-shrink:0}
#tabs{display:flex;gap:3px}
#tabs button{background:none;border:none;color:var(--sub);cursor:pointer;
  font-size:9px;font-weight:700;letter-spacing:.15em;padding:2px 9px;border-radius:4px;
  font-family:inherit}
#tabs button.on{color:var(--bg)}
#chartwrap{flex:1;padding:3px 8px}
#chart{width:100%;height:100%}
/* overlays */
#toasts{position:fixed;top:56px;left:50%;transform:translateX(-50%);z-index:60;
  display:flex;flex-direction:column;gap:6px;align-items:center;pointer-events:none}
.toast{display:flex;align-items:center;gap:9px;padding:8px 16px;border-radius:8px;
  font-size:13px;font-weight:700;letter-spacing:.06em;background:rgba(17,22,31,.96);
  backdrop-filter:blur(8px);animation:drop .2s ease-out}
@keyframes drop{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
#alerthist{position:fixed;bottom:14px;right:14px;width:250px;z-index:50;border-radius:8px;
  background:rgba(17,22,31,.94);border:1px solid var(--line);backdrop-filter:blur(8px);
  overflow:hidden;display:none}
#alerthist .ah-head{padding:5px 12px;border-bottom:1px solid var(--line);
  font-size:9px;font-weight:700;letter-spacing:.15em;color:var(--sub)}
#alertrows{max-height:150px;overflow-y:auto;padding:2px 12px}
.arow{display:flex;align-items:center;gap:7px;padding:3px 0;font-size:10px;
  border-bottom:1px solid var(--line)}
.arow i{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.arow .as{margin-left:auto;color:var(--sub)}
#devov{position:fixed;bottom:14px;left:14px;z-index:60;border-radius:8px;padding:11px 15px;
  background:rgba(17,22,31,.95);border:1px solid var(--info);backdrop-filter:blur(8px);
  display:none;font-size:11px}
#devov .dh{font-weight:700;letter-spacing:.15em;color:var(--info);margin-bottom:7px}
#devgrid{display:grid;grid-template-columns:1fr 1fr;gap:3px 22px}
#devgrid div{display:flex;justify-content:space-between;gap:14px}
#devgrid .k{color:var(--dis)}
#banner{position:fixed;top:0;left:0;right:0;z-index:100;display:none;padding:5px;text-align:center;
  font-size:11px;font-weight:700;letter-spacing:.08em;color:var(--warn);
  background:rgba(255,196,0,.12);border-bottom:1px solid var(--warn)}
</style>
</head>
<body>
<div id="banner"></div>
<div id="toasts"></div>
<div id="appgrid">

  <div id="topbar" class="panel">
    <span style="font-size:13px;font-weight:700;letter-spacing:.15em;color:var(--sub)" id="sym">—</span>
    <span id="price" class="dash">—</span>
    <span id="chg" class="dash">—</span>
    <span id="sigchip"><b id="sigtop" class="dash">—</b><span id="conftop" style="font-size:11px;color:var(--sub)">—</span></span>
    <span style="flex:1"></span>
    <span class="kv"><span class="k">ATR(14)</span><span class="v dash" id="atr">—</span></span>
    <span class="kv"><span class="k">SPREAD</span><span class="v" id="spread">—</span></span>
    <span class="kv"><span class="k">LATENCY</span><span class="v" id="lat">—</span></span>
    <span class="kv"><span class="k">FPS</span><span class="v" id="fps">—</span></span>
    <span id="live" style="color:var(--dis);border:1px solid var(--line)">CONNECTING</span>
    <button id="devbtn" title="Developer Overlay">🐛</button>
  </div>

  <div id="main">
    <div id="left" class="panel">
      <div class="phead"><span class="ptitle">ORDER BOOK</span><span class="hint">QTY / Σ DEPTH</span></div>
      <div id="bookbody"><div class="dash" style="text-align:center">—</div></div>
    </div>

    <div id="center">
      <div class="panel" style="flex:1">
        <div class="phead">
          <span class="ptitle" id="fptitle">FOOTPRINT</span>
          <span class="ctl">
            <button id="prevbar">◀</button><span class="idx" id="baridx">—/—</span><button id="nextbar">▶</button>
            <span style="width:1px;height:14px;background:var(--line);margin:0 4px"></span>
            <button id="zin">＋</button><button id="zout">－</button>
            <button id="plock" class="lock">🔒</button>
          </span>
        </div>
        <div id="fpcols">
          <span style="width:110px">PRICE</span><span style="flex:1;text-align:right;padding-right:8px">BID</span>
          <span style="width:26px"></span><span style="flex:1;padding-left:8px">ASK</span>
          <span style="width:60px;text-align:right">DELTA</span><span style="width:44px;text-align:center">SIG</span>
        </div>
        <div id="fpbody"><div class="dash" style="text-align:center">—</div></div>
      </div>

      <div id="flowpanel" class="panel">
        <div class="phead">
          <span class="ptitle">FLOW EVENTS</span>
          <span class="legend" id="flowlegend"></span>
        </div>
        <div id="flowbody"></div>
      </div>
    </div>

    <div id="right">
      <div class="panel">
        <div class="phead"><span class="ptitle">MARKET STATE</span><span class="hint">FROM SIGNALENGINE</span></div>
        <div id="mstate"><div id="mschip" class="dash">—</div></div>
      </div>
      <div class="panel">
        <div class="phead"><span class="ptitle">CONFLUENCE</span></div>
        <div id="confl">
          <div id="confstars" class="dash">—</div>
          <div id="confgrid"></div>
        </div>
      </div>
      <div id="whypanel" class="panel">
        <div class="phead"><span class="ptitle">SIGNAL — WHY</span></div>
        <div id="whybody">
          <div id="whytop">
            <span id="whysig" class="dash">—</span>
            <span style="font-size:11px;color:var(--sub)">CONF <b id="whyconf" style="font-size:14px;color:var(--text)">—</b></span>
          </div>
          <div id="vetobadge"></div>
          <div id="scores"></div>
          <div id="whyfoot">
            <div class="mchip"><div class="k">RISK</div><div class="v dash" id="risk">—</div></div>
            <div class="mchip"><div class="k">EXP. RR</div><div class="v dash" id="rr">—</div></div>
            <div class="mchip"><div class="k">VETO</div><div class="v dash" id="veto">—</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="bottom" class="panel">
    <div class="phead">
      <span id="tabs"></span>
      <span style="display:flex;align-items:center;gap:12px">
        <span class="legend" id="chartlegend"></span>
        <b id="chartlast" class="dash" style="font-size:13px">—</b>
      </span>
    </div>
    <div id="chartwrap"><svg id="chart" preserveAspectRatio="none" viewBox="0 0 1000 100"></svg></div>
  </div>
</div>

<div id="alerthist"><div class="ah-head">🕘 ALERTS</div><div id="alertrows"></div></div>
<div id="devov"><div class="dh">🐛 DEVELOPER OVERLAY</div><div id="devgrid"></div></div>

<script>
"use strict";
// ============================================================
// UIは Payload のみを参照する。判定ロジック禁止（表示整形のみ）。
// 対応 Payload version:
const UI_PAYLOAD_VERSION = 1;
// FLOWカテゴリ色（バッジ専用名前空間。未知カテゴリは白 UNKNOWN）
const CAT = {DELTA:"#FF4D4D",IMBALANCE:"#4DA3FF",ABSORPTION:"#9C7DFF",
             EXHAUSTION:"#FFC400",ICEBERG:"#E8EDF4"};
const BUY="#00E676",SELL="#FF4D4D",WARN="#FFC400",INFO="#9C7DFF",DIS="#5B6472",TXT="#E8EDF4",LINE="#1E2735",SUB="#8A94A6";
const $=id=>document.getElementById(id);
const N=s=>s==null?null:Number(s);           // 表示専用変換
const fmt=(s,d=2)=>s==null?"—":Number(s).toFixed(d);

// ---------------- state（全てPayload由来） ----------------
const S={
  symbol:"—", price:null, prevPrice:null, firstOpen:null,
  bars:[],            // CANDLE履歴（最大300）
  barView:-1,         // -1 = 最新追従（price lock）
  zoom:1, lock:true,
  analysis:null, flows:[], alerts:[],
  series:{ "CVD+Δ":{cvd:[],delta:[]}, VOLUME:[], OI:[], LIQUIDATION:[] },
  tab:"CVD+Δ", stats:null, lastTickAt:null, latency:null,
};

// ---------------- WebSocket ----------------
let ws=null, backoff=1000;
function connect(){
  ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
  ws.onopen=()=>{backoff=1000;setLive(true);};
  ws.onclose=()=>{setLive(false);setTimeout(connect,backoff);backoff=Math.min(backoff*2,10000);};
  ws.onerror=()=>ws.close();
  ws.onmessage=e=>{let m;try{m=JSON.parse(e.data);}catch(_){return;}handle(m);};
}
function setLive(on){
  const el=$("live");
  el.textContent=on?"LIVE":"RECONNECTING";
  el.style.color=on?BUY:DIS;
  el.style.background=on?"rgba(0,230,118,.08)":"transparent";
  el.style.borderColor=on?"rgba(0,230,118,.25)":LINE;
}

function versionWarn(serverV){
  const b=$("banner"); b.style.display="block";
  b.textContent=`⚠ PAYLOAD VERSION MISMATCH — server v${serverV} / ui v${UI_PAYLOAD_VERSION}（描画は継続。表示欠落の可能性あり）`;
}
function handle(m){
  // §6.2 段階的縮退: 不一致でもWarningのみ表示し描画継続。全面停止しない。
  if(m.v!==UI_PAYLOAD_VERSION)versionWarn(m.v);
  S.symbol=m.symbol||S.symbol;
  const p=m.payload||{};
  try{
    switch(m.type){
      case "HELLO":
        if(p.payload_version!==UI_PAYLOAD_VERSION)versionWarn(p.payload_version);
        $("sym").textContent=m.symbol; break;
      case "TICK": onTick(m,p); break;
      case "CANDLE": onCandle(p); break;
      case "ANALYSIS": S.analysis=p; renderAnalysis(); renderTopSignal(); break;
      case "FLOW": onFlow(m,p); break;
      case "LIQUIDATION": pushSeries("LIQUIDATION",Math.abs(N(p.quantity)??0)); break;
      case "OI": pushSeries("OI",N(p.open_interest)); break;
      case "STATS": S.stats=p; renderDev(); break;
      default: break; // 未知typeは破棄（前方互換）
    }
  }catch(_){/* 必須フィールド欠落等はメッセージ単位でスキップ。画面は落とさない */}
}

// ---------------- handlers ----------------
function onTick(m,p){
  S.prevPrice=S.price; S.price=N(p.price);
  if(S.firstOpen==null&&S.price!=null)S.firstOpen=S.price;
  S.lastTickAt=Date.now();
  S.latency=Math.max(0,Date.now()-Date.parse(m.time));
  renderTop();
}
function onCandle(p){
  S.bars.push(p); if(S.bars.length>300)S.bars.shift();
  pushSeries("CVD+Δ",{cvd:N(p.cvd),delta:N(p.delta)});
  pushSeries("VOLUME",N(p.volume));
  renderBook(p.orderbook); renderFootprint(); renderChart();
}
function onFlow(m,p){
  S.flows.unshift(p); if(S.flows.length>40)S.flows.pop();
  renderFlow();
  const th=0.85; // 表示演出の閾値（判定ではない。configと同期は将来HELLOに載せる）
  if(N(p.strength)>=th){
    const a={t:(p.event_time||m.time).slice(11,19),cat:p.category,side:p.side,strength:p.strength};
    S.alerts.unshift(a); if(S.alerts.length>8)S.alerts.pop();
    toast(a); renderAlerts();
  }
}
function pushSeries(key,v){
  if(v==null)return;
  if(key==="CVD+Δ"){S.series[key].cvd.push(v.cvd);S.series[key].delta.push(v.delta);
    if(S.series[key].cvd.length>140){S.series[key].cvd.shift();S.series[key].delta.shift();}}
  else{S.series[key].push(v); if(S.series[key].length>140)S.series[key].shift();}
  if(key===S.tab||key==="CVD+Δ"&&S.tab==="CVD+Δ")renderChart();
}

// ---------------- renderers ----------------
function renderTop(){
  if(S.price==null)return;
  const up=S.prevPrice==null||S.price>=S.prevPrice;
  const pe=$("price"); pe.classList.remove("dash");
  pe.textContent=S.price.toLocaleString(undefined,{minimumFractionDigits:1});
  pe.style.color=up?BUY:SELL;
  if(S.firstOpen){const c=(S.price-S.firstOpen)/S.firstOpen*100;
    const ce=$("chg"); ce.classList.remove("dash");
    ce.textContent=(c>=0?"▲":"▼")+Math.abs(c).toFixed(2)+"%"; ce.style.color=c>=0?BUY:SELL;}
  if(S.latency!=null){const le=$("lat"); le.textContent=S.latency+"ms";
    le.style.color=S.latency<60?BUY:S.latency<120?WARN:SELL;}
  const last=S.bars[S.bars.length-1];
  if(last&&last.orderbook&&last.orderbook.asks[0]&&last.orderbook.bids[0]){
    $("spread").textContent=(N(last.orderbook.asks[0].price)-N(last.orderbook.bids[0].price)).toFixed(1);}
}
function renderTopSignal(){
  const a=S.analysis; if(!a)return;
  const col=sigColor(a.signal);
  const st=$("sigtop"); st.classList.remove("dash"); st.textContent=a.signal; st.style.color=col;
  $("sigchip").style.background=col+"14"; $("sigchip").style.borderColor=col+"44";
  $("conftop").textContent=a.confidence==null?"—":Math.round(N(a.confidence)*100)+"%";
}
function sigColor(s){return s==="BUY"?BUY:s==="SELL"?SELL:s==="WAIT"?DIS:WARN;}

function renderBook(book){
  const el=$("bookbody"); if(!book){return;}
  const rows=[]; const all=[...book.asks,...book.bids].map(r=>N(r.qty));
  const max=Math.max(...all,0.0001);
  const asks=[...book.asks].reverse(); // 高値上
  let cum=0; const askCum=asks.map(r=>0);
  for(let i=asks.length-1;i>=0;i--){cum+=N(asks[i].qty);askCum[i]=cum;}
  const maxCum=Math.max(cum, book.bids.reduce((s,r)=>s+N(r.qty),0), 0.0001);
  asks.forEach((r,i)=>{const h=N(r.qty)/max;
    rows.push(`<div class="brow" style="background:rgba(255,77,77,${(0.05+h*0.42).toFixed(3)})">
      <div class="cum" style="width:${(askCum[i]/maxCum*100).toFixed(1)}%;border-bottom:1px solid rgba(255,77,77,.5)"></div>
      <span style="color:${h>0.75?"#FFF":SELL}">${fmt(r.price,1)}</span>
      <span class="qty" style="color:${h>0.75?"#FFF":SUB}">${fmt(r.qty)}</span>
      <span class="sig">${askCum[i].toFixed(1)}</span></div>`);});
  rows.push(`<div id="mid"><b style="color:${S.prevPrice==null||S.price>=S.prevPrice?BUY:SELL}">${S.price?S.price.toFixed(1):"—"}</b><span class="hint">MID</span></div>`);
  let bcum=0;
  book.bids.forEach(r=>{const h=N(r.qty)/max; bcum+=N(r.qty);
    rows.push(`<div class="brow" style="background:rgba(0,230,118,${(0.04+h*0.38).toFixed(3)})">
      <div class="cum" style="width:${(bcum/maxCum*100).toFixed(1)}%;border-top:1px solid rgba(0,230,118,.5)"></div>
      <span style="color:${h>0.75?"#FFF":BUY}">${fmt(r.price,1)}</span>
      <span class="qty" style="color:${h>0.75?"#FFF":SUB}">${fmt(r.qty)}</span>
      <span class="sig">${bcum.toFixed(1)}</span></div>`);});
  el.innerHTML=rows.join("");
}

function renderFootprint(){
  if(!S.bars.length)return;
  const idx=S.lock||S.barView<0?S.bars.length-1:Math.min(S.barView,S.bars.length-1);
  const bar=S.bars[idx]; const fp=bar.footprint;
  $("fptitle").textContent=`FOOTPRINT — BAR ${bar.bar_time.slice(11,16)} (${bar.timeframe})`;
  $("baridx").textContent=`${idx+1}/${S.bars.length}`;
  const lv=fp.levels; if(!lv.length){$("fpbody").innerHTML='<div class="dash" style="text-align:center">—</div>';return;}
  const max=Math.max(...lv.map(l=>Math.max(N(l.bid),N(l.ask))),0.0001);
  // VA帯の範囲（受信したPOC/VAH/VALを使うのみ。再計算しない）
  const html=lv.map(l=>{
    const bid=N(l.bid),ask=N(l.ask),d=ask-bid;
    const isPoc=l.price===fp.poc_price, isVah=l.price===fp.vah_price, isVal=l.price===fp.val_price;
    const inVa=fp.vah_price!=null&&fp.val_price!=null&&N(l.price)<=N(fp.vah_price)&&N(l.price)>=N(fp.val_price);
    // SIG列は「表示強調」のみ（判定はFLOW/ANALYSISが正）
    const imb=ask>bid*3?"buy":bid>ask*3?"sell":null;
    const abs=(bid+ask)>max*1.4&&Math.abs(d)<max*0.1;
    return `<div class="fprow${isPoc?" poc":inVa?" va":""}${isVah?" vah":""}${isVal?" val":""}" style="font-size:${13*S.zoom}px">
      <span class="fp-price" style="color:${isPoc?WARN:SUB}">${fmt(l.price,1)}
        ${isPoc?'<span class="badge poc">POC</span>':""}${isVah&&!isPoc?'<span class="badge va">VAH</span>':""}${isVal&&!isPoc?'<span class="badge va">VAL</span>':""}</span>
      <span class="fp-side bid"><span style="color:${SELL}">${fmt(l.bid)}</span>
        <span class="fp-bar" style="width:${(bid/max*100).toFixed(1)}%;background:rgba(255,77,77,.55)"></span></span>
      <span class="fp-x">×</span>
      <span class="fp-side ask"><span class="fp-bar" style="width:${(ask/max*100).toFixed(1)}%;background:rgba(0,230,118,.5)"></span>
        <span style="color:${BUY}">${fmt(l.ask)}</span></span>
      <span class="fp-delta" style="color:${d>=0?BUY:SELL}">${d>=0?"+":""}${d.toFixed(1)}</span>
      <span class="fp-sig">${imb==="buy"?`<span style="color:${BUY}">▸</span>`:imb==="sell"?`<span style="color:${SELL}">◂</span>`:""}${abs?`<span style="color:${WARN}"> ●</span>`:""}</span>
    </div>`;
  }).join("");
  $("fpbody").innerHTML=html;
}

function catColor(c){return CAT[c]||"#FFFFFF";}
function renderFlow(){
  $("flowbody").innerHTML=S.flows.map((f,i)=>{
    const col=catColor(f.category), s=N(f.strength)??0, b=Math.round(s*10);
    const cat=CAT[f.category]?f.category:"UNKNOWN";
    return `<div class="frow" style="opacity:${Math.max(0.35,1-i*0.055)}">
      <span style="color:${DIS}">${(f.event_time||"").slice(11,19)}</span>
      <span class="fcat" style="background:${col}22;color:${col};border:1px solid ${col}55">${cat}</span>
      <span class="fside" style="color:${f.side==="BUY"?BUY:SELL}">${f.side}</span>
      <span class="fdet">${f.detector||""}</span>
      <span class="fblocks" style="color:${col}">${"■".repeat(b)}<span style="color:${LINE}">${"■".repeat(10-b)}</span></span>
      <span class="fstr">${fmt(f.strength)}</span></div>`;
  }).join("");
}
$("flowlegend").innerHTML=Object.entries(CAT).map(([k,c])=>`<span><i style="background:${c}"></i>${k}</span>`).join("")+`<span style="color:${BUY}">● LIVE</span>`;

function scoreRow(name,val,{composite=false,zeroToOne=false}={}){
  const v=N(val);
  const col=composite?INFO:v==null?DIS:v>=0?BUY:SELL;
  const width=v==null?0:zeroToOne?Math.min(Math.abs(v)*100,100):Math.min(Math.abs(v),100);
  const disp=v==null?"—":(v>0&&!composite&&!zeroToOne?"+":"")+(zeroToOne?v.toFixed(2):Math.round(v));
  return `<div class="srow"><div class="top">
    <span class="name" style="color:${composite?INFO:TXT}">${name}</span>
    <span class="val" style="color:${col}">${disp}</span></div>
    <div class="track"><div class="fill" style="width:${width}%;background:${col};box-shadow:0 0 8px ${col}55"></div></div></div>`;
}
function renderAnalysis(){
  const a=S.analysis; if(!a)return;
  // MARKET STATE: 受信文字列をそのまま。BULL/BEAR含有は表示ヒントのみ
  const ms=$("mschip"); ms.classList.remove("dash"); ms.textContent=a.market_state??"—";
  const mc=(a.market_state||"").includes("BULL")?BUY:(a.market_state||"").includes("BEAR")?SELL:SUB;
  ms.style.color=mc; ms.style.background=mc+"14"; ms.style.border=`1px solid ${mc}55`; ms.style.boxShadow=`0 0 12px ${mc}22`;
  // CONFLUENCE: 受信フラグを描画するのみ
  const cf=a.confluence||{}; const names=["cvd","footprint","imbalance","absorption","flow"];
  $("confstars").classList.remove("dash");
  $("confstars").innerHTML="★".repeat(cf.count||0)+`<span style="color:${LINE}">${"★".repeat(5-(cf.count||0))}</span>`;
  $("confgrid").innerHTML=names.map(n=>`<div class="cchip${cf[n]?" on":""}"><b>${cf[n]?"✔":"—"}</b><span>${n.toUpperCase()}</span></div>`).join("");
  // SIGNAL — WHY
  const col=sigColor(a.signal);
  const ws_=$("whysig"); ws_.classList.remove("dash"); ws_.textContent=a.signal; ws_.style.color=col;
  $("whyconf").textContent=a.confidence==null?"—":Math.round(N(a.confidence)*100)+"%";
  const vb=$("vetobadge");
  if(a.veto&&a.veto!=="NONE"){vb.style.display="block";vb.textContent="⚠ "+a.veto;}else vb.style.display="none";
  const sc=a.scores||{};
  $("scores").innerHTML=
    scoreRow("CVD",sc.cvd)+scoreRow("FOOTPRINT",sc.footprint)+scoreRow("IMBALANCE",sc.imbalance)+
    scoreRow("ABSORPTION",sc.absorption,{zeroToOne:true})+scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
  const rk=$("risk"); rk.classList.remove("dash"); rk.textContent=a.risk_level??"—";
  rk.style.color=a.risk_level==="LOW"?BUY:a.risk_level==="MEDIUM"?WARN:a.risk_level==="HIGH"?SELL:DIS;
  $("rr").textContent=a.expected_rr==null?"—":a.expected_rr;   // v1は常に—
  const ve=$("veto"); ve.classList.remove("dash"); ve.textContent=a.veto??"—";
  ve.style.color=a.veto==="NONE"?DIS:WARN;
}

// bottom chart
const TABS=["CVD+Δ","VOLUME","OI","LIQUIDATION"];
function tabColor(t,lastV){return t==="LIQUIDATION"?WARN:t==="OI"?INFO:(lastV??0)>=0?BUY:SELL;}
function renderTabs(){
  $("tabs").innerHTML=TABS.map(t=>`<button class="${t===S.tab?"on":""}" data-t="${t}"
    style="${t===S.tab?`background:${tabColor(t,seriesLast(t))}`:""}">${t}</button>`).join("");
  [...$("tabs").children].forEach(b=>b.onclick=()=>{S.tab=b.dataset.t;renderTabs();renderChart();});
}
function seriesLast(t){const s=S.series[t];return t==="CVD+Δ"?(s.cvd[s.cvd.length-1]??null):(s[s.length-1]??null);}
function path(data){
  if(data.length<2)return "";
  const mn=Math.min(...data),mx=Math.max(...data);
  return data.map((v,i)=>`${i?"L":"M"}${(i/(data.length-1)*1000).toFixed(1)},${(100-((v-mn)/(mx-mn||1))*90-5).toFixed(1)}`).join(" ");
}
function renderChart(){
  const t=S.tab, lastV=seriesLast(t), col=tabColor(t,lastV);
  const cl=$("chartlast");
  if(lastV!=null){cl.classList.remove("dash");cl.textContent=(lastV>=0&&(t==="CVD+Δ"||t==="OI")?"+":"")+lastV.toFixed(2)+(t==="CVD+Δ"?" BTC":"");cl.style.color=col;}
  const main=t==="CVD+Δ"?S.series[t].cvd:S.series[t];
  const overlay=t==="CVD+Δ"?S.series[t].delta:null;
  $("chartlegend").innerHTML=t==="CVD+Δ"?`<span><i style="background:${col};border-radius:0;width:12px;height:2px"></i>CVD</span><span><i style="background:${INFO};border-radius:0;width:12px;height:2px"></i>DELTA</span>`:"";
  $("chart").innerHTML=`
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".22"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/>
    </linearGradient></defs>
    ${main.length>1?`<path d="${path(main)} L1000,100 L0,100 Z" fill="url(#g)"/>`:""}
    ${overlay&&overlay.length>1?`<path d="${path(overlay)}" fill="none" stroke="${INFO}" stroke-width="1" stroke-dasharray="3,3" opacity=".8"/>`:""}
    ${main.length>1?`<path d="${path(main)}" fill="none" stroke="${col}" stroke-width="1.6"/>`:""}`;
}

// alerts
function toast(a){
  const col=catColor(a.cat);
  const el=document.createElement("div"); el.className="toast";
  el.style.border=`1px solid ${col}`; el.style.color=a.side==="BUY"?BUY:SELL;
  el.innerHTML=`<span>🚨</span><span class="badge" style="background:${col};color:#0A0D12;font-size:9px">${a.cat}</span>${a.side} ${a.cat} ${fmt(a.strength)}`;
  $("toasts").appendChild(el); setTimeout(()=>el.remove(),3000);
}
function renderAlerts(){
  $("alerthist").style.display=S.alerts.length?"block":"none";
  $("alertrows").innerHTML=S.alerts.map(a=>`<div class="arow">
    <span style="color:${DIS}">${a.t.slice(0,5)}</span><i style="background:${catColor(a.cat)}"></i>
    <span style="color:${a.side==="BUY"?BUY:SELL};font-weight:600">${a.side} ${a.cat}</span>
    <span class="as">${fmt(a.strength)}</span></div>`).join("");
}

// dev overlay + FPS
let frames=0,fpsVal=0;
(function fpsLoop(){frames++;requestAnimationFrame(fpsLoop);})();
setInterval(()=>{fpsVal=frames;frames=0;$("fps").textContent=fpsVal;renderDev();},1000);
function renderDev(){
  if($("devov").style.display!=="block")return;
  const s=S.stats||{};
  const rows=[["FPS",fpsVal,fpsVal>=55?BUY:WARN],["TICK/SEC",s.tick_per_sec??"—",TXT],
    ["QUEUE",s.queue_depth??"—",TXT],["DROPPED",s.dropped??"—",s.dropped==="0"?BUY:SELL],
    ["WS",s.ws_upstream??"—",BUY],["LATENCY",S.latency==null?"—":S.latency+"ms",TXT],
    ["CPU",s.cpu_percent!=null?s.cpu_percent+"%":"—",TXT],["RAM",s.ram_mb!=null?s.ram_mb+"MB":"—",TXT]];
  $("devgrid").innerHTML=rows.map(([k,v,c])=>`<div><span class="k">${k}</span><span style="color:${c};font-weight:600">${v}</span></div>`).join("");
}
$("devbtn").onclick=()=>{const o=$("devov");const on=o.style.display!=="block";
  o.style.display=on?"block":"none";$("devbtn").classList.toggle("on",on);renderDev();};

// footprint controls
$("prevbar").onclick=()=>{S.lock=false;$("plock").textContent="🔓";
  S.barView=(S.barView<0?S.bars.length-1:S.barView)-1;if(S.barView<0)S.barView=0;renderFootprint();};
$("nextbar").onclick=()=>{if(S.barView<0)return;S.barView=Math.min(S.barView+1,S.bars.length-1);renderFootprint();};
$("zin").onclick=()=>{S.zoom=Math.min(1.5,S.zoom+0.25);renderFootprint();};
$("zout").onclick=()=>{S.zoom=Math.max(0.75,S.zoom-0.25);renderFootprint();};
$("plock").onclick=()=>{S.lock=!S.lock;$("plock").textContent=S.lock?"🔒":"🔓";
  if(S.lock)S.barView=-1;renderFootprint();};

renderTabs(); connect();
</script>
</body>
</html>
```

---

# 8. Docker

**Dockerfile**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn[standard]
COPY . .
EXPOSE 8080
CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**docker-compose.yml**
```yaml
services:
  deltaengine:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    restart: unless-stopped
```

requirements.txt に `fastapi` / `uvicorn[standard]` を追記（バージョンはインストール確認できた安定版で固定）。

---

# 9. テスト（14本、221 → 235）

`tests/webapp/` 新設:

1. envelope: v=1 / type / time ISO / symbol を含む
2. d2s: Decimal→str、None→None、float入力でTypeError
3. compute_value_area: 単峰分布でPOC/VAH/VAL期待値一致
4. compute_value_area: 空levelsで(None,None,None)
5. PushBroker.confluence: BUY方向で閾値通過フラグとcount
6. PushBroker.confluence: WAITで全false / count 0
7. PushBroker.flow_score: 窓内イベントの加重平均、0件でNone
8. PushBroker.on_analysis: Payloadがexpected_rr=null / market_state・signal文字列パススルーであること
9. FLOW hook: ImbalanceResult(stacked)でBUY/SELL方向イベントが発火、strength=min(net/stack_ref,1)
10. FLOW hook: Absorption events_detected増分で1回だけ発火（同一イベントの二重発火なし）
11. FLOW hook未設定(None)でpipelineが例外なく動作（決定性無影響）
12. WSエンドポイント: 接続時HELLOが返りpayload_version=1（fastapi TestClient）
13. register/unregister: broadcast中の切断クライアントが除去される
14. config: webappセクションのバリデーション（不正portで起動失敗）

---

# 10. 完了条件

- [ ] 235本以上 green、既存221本無影響
- [ ] `grep -rn "float(" webapp/ src/` → webapp/ 0件、src/ 既存差分なし
- [ ] `docker-compose up` → `http://localhost:8080` でUI表示・WS接続・HELLO受信
- [ ] 正本ドキュメント無変更
- [ ] Payloadが WebSocketPayload仕様_v1 に完全一致（目視レビュー必須）

# 11. 報告（3点セット）

1. CompletionLog.md に完了報告追記
2. `DeltaEngine_WebApp_v3_完了.zip` として**プロジェクト全体**をZIP提出（差分のみ禁止）
3. チャット報告とZIPの両方を提出
