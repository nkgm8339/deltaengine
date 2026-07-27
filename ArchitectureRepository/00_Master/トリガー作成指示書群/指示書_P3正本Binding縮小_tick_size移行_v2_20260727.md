# 指示書: P3 正本binding縮小 + tick_size config移行 v2

作成日: 2026-07-27
作成者: Claude web
対象ブランチ: ui-refresh-v2
前提: P2完了（580 passed, 1 skipped）およびP3 Stage 1調査完了
参照: `P2_PIPELINE_WIRING_CHECKPOINT_20260727.md`、P3 Stage 1調査結果

## 0. 目的

P2で追加された暫定`_BTCUSDT_TICK_SIZE`をconfig供給へ移行し、代表variantのbindingを
現実に生産可能なcondition keyへ縮小する。

本書はwebレビュー用の実装指示書案である。お館様の承認前にStage 2を開始してはならない。

## 1. Stage 1調査で確認済みの事実

### 1.1 正本binding

binding正本は
`ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`
である。

代表variantの現行行:

- E01: CSV:363。candidateは`flow_price_divergence_active`、`cvd_change_5s`、
  `cvd_slope_5s`、`upward_progress_ticks_1s`、`downward_progress_ticks_1s`。
  contradictionは`upside_breakout_follow_through`、`downside_breakout_follow_through`。
- E02: CSV:364。candidateは`bid_absorption_like_active`、
  `ask_absorption_like_active`、`buy_no_progress_ratio_1s`、
  `sell_no_progress_ratio_1s`。contradictionはbid/ask passive defense failed。
- E03: CSV:365。candidateはbreakout attempt、progress、wall、refresh/pull、
  passive defenseの16 key。contradictionはbreakout failureとpassive defense failed。
- E98: CSV:368。candidateはOI、wall、refresh/pull、passive defenseの16 key。
  contradictionは`open_interest_change_5m`、`open_interest_pct_change_5m`、
  `bid_passive_defense_failed`、`ask_passive_defense_failed`。

### 1.2 P1/P2実生成keyとの突合

- Producerは完全window時の`cvd_slope_5s`を生成する
  （`src/strategy_engine/ingestion/snapshot_producer.py:154-180`）。
- ProducerはFlowResponseから`trade_delta_30s`／`trade_delta_5m`を生成するが、
  300s `price_change`および`flow_price_divergence_active`は生成しない
  （同:144-152、214-219）。
- `bid_absorption_like_active`は`BUY_ABSORPTION`時にDecimal `1`として生成する
  （同:68-83）。
- Adapterはbook snapshotから`bid_wall_concentration_top10`を比率、
  `distance_to_nearest_bid_wall`をtick単位で生成する
  （`src/strategy_engine/ingestion/condition_adapter.py:65-87`）。
- OI keyはOI samplesがある場合のみ生成される
  （同:89-111）。P2 pipelineはOI samplesを供給していない。

### 1.3 E98承認文書

`承認文書_E98修正版_20260727.md:17-20`で、
`downside_breakout_failure`はcandidate、`downside_breakout_follow_through`はcontradiction。
反映時期はSnapshot Producer完成後、Composite Synthesis Stage 2と合わせる
（同:31-34）。

## 2. お館様に確定を求める事項

以下4項目を承認してからStage 2へ進む。

### D1: E01 price response key

次のどちらかを選ぶ。

- A案: `FlowResponseSnapshot(300s).price_change`用の新Tier A keyを正本に追加する。
- B案: E01を`cvd_slope_5s`と既存keyだけの縮小bindingにし、price response条件を後続へ延期する。

推測でkey名・単位・thresholdを決めてはならない。

### D2: E03 wall崩壊差分

次のどちらかを選ぶ。

- A案: P3で前snapshot差分のproducerを追加する。差分window・freshness・reset契約が必要。
- B案: E03を現行のpoint-in-time wall keyだけへ縮小し、崩壊差分を後続へ延期する。

既存の`bid_wall_concentration_top10`と`distance_to_nearest_bid_wall`を差分keyへ
無言で読み替えてはならない。

### D3: E98 OI供給

次のどちらかを選ぶ。

- A案: P3でOI sample供給経路を追加し、E98をOI key中心に維持する。
- B案: OI keyも現行producer経路では欠測omitとし、E98縮小bindingを正本へ反映する。

### D4: tick_size config schema

`config.market.tick_size`をDecimal文字列として追加することを承認する。
変更候補は以下である。

- `src/config.py:230-234`（SCHEMA）
- `config/config.yaml:9-12`（default）
- `ArchitectureRepository/40_Reference/YAMLReference_v3.4.md:22-25`（canonical sample）
- `tests/test_config.py:29-33`、`tests/webapp/test_push_broker.py:607-624`（fixture）
- `src/pipeline.py:384-400,935-949`（from_config供給）

既存の`Decimal(str(...))`変換パターン（`pipeline.py:966-969`）に合わせ、
`float()`は禁止する。

## 3. Stage 2実装（D1-D4承認後のみ）

1. D1-D3の決定に従い、代表variantのE01/E02/E03/E98 bindingをCSVで更新する。
2. E98では、承認された縮小範囲外のdefense/breakout keyをcandidate／contradictionから除去する。
3. D4に従いschema、default YAML、canonical sample、必要fixtureを更新する。
4. pipeline.pyから`_BTCUSDT_TICK_SIZE`（現行定義: `pipeline.py:637`、参照:同:552,603,1303,1463）を除去し、
   config由来のDecimal tick sizeをReplay／Liveへ渡す。
5. `tests/test_pipeline_snapshot_wiring.py`へconfig tick sizeの供給確認を追加する。
6. bindingのbefore/after、生成key、単位、欠測omitを実測確認する。

## 4. 完了基準

- 正本CSVの変更がD1-D3承認内容と一致する。
- `_BTCUSDT_TICK_SIZE`の定義・参照が0件になる。
- `market.tick_size`がReplay／Live双方へDecimalで供給される。
- runtime有効化0、発注権限0を維持する。
- 既存検出器、raw data、収録基盤は無変更。
- 回帰: P2基準の580 passed, 1 skipped以上を維持する。
- commit/pushはお館様の指示まで行わない。

## 5. 停止条件

- D1-D4の承認が揃っていない。
- key名、単位、window、差分、OI供給が正本から一意に決まらない。
- config schemaとcanonical YAMLReferenceに齟齬がある。
- 未生産keyを実装済みとしてbindingへ残す必要が生じる。
- 既存検出器、runtime、発注系、収録基盤の変更が必要になる。

上記の場合は実装を停止し、ファイル・行番号付きで報告する。
