# P3-b 代表variant key生産可否 突合報告

作成日: 2026-07-27 JST  
対象: `VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

## 1. 成果物

全candidate/contradiction keyを52行に展開した突合表:

`ArchitectureRepository/00_Master/トリガー作成指示書群/突合表_代表variant_key生産可否_20260727.csv`

内訳:

- E01: 7行
- E02: 6行
- E03: 20行（candidate 16 / contradiction 4）
- E98: 19行（candidate 15 / contradiction 4）

## 2. 生産確認済み

- `cvd_change_5s`, `cvd_slope_5s`: SnapshotProducerの完全5秒窓出力をpre_aggregated経由でAdapterが供給する。根拠: `src/strategy_engine/ingestion/snapshot_producer.py:154-180`、`condition_adapter.py:46-61`。
- `bid_absorption_like_active`, `ask_absorption_like_active`: AbsorptionResultのclassificationをDecimal flagへ直結する。根拠: `snapshot_producer.py:68-83`、pipeline bar-close供給 `pipeline.py:544-552`。
- `bid_wall_concentration_top10`, `distance_to_nearest_bid_wall`, `ask_wall_concentration_top10`, `distance_to_nearest_ask_wall`: point-in-time book snapshotからAdapterが生成する。根拠: `condition_adapter.py:65-87`。

## 3. 未生成・欠測時omit

以下は突合表で`NOT_AVAILABLE`とし、欠測時はomitと記録した。推測による代替keyへの読み替えは行っていない。

- divergence composite、breakout attempt/follow-through/failure
- progress ticks、no-progress ratio
- refresh/pull
- passive defense holding/failed
- E98のOI 3 key（P2 pipelineは`oi_samples`を供給しない）

E98 OIの根拠: `condition_adapter.py:89-111`は`oi_samples`が存在する場合のみ計算し、SnapshotProducerのMarketState構築 `snapshot_producer.py:124-133`にはOI供給がない。

## 4. 判断

- E01: CVD slope単独をdivergenceへ読み替えず、現行binding維持。
- E02: absorptionの2 side flagは直接生産可能。ratio系・defense系は未生成のため実装済み扱いしない。
- E03: wall point-in-time値を崩壊差分へ読み替えず、現行binding維持。
- E98: OI・defense系は未生成のため実装済み扱いしない。正本CSV変更はこの表に基づく決裁後に限定する。

`production_status`列追加は正本schema変更となるため、本報告の範囲では実施していない。

## 5. 検証

- P3-a回帰: 581 passed, 1 skipped。
- runtime有効化・発注権限: 0のまま。
- 正本binding CSV: 未変更。
- commit/push: 未実施。

## 6. 次の再開位置

突合表を根拠に、E02を直接生産可能なabsorption flagへ縮小するかを決定する。E01/E03/E98は意味を変える代替がないため、producer追加工程（P3-c）まで現行bindingを維持する。
