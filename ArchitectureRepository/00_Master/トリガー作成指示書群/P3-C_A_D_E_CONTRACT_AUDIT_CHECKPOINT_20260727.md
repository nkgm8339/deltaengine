# P3-C A/D/E契約監査チェックポイント

作成時刻: 2026-07-27 20:18:17 JST  
状態: **A／D／E順次解決・全回帰完了**

## 0. 2026-07-27 20:23:03 JST 再開承認

お館様から「ひとつひとつ解決しろ。それがおまえたちのしごとだ」と明示指示を受けた。
これをA、D、Eの契約設計、source実装、対象試験、全回帰までの承認として扱う。

実行順序:

1. A: source-time価格履歴とprice progress
2. D: book event履歴、時刻、gap／resync reset
3. E: wall距離の正本語義と計算の一致

各項目を独立して完成・検証し、主要工程の完了ごとに本checkpointを追記する。
完成済みFlow Price Response、3段チャート、8パターン、OI、UI、runtime有効化、
発注権限、raw data、収録基盤、commit／pushは引き続き対象外とする。

## 1. 承認範囲

`CODEX_HANDOVER_P3C_TIME_AND_REMAINING_20260727.md`の再開順序に従い、
G16正本と現行sourceからA/D/Eの実装契約を一意に導けるかを監査する。

このcheckpointは現状報告であり、正本変更、source実装、runtime有効化、発注許可、
raw data／収録基盤変更、commit／pushの承認ではない。

