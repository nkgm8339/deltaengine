この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_TradeStream_Sync_v1

**対象**: 2件
1. @aggTrade → @trade 恒久切り替え（config・コード・正本の整合）
2. Order Book 初期同期 lenient 方式の ADR 記録

**前提**: 207 passed

---

## 0. 背景

### 件1: @aggTrade → @trade

BugFix_Live で判明した事実: Binance Futures の `wss://fstream.binance.com/ws` + SUBSCRIBE で `btcusdt@aggTrade` を購読しても aggTrade イベントが到着しない（ws_probe2.py で確認済み）。`btcusdt@trade` は正常に到着する。

現状の対処は `tools/live_verify.py` の実行時置換のみ。`config.yaml` の `subscribe_streams` は `btcusdt@aggTrade` のまま、`binance.yaml` の `trade_id` は `a`（aggTrade 用）のまま。本番ライブ経路（`LivePipeline.from_config`）を使うと Bug 1 が再発する。

本指示書で `@trade` を正式採用し、config・profile・コード・正本を一貫させる。

`@trade` イベントのフィールド構造:
- `e`: `"trade"`
- `t`: 個別約定 ID（dedup キー）
- `a`: 集約取引 ID（参考値、dedup には不使用）
- `E`, `T`, `s`, `p`, `q`, `m`: aggTrade と同一

したがって `trade_id` マッピングは `a` → `t` に変更する。`trade_id_fallback` は不要になる。

### 件2: lenient 同期

BugFix_Live の指示書は `first_update_id <= sync_id+1 かつ final_update_id >= sync_id+1` の厳密同期条件を指定したが、Binance Futures `@depth@100ms` は diff 間の `U`（first_update_id）が連続しない。`pu` フィールドで連続性を保証する設計のため、厳密条件は成立しない。実装の lenient 方式（最初の非 stale diff で同期完了）が正しい。ADR として記録する。

---

## 1. 修正ファイル

### 1.1 `config/config.yaml`

`subscribe_streams` を変更:

```yaml
  subscribe_streams:
    - "btcusdt@trade"
    - "btcusdt@depth@100ms"
```

### 1.2 `config/profiles/binance.yaml`

`trade_id` と `trade_id_fallback` を変更:

```yaml
field_mapping:
  event_time: E
  trade_time: T
  trade_id: t
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
```

- `trade_id: a` → `trade_id: t`
- `trade_id_fallback: t` の行を削除

ファイル冒頭のコメントも更新:

```
# Phase6→BugFix_Live: subscribe_streams uses `@trade` (config.yaml). The Binance
# Futures @trade payload carries the individual trade id in field `t`. The
# aggregate trade id `a` is also present but is not used as dedup key.
# trade_id is therefore mapped to `t`.
# NOTE: @aggTrade stream is unavailable on Binance Futures /ws + SUBSCRIBE
# endpoint (confirmed via ws_probe2.py). ADR-006 records this decision.
```

### 1.3 `src/acquisition/binance_ws.py`

モジュール docstring の以下の記述を更新:

旧: `Endpoint model: the config uses the raw single-connection endpoint` から始まる段落

新:

```
Endpoint model: the config uses the raw single-connection endpoint
``wss://fstream.binance.com/ws`` and subscribes via a control frame
(``{"method":"SUBSCRIBE","params":[...],"id":1}``); messages then arrive
*unwrapped* (top-level ``e`` discriminates the event type). ``is_agg_trade``
is retained for backward compatibility but the live feed uses ``@trade``
(ADR-006). ``is_agg_trade_or_depth`` accepts both ``"aggTrade"`` and
``"trade"`` event types so tests using aggTrade fixtures continue to pass.
```

`is_agg_trade` の docstring に 1 行追記:

```python
def is_agg_trade(message: Any) -> bool:
    """True for a Binance aggTrade event — the trade feed the CVD path consumes.

    Used as the DataReceiver ``validate`` predicate so subscription-ack and
    order-book (depthUpdate) frames are filtered out (and counted) before
    normalization, keeping the CVD path aggTrade-only (Phase6 decision).
    Kept for backward compatibility; pipeline.py still uses this predicate.

    .. deprecated:: BugFix_Live
        Live feed uses @trade (ADR-006). Use ``is_agg_trade_or_depth`` instead.
    """
```

