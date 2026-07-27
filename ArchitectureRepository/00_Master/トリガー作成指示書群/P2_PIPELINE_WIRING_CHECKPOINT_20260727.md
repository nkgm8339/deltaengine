# P2 Pipeline配線 v1.1 Checkpoint

作成日: 2026-07-27 JST
状態: P2完了、P3開始前停止

## 1. 完了内容

- `Delta_Engine_Pro4web/src/pipeline.py`に`SnapshotProducer` importを追加（line 83）。
- UTC epoch integer nanosecond変換の`_to_engine_ns`と、P3移行予定のBTCUSDT tick size定数を追加（lines 626-637）。
- Replay Pipelineにproducer生成・`_last_market_state`初期化を追加（lines 464-468）。
- Replayのtrade／FlowResponse／depth／bar-close／finalizeをproducerへ接続（lines 509-603）。
- Live Pipelineにproducer生成、`_last_market_state`、`_snapshot_producer`公開を追加（lines 1188-1193）。
- Liveのtrade／FlowResponse／通常depth／drain depth／bar-close／finalizeをproducerへ接続（lines 1220-1462）。
- CVDはPre-flight解決どおり`cvd_result.update`のみ供給。OrderBookは公開`snapshot()`を使用し、None時はomitする。
- 配線回帰テストを新規追加: `tests/test_pipeline_snapshot_wiring.py`。

## 2. 検証結果

- P2配線テスト + P1 producerテスト: **6 passed**。
- 全回帰: `python -m pytest -q tests -p no:cacheprovider --basetemp .pytest_snapshot_p2_full_20260727_1505` — **580 passed, 1 skipped in 25.02s**。
- 専用basetempは検証後に削除済み。

## 3. 変更範囲

- 変更: `src/pipeline.py`。
- 新規テスト: `tests/test_pipeline_snapshot_wiring.py`。
- 既存producerとP1テストはP1成果物として維持。
- 検出器、config、正本CSV／policy、Strategy Engine接続、runtime、raw data、収録基盤は無変更。
- `_evaluate_and_store`シグネチャは無変更。commit/pushなし。

## 4. 次の再開位置

- P3: Strategy Engine接続およびtick_sizeのconfig移行。
- 本checkpointではP3へ進まない。
