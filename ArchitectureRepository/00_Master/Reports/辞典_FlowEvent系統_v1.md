# 辞典 — FlowEvent 系統（DeltaEngine）v1

> 根拠: `Delta_Engine_Pro4web/` の実コード（2026-07-19 版 ZIP）。行番号は当該版のもの。
> 目的: 「フローイベントはトリガーかフックか」を毎回追い直さないための一次参照。

---

## 0. 一行で

**"FlowEvent" という名前は2つの別物を指す。混同するとロスる。**

| 呼び名 | 実体クラス | 定義場所 | 役割 | シグナルに効く？ |
|---|---|---|---|---|
| 内部 FlowEvent | `FlowEvent` | `src/orderflow/flow_detector.py:16` | 5検出器の出力。**SignalEngine の入力**になる | **効く**（`w_flow` 加重） |
| webapp FLOW | `PushFlowEvent` | `src/pipeline.py:172` | UI へ配信する `FLOW` メッセージ専用。IMBALANCE/ABSORPTION のみ v1 | **効かない**（表示専用） |

- **UI に流れる「FLOW」メッセージ = `PushFlowEvent`。`FlowEvent` ではない。**
- 両者はフィールドも違う（下表）。

---

## 1. トリガーか、フックか（結論）

**発火判定（トリガー）と運搬（フック）は別レイヤー。両方ある。**

### webapp FLOW（`PushFlowEvent`）

- **トリガー（発火判定）**は2系統:
  1. **IMBALANCE** … バー確定時。純粋関数 `_imbalance_should_fire()` が可否を決定（`pipeline.py:100`, 発火は `:506`）
  2. **ABSORPTION** … トレード駆動。`absorption.events_detected` が増えた瞬間（`pipeline.py:967`）
- **フック（運搬）**は1本:
  - `on_webapp_flow_event` → `broker.on_flow_event(ev)` → `FLOW` エンベロープを WS 配信

### 内部 `FlowEvent`

- **トリガー** … 5検出器の `process()` が非 None を返した瞬間（トレード or バー）
- **運搬** … `_emit_flow()` が ①バッファ追加 ②`on_flow_event` フック（**webapp では未配線**）
- **かつ** SignalEngine へ `flow_events` として供給されスコアに反映

---

## 2. 配線図（現行 webapp）

```
[トレード/バー]
   │
   ├─ 内部検出器5種 ─► FlowEvent ─► _emit_flow()
   │                                 ├─ flow_event_buffer(deque maxlen=500)
   │                                 │     └─► SignalEngine.evaluate(flow_events=…)  ← シグナルに効く
   │                                 └─ on_flow_event フック  ← webappでは未配線(None)
   │
   ├─ _bar_close() IMBALANCE判定
   │     └─ _imbalance_should_fire() 真 ─► PushFlowEvent(category=IMBALANCE)
   │
   └─ absorption.events_detected 増分 ─► PushFlowEvent(category=ABSORPTION)
                                          │
                          on_webapp_flow_event フック
                                          │  (main.py:136  pipeline.on_webapp_flow_event = on_webapp_flow_cb)
                                          ▼
                          broker.on_flow_event(ev)         (push_broker.py:264)
                                          ▼
                          envelope("FLOW", …) ─► _broadcast ─► WebSocket
```

> **罠**: `broker.on_flow_event` は名前に反して **`PushFlowEvent` を処理する**（`ev.category / ev.side / ev.detector` を読む）。内部 `FlowEvent` は扱わない。

---

## 3. データ構造

### 3.1 内部 `FlowEvent`（`flow_detector.py:16`）

| フィールド | 型 | 内容 |
|---|---|---|
| `event_time` | datetime | 発生時刻 |
| `kind` | str | `large_trade` / `sweep` / `exhaustion` / `unfinished_auction` / `tape` |
| `side` | str | `BUY` / `SELL` / `NEUTRAL` |
| `price` | Decimal | 価格 |
| `strength` | Decimal | 0–1 |
| `detail` | dict | 検出器別メタ |

### 3.2 webapp `PushFlowEvent`（`pipeline.py:172`）

| フィールド | 型 | 内容 |
|---|---|---|
| `event_time` | Any | 発生時刻 |
| `symbol` | str | シンボル |
| `category` | str | `IMBALANCE` / `ABSORPTION`（v1 はこの2つのみ） |
| `side` | str | `BUY` / `SELL` |
| `strength` | Decimal | 下記 §4 参照 |
| `detector` | str | `ImbalanceDetector` / `AbsorptionDetector` |
| `detail` | str | 例 `stacked_count=4` / `window_sec=…` |

### 3.3 WS 送出形（`FLOW` メッセージ）

`envelope("FLOW", …)`（`push_broker.py:27`）で下記が乗る。`strength` は `d2s()` により **Decimal→str**（float 禁則遵守）。

