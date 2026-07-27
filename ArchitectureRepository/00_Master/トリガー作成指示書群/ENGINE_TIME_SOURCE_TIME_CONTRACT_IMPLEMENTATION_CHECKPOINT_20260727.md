# Engine/Source Time契約 実装チェックポイント

日付: 2026-07-27 JST

## 決定

`engine_time_ns`はmonotonic専用、UTC epochは`source_time_ns`へ分離する仕様を`ENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.md`へ追記し、実装へ反映した。

## 変更

- `src/strategy_engine/ingestion/market_state.py`: MarketStateSnapshotへsource_time_nsを追加。engine_time_nsのmonotonic契約を明示。
- `src/pipeline.py`: Replayは最初のsource eventを原点にした経過ns、Liveはtime.monotonic_ns()をengine_time_nsへ供給。bar source datetimeはsource_time_nsへ供給。
- `src/strategy_engine/ingestion/snapshot_producer.py`: source_time_ns基準で未来観測を除外。旧呼出しはengine_time_nsをsource基準へフォールバック。trade_delta重複は既存値を保護。
- `src/strategy_engine/ingestion/condition_adapter.py`: CVD/OI窓はsource_time_ns優先。pre_aggregatedは既存adapter出力を上書きしない。
- `tests/strategy_engine/test_snapshot_producer.py`: 衝突保護・未来観測排除に合わせて期待値を更新。

## 検証

- 対象テスト: 43 passed。
- 全回帰: **583 passed, 1 skipped**（69.98秒）。
- py_compile: touched source files pass。
- runtime有効化0、発注権限0、raw data、検出器、収録基盤は変更なし。
- commit/push: 未実施。

## 未完了

G16正本の材料定義が未確定のため、price response履歴、wall差分/reset、breakout/passive-defense合成FLAGは未実装。これは仕様未確定に起因する残存作業であり、本変更で推測実装していない。