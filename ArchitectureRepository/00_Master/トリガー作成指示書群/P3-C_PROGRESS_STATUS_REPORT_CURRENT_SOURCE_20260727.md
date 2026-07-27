# P3-c 進捗確認・現行ソース版報告

作成日: 2026-07-27 JST  
種別: 調査・報告  
位置づけ: 旧 `P3-C_PROGRESS_STATUS_REPORT_20260727.md` を置き換える現行ソース基準版

## 0. 現行ソースの固定

検証対象は、手元workspaceの次の実物ファイルである。旧版の行番号は採用しない。

| file | git状態 | 行数 | bytes | SHA-256 |
|---|---:|---:|---:|---|
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py` | `M` | 203 | 7911 | `C364B0ECCD66E7FD9F5406D7BE8D92D7554E10944FA8A1FAB0BC8AFABB50BAF7` |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py` | `M` | 69 | 2719 | `4F99D0A4E2537D9405AE4B4445434FBCFB38E6B2E2C714A66A7FF7EF74EB7766` |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py` | `??` | 589 | 22807 | `C8C5ABC09CA7DC5DB68FD941EF54DA91EB0F597FDA17DC52302C71E011E6100B` |

`condition_adapter.py` と `market_state.py` はHEADから変更済み、`snapshot_producer.py` はHEADに存在しない新規ファイルである。以後の検証はこの3ファイルを基準にする。

## 1. 問題A: `_price_samples`

適用済み。`_price_history` を走査する。

```text
348:    def _price_samples(self, source_time_ns: int) -> Iterable[TimeSample]:
349:        for sample in self._price_history:
350:            if sample.engine_time_ns <= source_time_ns:
351:                yield sample
```

```text
76:        self._price_history: deque[TimeSample] = deque()
101:    def observe_trade(self, trade: object) -> None:
114:        self._price_history.append(
115:            TimeSample(engine_time_ns=event_time_ns, value=price)
116:        )
```

`_record_price` は現行ファイルには見つからない。prune期間は300秒。

```text
23:_PRICE_HISTORY_NS = 300 * _NS_PER_SECOND
118:        cutoff_ns = event_time_ns - _PRICE_HISTORY_NS
120:        while (
121:            len(self._price_history) > 1
122:            and self._price_history[1].engine_time_ns <= cutoff_ns
123:        ):
124:            self._price_history.popleft()
```

## 2. 問題B1: `trade_delta_*`

無条件上書きではなく `setdefault` である。

```text
269:    def _pre_aggregated(self, source_time_ns: int | None) -> dict[str, Decimal]:
270:        values = self._cvd_conditions(source_time_ns)
276:            values.setdefault(f"trade_delta_{label}", _decimal(
277:                getattr(snapshot, "delta")
278:            ))
```

```text
283:    def _cvd_conditions(self, source_time_ns: int | None) -> dict[str, Decimal]:
308:            out[f"trade_delta_{label}"] = sum(deltas, _ZERO)
```

key名は `trade_delta_{label}` のままであり、改名はない。

## 3. 問題B2: `_add_pre_aggregated`

呼び出しは末尾。

```text
42:    def to_conditions(self, snapshot: MarketStateSnapshot) -> dict[str, Decimal]:
43:        conditions: dict[str, Decimal] = {}
44:        self._add_cvd(snapshot, conditions)
45:        self._add_price_progress(snapshot, conditions)
46:        self._add_walls(snapshot, conditions)
47:        self._add_open_interest(snapshot, conditions)
48:        self._add_pre_aggregated(snapshot, conditions)
49:        return conditions
```

既存keyの上書き防止:

```text
163:    def _add_pre_aggregated(
166:        for key, value in snapshot.pre_aggregated.items():
167:            out.setdefault(key, value if isinstance(value, Decimal) else Decimal(str(value)))
```

`cvd_change_5s` の出力はAdapter側 `condition_adapter.py:60`、Producer側 `snapshot_producer.py:309` の2箇所。

## 4. 問題C: 時刻

`build_market_state`:

```text
Delta_Engine_Pro4web/src/pipeline.py:564,625,1338,1507
Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py:266
Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py:134,311
```

`.to_conditions`:

```text
Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py:265
Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py:97,109,118,126,142,160,168,185,228,280,329
Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py:48,61,82,99,108,121,134,153,163,169,179,188,192,199,206
```

Replay:

```text
pipeline.py:515  event_source_ns = _to_source_ns(normalized.event_time)
pipeline.py:565  engine_time_ns=event_source_ns - replay_origin_source_ns,
pipeline.py:566  source_time_ns=event_source_ns,
```

`source_time_ns` はUnix epoch ns、`engine_time_ns` はReplay開始基準の相対差分（その他(c)）。

Live:

```text
pipeline.py:1339  engine_time_ns=time.monotonic_ns(),
pipeline.py:1340  source_time_ns=_to_source_ns(normalized.event_time),
pipeline.py:1508  engine_time_ns=time.monotonic_ns(),
```

Liveの `engine_time_ns` はmonotonic ns (b)、`source_time_ns` はUnix epoch ns (a)。

変換関数は `pipeline.py:655-662` にある。

## 5. テスト

```text
python -m pytest -q -p no:cacheprovider
590 passed, 1 skipped in 69.06s (0:01:09)
```

failedは0件。旧ベースライン `581 passed / 1 skipped` 比で `passed +9`、`skipped ±0`。

## 6. git状態

対象3ファイル:

```text
 M Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py
 M Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py
?? Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py
```

直近HEADは `d795dec docs: handover Strategy Engine work to Codex`。対象3ファイルについてHEAD blobは既存2ファイルのみで、`snapshot_producer.py` のHEAD blobはない。

## 7. 差し替え指示

旧報告書の行番号・内容は旧版ソースに基づくため採用しない。検証・レビュー時は、本報告のSHA-256と照合した現行3ファイルを使用する。
