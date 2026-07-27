# P3-c 進捗確認・状態報告

作成日: 2026-07-27 JST  
種別: 調査・報告  
対象workspace: `C:\Users\user\Desktop\DeltaEngine05M`  
対象コード: `Delta_Engine_Pro4web/`

本報告作成中、コード変更は行っていない。

## 1. 問題A: `_price_samples` 履歴欠如

対象: `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`

### 1-1 現在形

適用済み。`_price_history` を走査している。

```text
348:    def _price_samples(self, source_time_ns: int) -> Iterable[TimeSample]:
349:        for sample in self._price_history:
350:            if sample.engine_time_ns <= source_time_ns:
351:                yield sample
```

`_price_history` deque:

```text
76:        self._price_history: deque[TimeSample] = deque()
```

価格履歴のprune期間は300秒。

```text
23:_PRICE_HISTORY_NS = 300 * _NS_PER_SECOND
118:        cutoff_ns = event_time_ns - _PRICE_HISTORY_NS
120:        while (
121:            len(self._price_history) > 1
122:            and self._price_history[1].engine_time_ns <= cutoff_ns
123:        ):
124:            self._price_history.popleft()
```

5分境界のas-of predecessorを1件残す実装である。

### 1-2 記録関数

`_record_price` は見つからない。`observe_trade` 内で直接記録している。

```text
101:    def observe_trade(self, trade: object) -> None:
114:        self._price_history.append(
115:            TimeSample(engine_time_ns=event_time_ns, value=price)
116:        )
```

## 2. 問題B1: `trade_delta_*` 二重書き込み

旧形式の無条件上書き行は現存しない。

```text
269:    def _pre_aggregated(self, source_time_ns: int | None) -> dict[str, Decimal]:
270:        values = self._cvd_conditions(source_time_ns)
276:            values.setdefault(f"trade_delta_{label}", _decimal(
277:                getattr(snapshot, "delta")
278:            ))
```

key名は改名されておらず、`trade_delta_{label}` のままである。`setdefault` によりCVD由来値を保護している。

`_cvd_conditions` 側の出力:

```text
283:    def _cvd_conditions(self, source_time_ns: int | None) -> dict[str, Decimal]:
306:            label = _WINDOW_LABELS[window]
307:            deltas = [_decimal(getattr(item, "tick_delta")) for item in window_updates]
308:            out[f"trade_delta_{label}"] = sum(deltas, _ZERO)
```

## 3. 問題B2: `_add_pre_aggregated` 無言上書き

対象: `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`

呼び出し位置は末尾。

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

上書き防止あり。

```text
163:    def _add_pre_aggregated(
166:        for key, value in snapshot.pre_aggregated.items():
167:            out.setdefault(key, value if isinstance(value, Decimal) else Decimal(str(value)))
```

`cvd_change_5s` の出力箇所は以下の2箇所。

Adapter側:

```text
60:        out["cvd_change_5s"] = latest.value - base.value
```

Producer側:

```text
309:            out[f"cvd_change_{label}"] = sum(deltas, _ZERO)
```

## 4. 問題C: `engine_time_ns` 判定材料

### 4-1 `build_market_state` 呼び出し

実装コード:

```text
Delta_Engine_Pro4web/src/pipeline.py:564
Delta_Engine_Pro4web/src/pipeline.py:625
Delta_Engine_Pro4web/src/pipeline.py:1338
Delta_Engine_Pro4web/src/pipeline.py:1507
```

Producer内部:

```text
Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py:266
```

テスト:

```text
Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py:134
Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py:311
```

### `.to_conditions` 呼び出し

実装コード:

```text
Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py:265
```

テスト:

```text
Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py:97,109,118,126,142,160,168,185,228,280,329
Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py:48,61,82,99,108,121,134,153,163,169,179,188,192,199,206
```

### 4-2 時刻の出所

Replay通常経路:

```text
515:            event_source_ns = _to_source_ns(normalized.event_time)
516:            if replay_origin_source_ns is None:
517:                replay_origin_source_ns = event_source_ns
564:                    self._last_market_state = producer.build_market_state(
565:                        engine_time_ns=event_source_ns - replay_origin_source_ns,
566:                        source_time_ns=event_source_ns,
```

判定: `engine_time_ns` はその他(c)。Replay開始時点を0とする相対epoch差分。`source_time_ns` はUnix epoch ns。