```json
{
  "v": "<PAYLOAD_VERSION>",
  "type": "FLOW",
  "time": "<UTC ISO>",
  "symbol": "<symbol>",
  "payload": {
    "event_time": "<UTC ISO>",
    "category": "IMBALANCE|ABSORPTION",
    "side": "BUY|SELL",
    "strength": "<decimal string>",
    "detector": "<name>",
    "detail": "<str>"
  }
}
```

---

## 4. 発火条件と strength 式（要暗記）

### 4.1 IMBALANCE（バー確定トリガー）

- 集計: `stacked_imbalances` から BUY/SELL 別に `count` を合算 → `net`（`pipeline.py:498`）
- 発火判定 `_imbalance_should_fire(net, bars_since, last_net, cooldown=3)`（`pipeline.py:100`）:
  - `bars_since is None`（未発火）**または** `bars_since >= 3` → **発火**
  - それ以外は `net > last_net`（スタック増加中）のときのみ **発火**
  - → 毎バー連発（spam）を抑止
- **strength = `min(net / (stack_ref × 2), 1)`**（`pipeline.py:512`）
  - Task-A で分母を2倍化＝**半減**。強いが極端でないスタックが 1.00 に飽和しない設計
- 状態: `_imbalance_fire_state[direction] = {"bars_since", "last_net"}`（方向別クールダウン, `pipeline.py:933`）

### 4.2 ABSORPTION（トレード駆動トリガー）

- `absorption.observe_trade()` 後、`events_detected` が前値超え → 発火（`pipeline.py:965-967`）
- `side` = `BUY_ABSORPTION`→`BUY` / それ以外→`SELL`
- **strength = `absorption.current().strength`**（検出器算出をそのまま）

---

## 5. 定数・既定値（一次ソース）

| 名前 | 値 | 場所 |
|---|---|---|
| `_IMBALANCE_COOLDOWN_BARS` | `3` | `pipeline.py:79` |
| `_IMBALANCE_MIN_VOLUME_DEFAULT` | `Decimal("0.5")` | `pipeline.py:76` |
| `flow_large_trade_min_qty`（既定） | `Decimal("5.0")` | `pipeline.py:663` |
| `flow_sweep_min_qty`（既定） | `Decimal("8.0")` | `pipeline.py:665` |
| `flow_exhaustion_ratio`（既定） | `Decimal("0.25")` | `pipeline.py:668` |
| `flow_ua_min_vol`（既定） | `Decimal("2.0")` | `pipeline.py:669` |
| `flow_tape_window_ms`（既定） | `5000` | `pipeline.py:670` |
| `flow_event_buffer` | `deque(maxlen=500)` | `pipeline.py:910` |

> 実運用の値は `config.flow_detector.*` が上書き（`pipeline.py:797-804`）。上表は未指定時の既定。

---

## 6. よくある取り違え（時間ロス防止チェックリスト）

- [ ] 「FLOW メッセージが出ない」→ 見るのは `PushFlowEvent` 経路（IMBALANCE/ABSORPTION）であって内部 `FlowEvent` ではない
- [ ] 「シグナルが動かない」→ 効くのは**内部 `FlowEvent`**（`w_flow` 加重, `signal.py:178`）。`PushFlowEvent` は表示専用で無関係
- [ ] `broker.on_flow_event` は **PushFlowEvent 用**。名前に釣られない
- [ ] webapp では `pipeline.on_flow_event`（内部フック）は**未配線**。内部 FlowEvent は UI に出ない（シグナルに入るだけ）
- [ ] IMBALANCE の飽和を疑うときは **strength 式 `net/(stack_ref×2)`** と **`stack_ref` 値**を両方見る（課題5の較正対象）
- [ ] `strength` は WS 上では**文字列**（`d2s`）。数値比較するならクライアント側で戻す

---

## 7. 関連課題との接続

- **課題5（stack_ref・min_volume 較正）** は §4.1 の strength 分母 `stack_ref × 2` と、IMBALANCE 判定の `min_volume` に直結する。`stack_ref` を上げると IMBALANCE の strength は下がり飽和が緩む。
- `min_volume`（既定 0.5）は ImbalanceDetector 側のフィルタ。null 時は E3002 警告 + 既定フォールバック（`pipeline.py:94`）。

---

## 参照ファイル

- `src/orderflow/flow_detector.py` — 内部 `FlowEvent` と5検出器
- `src/orderflow/signal.py` — `score_flow_events` / `evaluate(flow_events=…)`
- `src/pipeline.py` — `PushFlowEvent`・`_imbalance_should_fire`・`_bar_close`・absorption 発火・`_emit_flow`
- `webapp/main.py` — フック配線（`on_webapp_flow_event`）
- `webapp/push_broker.py` — `on_flow_event`（PushFlowEvent 処理）・`envelope`・`d2s`
