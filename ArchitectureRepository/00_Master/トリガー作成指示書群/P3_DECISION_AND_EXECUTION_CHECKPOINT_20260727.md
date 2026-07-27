# P3 決定・実行チェックポイント

作成日: 2026-07-27 JST  
対象: `Delta_Engine_Pro4web` / branch `ui-refresh-v2`

## 1. 現時点の決定

### D4: tick_size config移行

| 項目 | 決定 | 根拠 |
|---|---|---|
| D4-1 値 | `"0.1"`（Decimal化して使用） | `Delta_Engine_Pro4web/src/pipeline.py:637` の `_BTCUSDT_TICK_SIZE = Decimal("0.1")` |
| D4-2 欠落時 | schema/load時にエラー。無言フォールバックなし | tick_size誤設定を fail-closed で検出するため |
| D4-3 後方互換 | 旧configは移行時に `market.tick_size` を追記 | 現行schemaの market 定義は `src/config.py:225-234`、YAMLは `config/config.yaml:9-12` |

### bindingの暫定判断

- E01: `cvd_slope_5s`単独ではflow-price divergenceを構成しないため、現行bindingを維持する。
- E02: `bid_absorption_like_active`は既存producerが直接生成するため候補とする。未生成ratio系を実装済み扱いしない。
- E03: point-in-timeのwall値を崩壊差分へ読み替えない。現行bindingを維持する。
- E98: P2ではOI samples供給がないため、OIを生成済み扱いしない。未生成の反証keyも維持する。

この暫定判断は、突合表完成後にkey単位で再確認する。正本CSVの変更はその確認後に限定する。

## 2. 実測済み事実

- `_BTCUSDT_TICK_SIZE` の定義: `Delta_Engine_Pro4web/src/pipeline.py:637`
- 同定数の参照: `pipeline.py:552,603,1303,1463`
- market schema現状: `Delta_Engine_Pro4web/src/config.py:225-234`
- default YAML現状: `Delta_Engine_Pro4web/config/config.yaml:9-12`
- Decimal文字列変換の既存例: `Delta_Engine_Pro4web/src/pipeline.py:966-969`
- E98承認配置: `承認文書_E98修正版_20260727.md:17-20`

## 3. 実行順序

1. 本書のD4決定に基づきP3-aを実装する。
2. P3-aと並行して、E01/E02/E03/E98の全candidate/contradiction key突合表を作成する。
3. 突合表に生産経路・単位・欠測挙動・根拠行を埋める。
4. 突合表と実測生成keyを照合し、正本CSVの変更範囲を確定する。
5. 変更範囲確定後にP3-bを実施する。

## 4. 報告基準

各工程の報告には必ず以下を含める。

- 変更ファイルの絶対パス
- before/afterのアンカー文字列
- 根拠となるファイル:行番号
- 生成keyの実測一覧
- 欠測時のfail-closed挙動
- テスト実行コマンドと実測結果
- 未完了項目・停止条件・次の再開位置

## 5. 現在の状態

- P2: 完了（580 passed, 1 skipped）
- P3-a: 未着手
- P3-b: 未着手
- P3-c: P3スコープ外
- commit/push: 未実施

## 6. P3-a完了記録

完了日時: 2026-07-27 JST

### 変更ファイル

- `Delta_Engine_Pro4web/src/config.py:225-235` — `market.tick_size`をDecimal文字列の必須schemaとして追加。
- `Delta_Engine_Pro4web/config/config.yaml:9-13` — default `tick_size: "0.1"`を追加。
- `ArchitectureRepository/40_Reference/YAMLReference_v3.4.md:22-27` — canonical sampleを更新。
- `Delta_Engine_Pro4web/src/pipeline.py:314,411,796,963` — Replay/Liveのfrom_configから`Decimal(str(config.market.tick_size))`を供給。
- `Delta_Engine_Pro4web/src/pipeline.py:353,869,557,608,1308,1468` — pipeline保持値をMarketStateSnapshotへ供給。
- `Delta_Engine_Pro4web/tests/test_config.py:132-137` — tick_size欠落時の拒否試験を追加。
- `Delta_Engine_Pro4web/tests/test_pipeline_snapshot_wiring.py:4,78,103` — Replay/Liveのconfig tick_size供給を確認。
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py:607-613` — YAML fixtureへtick_sizeを追加。

### 検証結果

- `rg "_BTCUSDT_TICK_SIZE" src --glob "*.py"`: 0件。
- `python -m py_compile src/pipeline.py src/config.py`: PASS。
- 対象テスト: 29 passed。
- 全回帰: **581 passed, 1 skipped in 66.87s**。
- runtime有効化・発注権限・正本binding CSV・検出器・raw data・収録基盤: 未変更。
- commit/push: 未実施。

### 次の再開位置

P3-aは完了。P3-bは、E01/E02/E03/E98全candidate/contradiction keyの突合表を完成させ、実測生産経路を確定してから着手する。P3-c（producer追加）は別工程として保留。

## 7. P3-b Stage 1突合表完了記録

完了日時: 2026-07-27 JST

- 成果物: `突合表_代表variant_key生産可否_20260727.csv`
- 行数: 52（E01 7 / E02 6 / E03 20 / E98 19）
- 生産確認済み: CVD 2 key、absorption 2 key、wall point-in-time 4 key。
- 未生成: divergence/breakout/progress/ratio/refresh-pull/passive-defense/OI供給。
- 正本binding CSV: 未変更。

次の判断点: E02 absorption flagのみ縮小するかを決定する。E01/E03/E98は意味を変える代替がないため現行維持し、producer追加をP3-cへ送る。

## 8. P3-b E02更新完了記録

完了日時: 2026-07-27 JST

- 正本CSV E02行のみ更新。
- E02 candidateをabsorption flag 2 keyへ縮小。
- 未生成ratio系とpassive-defense contradictionをE02から除去。
- E01/E03/E98は未変更。
- Import-Csv整合性: PASS、data rows 3336。
- 更新後全回帰: **581 passed, 1 skipped in 71.40s**。
- commit/push: 未実施。

次の再開位置: P3-b完了。E01/E03/E98の未生成keyはP3-c producer追加工程へ送る。E98の承認済みfailure/follow-through配置は、該当composite producer完成後に反映する。

## 9. P3-c Stage 1調査記録

完了日時: 2026-07-27 JST

- Price response素材はFlowResponseSnapshotに存在するが、新Tier A key契約が未定義。
- Wall差分は履歴/window/reset/freshness契約が未定義。
- OIはMarketStateSnapshotのフィールドは存在するが、供給API・pipeline入力経路が未定義。
- 推測実装をせずStage 1停止。
- 詳細: `P3-C_PRODUCER_STAGE1_BLOCKER_REPORT_20260727.md`

次の再開位置: 正本へ3材料契約を追記後、producer実装Stage 2。