Replay最終bar:

```text
620:                final_source_ns = (
621:                    replay_last_source_ns
625:                self._last_market_state = producer.build_market_state(
626:                    engine_time_ns=(
627:                        final_source_ns - replay_origin_source_ns
631:                    source_time_ns=final_source_ns,
```

Live通常経路:

```text
1338:                    self._last_market_state = producer.build_market_state(
1339:                        engine_time_ns=time.monotonic_ns(),
1340:                        source_time_ns=_to_source_ns(normalized.event_time),
```

判定: `engine_time_ns` は(b) monotonic ns。`source_time_ns` は(a) Unix epoch ns。

Live最終bar:

```text
1507:                    self._last_market_state = producer.build_market_state(
1508:                        engine_time_ns=time.monotonic_ns(),
1509:                        source_time_ns=_to_source_ns(
1510:                            self._last_event_time
```

Unix epoch変換関数:

```text
655:def _to_source_ns(dt: datetime) -> int:
656:    """Convert a source datetime to UTC epoch nanoseconds."""
660:    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
662:    return (td.days * 86400 + td.seconds) * 1_000_000_000 + td.microseconds * 1000
```

## 5. テスト状態

実行ディレクトリ: `Delta_Engine_Pro4web/`

実行コマンド:

```text
python -m pytest -q -p no:cacheprovider
```

実測結果:

```text
590 passed, 1 skipped in 69.06s (0:01:09)
```

- failed: 0
- skipped: 1
- passed: 590

ベースライン `581 passed / 1 skipped` との差分:

```text
passed +9
skipped ±0
failed 0
```

## 6. git状態

### `git log --oneline -10`

```text
d795dec docs: handover Strategy Engine work to Codex
e001031 feat(strategy-engine): ingestion adapter skeleton (Tier A condition keys)
cf00f2e feat(strategy-engine): real predicate evaluator skeleton (representative variant, 9 classes)
28d5229 feat(strategy-engine): representative-variant body skeleton over contract enforcer
0b6a263 docs: update PROJECT_MEMORY with Strategy Engine design records
8ee8af9 chore: gitignore Stage 2B test temp dirs (.test_tmp_stage2b_*)
e67a2c1 add: Strategy Engine canon CSV registries (FSM/binding/routing/predicate)
aa1f43e test(strategy-contract): add replay contract rejection tests (R1-R8)
3965f94 docs(observation): propose Hook Trigger validation PDCA
c5cfb23 docs(observation): record Stage 2C start checkpoint
```

### `git status --short`

```text
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md
 M ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv
 M ArchitectureRepository/40_Reference/YAMLReference_v3.4.md
 M Delta_Engine_Pro4web/config/config.yaml
 M Delta_Engine_Pro4web/src/config.py
 M Delta_Engine_Pro4web/src/pipeline.py
 M Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py
 M Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py
 M Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py
 M Delta_Engine_Pro4web/tests/test_config.py
 M Delta_Engine_Pro4web/tests/webapp/test_push_broker.py
?? ArchitectureRepository/00_Master/トリガー作成指示書群/BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/CODEX_HANDOVER_P3C_TIME_AND_REMAINING_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/DRAFT_G16_COMPOSITE_RULES_AND_E98_UPDATE_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/ENGINE_TIME_SOURCE_TIME_CONTRACT_IMPLEMENTATION_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/ENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_COMPOSITE_SYNTHESIS_STAGE1_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P2_PIPELINE_WIRING_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P2_PIPELINE_WIRING_PREFLIGHT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-B_E02_UPDATE_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-B_PRODUCTION_MATRIX_REPORT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-C_A_D_E_CONTRACT_AUDIT_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-C_CONTRACT_DECISION_AGENDA_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-C_IMPLEMENTATION_GAP_REGISTER_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3-C_PRODUCER_STAGE1_BLOCKER_REPORT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/P3_DECISION_AND_EXECUTION_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/SNAPSHOT_PRODUCER_P1_CHECKPOINT_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/SNAPSHOT_PRODUCER_STAGE1_INVENTORY_20260727.md
?? ArchitectureRepository/00_Master/トリガー作成指示書群/WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md
?? Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py
?? Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py
?? Delta_Engine_Pro4web/tests/test_pipeline_snapshot_wiring.py
?? SNAPSHOT_PRODUCER_P1_REVIEW_20260727/
```

本報告作成中はコードを変更していない。