### 1.4 `src/normalization/normalizer.py`

`trade_id_fallback` ロジック（L229 付近）を削除する必要はない。profile に `trade_id_fallback` キーが存在しなければ実行されないため、コードは残置して汎用性を維持する。変更なし。

### 1.5 `tools/live_verify.py`

実行時置換ロジックを削除:

```python
    # 以下の 3 行を削除:
    # pipeline.subscribe_streams = [
    #     s.replace("@aggTrade", "@trade") for s in pipeline.subscribe_streams
    # ]
```

削除後、`pipeline.subscribe_streams` はそのまま使用される（config.yaml が `@trade` になるため）。

コメント `# Binance Futures @aggTrade WS stream is unavailable...` も削除。

### 1.6 `tools/ws_probe.py`

デフォルトストリームを変更:

```python
    stream = sys.argv[1] if len(sys.argv) > 1 else "btcusdt@trade"
```

### 1.7 `tools/ws_probe2.py`

デフォルトストリームを変更:

```python
    stream = sys.argv[2] if len(sys.argv) > 2 else "btcusdt@trade"
```

---

## 2. 正本更新

### 2.1 YAMLReference（現行 v3.2）→ v3.3

§2 Sample Configuration の `subscribe_streams` を変更:

```yaml
    - "btcusdt@trade"
```

§4 Exchange Profiles のサンプル Binance profile を変更:

```yaml
field_mapping:
  event_time: E
  trade_time: T
  trade_id: t
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
```

§4 の注記コメントを更新: aggTrade → trade の経緯を 1 行で記載。

### 2.2 ADR-006_TradeStream_Selection_v3.0.md（新規）

以下の全文をそのまま使用:

```markdown
# ADR-006 — Trade Stream Selection

**Status**: Accepted
**Version**: v3.0

---

# Context

The platform originally subscribed to `btcusdt@aggTrade` on Binance Futures (`wss://fstream.binance.com/ws` + SUBSCRIBE). During live verification (BugFix_Live), no aggTrade events were received. Investigation with `ws_probe2.py` confirmed that `@aggTrade` is not delivered on this endpoint, while `@trade` (individual trade stream) works correctly.

`@trade` events carry the same fields as `@aggTrade` (`E`, `T`, `s`, `p`, `q`, `m`) plus the individual trade id `t`. The aggregate trade id `a` is also present. The only functional difference is the dedup key: `@aggTrade` uses `a` (aggregate), `@trade` uses `t` (individual).

---

# Decision

1. The platform subscribes to `btcusdt@trade` instead of `btcusdt@aggTrade`.
2. The dedup key (`trade_id` in the exchange profile) maps to `t` (individual trade id).
3. The `trade_id_fallback` mechanism in the normalizer is retained for generality but the Binance profile no longer uses it.
4. `is_agg_trade_or_depth` accepts both `"aggTrade"` and `"trade"` event types so existing test fixtures (which use `e: "aggTrade"`) remain valid without modification.

---

# Rationale

- `@aggTrade` is confirmed unavailable on the Binance Futures `/ws` + SUBSCRIBE endpoint.
- `@trade` provides equivalent data at individual-trade granularity (equal or higher resolution).
- Changing the dedup key from `a` to `t` is semantically correct: each `@trade` event represents one fill, and `t` uniquely identifies it.

---

# Consequences

Positive

- Live pipeline works without runtime workarounds.
- Config, profile, and code are consistent.

Trade-offs

- Individual trades are higher frequency than aggregate trades. Volume per event may be smaller. No impact on CVD/Footprint/Imbalance correctness (they process per-event regardless of granularity).
- Existing test fixtures use `e: "aggTrade"` with field `a` as trade_id. These remain valid because `is_agg_trade_or_depth` accepts both event types and the normalizer `trade_id_fallback` mechanism handles `a` when `t` is absent (aggTrade payloads have `a` but not `t`).

---

# Related Documents