## 2. 確認済み正本・関連資料

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`全文
- `CODEX_HANDOVER_P3C_TIME_AND_REMAINING_20260727.md`全文
- `ENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.md`全文
- `ENGINE_TIME_SOURCE_TIME_CONTRACT_IMPLEMENTATION_CHECKPOINT_20260727.md`全文
- `P3-C_IMPLEMENTATION_GAP_REGISTER_20260727.md`全文
- `P3-C_CONTRACT_DECISION_AGENDA_20260727.md`全文
- `P3_DECISION_AND_EXECUTION_CHECKPOINT_20260727.md`全文
- `指示書_SnapshotProducer_Codex_20260727.md`全文
- `指示書_P3正本Binding縮小_tick_size移行_v3_20260727.md`全文
- `P3-C_PRODUCER_STAGE1_BLOCKER_REPORT_20260727.md`全文
- `ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`のG01、G06、G07、G09、G16、
  Source制約、Strategy使用規則
- `DRAFT_G16_COMPOSITE_RULES_AND_E98_UPDATE_20260727.md`の結論、
  G06／G07／G09転記、G16全48件、対象13件草案、UNDEFINED／MISSING、停止checkpoint
- 代表variant正本bindingのE00／E01／E02／E03／E04／E90／E98／E99

`DRAFT_G16_COMPOSITE_RULES_AND_E98_UPDATE_20260727.md`は明記どおり草案であり、
正本または実装承認として扱っていない。

## 3. 監査結論

| ID | 一意導出 | 結論 |
|---|---|---|
| A: price response履歴 | **不可** | G09は100ms／1s／5s／30sのkey名を持つが、算式、baseline、欠測／resetを持たない。P3-C議題の300秒`FlowResponseSnapshot.price_change`に対応する正本keyも存在しない。 |
| D: book履歴・時刻・reset | **不可** | G07は100ms／1s／5sの観測keyを持つが、event差分算式、reference level、source timestamp、gap／resync世代、window完成・freshness・reset契約を持たない。 |
| E: wall距離 | **不可** | G06は`nearest wall距離`とだけ定義する一方、現行adapterはtop10最大数量levelをwallとしてbestからのtick距離を出す。wall認定規則が正本にないため、名称と計算のどちらが正しいか確定できない。 |

したがって、A/D/Eはいずれも推測実装せず停止を維持する。

## 4. Aの根拠と決裁事項

現行Producerは`_flow_snapshots: dict[int, object]`へwindowごとの最新1件だけを保存し
（`snapshot_producer.py:37,59-66`）、`_price_samples()`もその最大4件を返すだけである
（同`:223-228`）。時系列履歴ではない。

正本G09は`upward/downward_progress_ticks`等を100ms／1s／5s／30sで定義するが
（Condition Dictionary`:410-453`）、具体算式、価格source、baseline選択、
同時刻重複、gap、window完成、resetを定義しない。G16の
`flow_price_divergence_active`は`STRATEGY_SPECIFIC`であり
（同`:718`）、採否・threshold・windowはvariant別検証事項である（同`:729-736`）。

決裁が必要:

1. 履歴のauthoritative source
   （normalized trade、1秒FlowResponseSnapshot、または別source）
2. 公開するCondition ID／key
3. 単位（price差、ticks、bps）と符号
4. window、baseline、retention、同時刻重複処理
5. gap／欠測／未完成window／reset時のomit条件

## 5. Dの根拠と決裁事項

現行Producerは最新`_book_snapshot`一件だけを保持する
（`snapshot_producer.py:39,85-105`）。`observe_book()`の`approved_time`は破棄される
（同`:98`）。

`OrderBookSnapshot`は`symbol`、`last_update_id`、bids、asksのみで、
source timestamp、gap、reinitialized/resync世代を持たない
（`src/orderflow/orderbook.py:69-81`）。gap／reinitializedは`ApplyResult`側にだけ存在する
（同`:84-89,168-180,212-240`）。現行pipelineはsnapshotだけをProducerへ渡し、
`ApplyResult`とdepth event timeを渡していない。

G07の100ms／1s／5s key名だけから、add/cancel/net/refresh/pull/stack/turnover/depth changeの
厳密な算式は一意に決まらない（Condition Dictionary`:304-355`）。

決裁が必要:

1. raw applied diffを集計するevent-flow方式か、point-in-time snapshot差分方式か
2. approved source timestampとwindow境界
3. comparison baselineとlevel identity追跡
4. snapshot適用、gap、resync、reconnect、symbol/session変更時の履歴reset
5. freshness上限、cooldown、window再完成までのomit
6. wall崩壊を既存G07 keyの組合せで表すか、新Condition ID／keyを追加するか

## 6. Eの根拠と決裁事項

正本:

- `bid/ask_wall_concentration_top10`: top10最大level数量比率
  （Condition Dictionary`:299,301`）
- `distance_to_nearest_bid/ask_wall`: nearest wall距離
  （同`:300,302`）

現行adapterはtop10最大数量levelを一つ選び、best priceからそのlevelまでをtick単位で計算する
（`condition_adapter.py:77-87`）。正本にはwall認定threshold、複数wall時のnearest選択、
wall不在、tie-break、距離単位がない。

決裁が必要:

1. 現行計算を正式意味とし、正本の名称／定義を合わせる
2. または、較正済みwall認定条件を満たすlevel群からnearestを選び、
   wall不在時はomitする文字どおりの意味へ計算を変える
3. 単位をticksと固定するか
4. 同数量tie、top10境界、crossed／stale／unsynced bookの扱い

## 7. 変更・検証・blocker

- 今回の変更file: 本checkpoint 1件のみ。
- source、test、正本CSV、Condition Dictionary、config、runtime、raw data、収録基盤:
  **無変更**。
- 完成済みFlow Price Response、3段チャート、8パターン、OI、UI: **無変更**。
- 既存worktreeには本監査着手前から未commit変更・未追跡fileが存在する。内容を保存し、
  reset／checkout／上書きを行っていない。
- read-only検証: 正本定義、代表binding、現行source、pipeline供給点を相互照合。
- test: source変更がないため今回追加実行なし。直前正本基準は
  **583 passed, 1 skipped**。
- commit／push: なし。
- blocker限定範囲: A/D/Eの正本契約と、それらへ直接依存するProducer／Adapter実装のみ。

## 8. 次の再開位置

お館様が§4〜§6を決裁した後、承認された契約だけを版付き正本へ反映し、
A、D、Eを独立taskへ分割して実装・対象試験・全回帰を行う。
未決裁項目とG16 composite FLAG、threshold較正、runtime有効化は引き続き停止する。

上記は20:18:17 JST時点の停止位置である。§0の20:23:03 JST明示指示により、
A→D→Eの順次解決へ再開した。

## 9. A完了checkpoint（2026-07-27 20:31:24 JST）

### 完了済み

- `PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md`へAの機械契約を固定。
- normalized tradeをauthoritative price sourceとし、source-time価格履歴をProducerへ追加。
- 300秒履歴と境界直前as-of sampleを保持し、future sampleをsnapshotから除外。
- G09既存100ms／1s／5s／30sについて、upward／downward progressをDecimal ticksで生成。
- 通常bar closeのsnapshot評価境界をbar startではなく現在のnormalized event時刻へ是正。
- Replay finalize／Live finalizeは最後の受理event時刻を評価境界に使用。
- G09に存在しない5m progress keyは追加せず、300秒履歴は既存OI joint用に供給。

### 変更file

- `ArchitectureRepository/00_Master/トリガー作成指示書群/PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py`
- `Delta_Engine_Pro4web/tests/test_pipeline_snapshot_wiring.py`

### 検証

- `py_compile`: A対象source 3件PASS。
- 対象試験: **17 passed**。
- 最初のsandbox内実行はpytest temp ACLで2 setup error。source assertion failureではない。
- 同一17件をsandbox外で再実行し全PASS。
- `git diff --check`: error 0（既存CRLF warningのみ）。

### 未完了・次の再開位置

- A: 完了。
- D: book event履歴、source時刻、gap／resync reset契約から再開。
- E、全回帰: 未完了。
- runtime有効化、発注権限、raw data、完成済みUI: 無変更。
- commit／push: なし。

## 10. D完了checkpoint（2026-07-27 20:37:25 JST）

### 完了済み

- `BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md`へDの機械契約を固定。
- applied `OrderBookUpdate`、`ApplyResult`、適用後snapshotを一組でProducerへ供給。
- source event時刻で100ms／1s／5sのG07全48 keyを生成。
- add、表示数量減少、net、best近傍top3 refresh、pull／stack ratio、
  unique level turnover、top10 depth changeを契約どおり算出。
- gap、SNAPSHOT、reinitializeでevent／baseline／snapshot履歴を即時reset。
- resync後は新baselineからwindowが完成するまでfail-closed omit。
- snapshot評価時刻より未来のbook level／eventを除外。
- Condition Dictionary G07／G09へ各機械契約の正本参照とomit条件を追記。

### 変更file

- `ArchitectureRepository/00_Master/トリガー作成指示書群/BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_snapshot_producer.py`

### 検証

- `py_compile`: D対象source PASS。
- Producer／Adapter対象: **18 passed**。
- pipeline／book resync／orderbook対象: **23 passed**。
- gap reset、window未完成omit、future level除外を専用試験で確認。
- `git diff --check`: error 0（既存CRLF warningのみ）。

### 未完了・次の再開位置

- A、D: 完了。
- E: `distance_to_nearest_*_wall`のwall認定、tie、単位、欠測契約から再開。
- 全回帰: 未完了。
- runtime有効化、発注権限、raw data、完成済みUI: 無変更。
- commit／push: なし。

## 11. E完了checkpoint（2026-07-27 20:39:42 JST）

### 完了済み

- `WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md`へEの機械契約を固定。
- wallをtop10最大数量のthreshold-free raw candidateとして定義。
- 同量candidateはbestに最も近いlevelを選択。
- concentrationとdistanceが必ず同じcandidateを参照。
- distanceをbestからの非負Decimal integer ticksへ固定し、off-gridを丸めずomit。
- bid／ask空、locked／crossed bookはwall keyを全omit。
- 既存Condition ID／keyを維持し、Condition Dictionary G06の語義を正確化。

### 変更file

- `ArchitectureRepository/00_Master/トリガー作成指示書群/WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py`

### 検証

- `py_compile`: E対象source PASS。
- Producer／Adapter対象: **20 passed**。
- tie時nearest、crossed book omit、off-grid distance omitを専用試験で確認。
- `git diff --check`: error 0（既存CRLF warningのみ）。

### 未完了・次の再開位置

- A、D、E: 対象実装と個別試験完了。
- 次: strategy_engine関連回帰、pipeline関連回帰、全回帰、最終checkpoint。
- runtime有効化、発注権限、raw data、完成済みUI: 無変更。
- commit／push: なし。

## 12. 最終checkpoint（2026-07-27 20:46:47 JST）

### 完了済み

- A: source-time価格履歴、G09 price progress、正しいevent評価境界。
- D: G07全48 key、book source時刻、gap／resync reset、future除外。
- E: wall candidate語義、tie-break、ticks、invalid book／off-grid fail-closed。
- Condition Dictionary G06／G07／G09へ機械契約を接続。
- staleな引継ぎ書、gap register、PROJECT_MEMORY、時刻契約へ解決状態を反映。

### 最終検証

- `py_compile`: touched source PASS。
- Strategy Engine全対象: **43 passed**。
- pipeline／Live／book resync／normalizer／Flow Response境界: **79 passed**。
- 全回帰: **590 passed, 1 skipped in 67.04s**。
- `git diff --check`: error 0（既存CRLF warningのみ）。
- sandbox pytest ACLで作成された本作業の一時directoryはsandbox外で削除済み。

### 未完了／限定blocker

- A、D、Eに未完了なし。
- G16 composite、CalibrationBook threshold、observe昇格、runtime有効化、発注権限は
  本作業の承認範囲外であり、未実装／未承認を維持。
- 既存worktreeの先行未commit変更・未追跡fileは保存し、reset／checkoutしていない。
- commit／push: なし。

### 次の再開位置

A/D/E材料を入力としてG16 compositeの版付き論理式を一つずつ実装する場合は、
対象variantとCalibrationBook契約を固定した上で別工程として開始する。