- YAMLReference
- WebSocket
- ExchangeConnectorReference
- ADR-003_Concurrency_Model
```

### 2.3 ADR-007_OrderBook_Initial_Sync_v3.0.md（新規）

以下の全文をそのまま使用:

```markdown
# ADR-007 — Order Book Initial Sync (Lenient Mode)

**Status**: Accepted
**Version**: v3.0

---

# Context

The Binance Spot documentation specifies a strict initial sync condition for order book depth diffs:

> Drop any event where `u` is <= `lastUpdateId` in the snapshot. The first processed event should have `U` <= `lastUpdateId`+1 AND `u` >= `lastUpdateId`+1.

This condition assumes contiguous `U` values between consecutive diffs. On Binance Futures, `@depth@100ms` diffs do not have contiguous `U` values; instead, continuity is guaranteed by the `pu` (previous final update id) field. The strict `U <= lastUpdateId+1` condition never matches, causing all diffs to be rejected permanently.

---

# Decision

`OrderBookStateManager.apply_initial_sync(snapshot_update_id)` uses a lenient sync mode:

1. After the REST snapshot is applied, diffs with `final_update_id <= snapshot_update_id` are counted as `diffs_stale` and discarded.
2. The first diff with `final_update_id > snapshot_update_id` completes the sync.
3. After sync, gap detection uses `pu`-based continuity (preferred) or `U == last_u + 1` fallback.

---

# Rationale

- The strict Spot-style condition is inapplicable to Futures `@depth@100ms`.
- The lenient mode correctly handles the Futures update id gap between REST snapshot and first WS diff.
- Post-sync gap detection via `pu` is the correct Futures continuity mechanism.
- Live verification confirmed: `book_diffs_applied: 292`, `book_gaps_detected: 0`, `book_diffs_rejected_before_snap: 0`.

---

# Consequences

Positive

- Order book sync works correctly on Binance Futures.

Trade-offs

- If the platform is ported to Binance Spot, the strict condition may need to be re-evaluated as an option.

---

# Related Documents

- Absorption
- DataNormalizer
- WebSocket
```

### 2.4 CHANGELOG 追記

`v3.6.0` の上に追加:

```markdown
# v3.6.1 — 2026-07-08

## Changed

- YAMLReference v3.2 → v3.3: `subscribe_streams` を `@aggTrade` → `@trade` に変更。Exchange Profile サンプルの `trade_id` を `a` → `t` に変更、`trade_id_fallback` を削除。

## Added

- ADR-006_TradeStream_Selection_v3.0.md: Binance Futures @trade ストリーム採用を決定。
- ADR-007_OrderBook_Initial_Sync_v3.0.md: Order Book 初期同期の lenient 方式を記録。

## Implementation

- `config.yaml`: `subscribe_streams` を `@trade` に変更。
- `binance.yaml`: `trade_id: t`、`trade_id_fallback` 削除。
- `live_verify.py`: 実行時置換ロジック削除。
- `binance_ws.py`: docstring 更新。
- `ws_probe.py` / `ws_probe2.py`: デフォルトストリーム変更。
```

---

## 3. テスト

既存 207 本は無変更。テスト内の fixture は `e: "aggTrade"` + フィールド `a` のままだが、`is_agg_trade_or_depth` が両方を受け入れ、normalizer の `trade_id_fallback` が `t` 不在時に `a` へフォールバックするため、全テストはそのまま通る。

新規テスト追加: なし（既存カバレッジで十分）。

**完了条件**: 207 本以上 green、既存 207 本無影響。

---

## 4. 正本操作手順

1. `YAMLReference_v3.2.md` → `YAMLReference_v3.3.md` として新規作成（旧版削除）
2. `ADR-006_TradeStream_Selection_v3.0.md` を `00_Master/ADR/` に新規作成
3. `ADR-007_OrderBook_Initial_Sync_v3.0.md` を `00_Master/ADR/` に新規作成
4. `CHANGELOG.md` に v3.6.1 エントリを追記

---

## 5. 報告

CompletionLog.md 追記 + `DeltaEngine_TradeStream_Sync_完了.zip`（プロジェクト全体）
