# 5m・10mネイティブ実行時間軸 実装チェックポイント

時刻: 2026-07-24 11:12 JST
対象: `C:\Users\user\Desktop\deltaengine_clone`
承認範囲: ユーザーがGOを明示。5m・10mネイティブ実行系の実装を開始。元の`DeltaEngine`と`DeltaEngine01M`は対象外。

## 完了

- `PROJECT_MEMORY.md`全文確認
- 実装指示書確認
- 現行コードを監査
- 現行の1分`market.bar_timeframe`、1分中心の`evaluation_window: 1 bar`、Flowの秒窓、5m/15m補助集計の境界を確認
- 変更前のGit状態を確認

## これから

- 1分系を壊さない時間軸別のネイティブ集計基盤
- 5m・10mの独立計測・状態・Outcome境界
- 時間軸をキーに含むテスト
- その後にパイプライン・API・UIを接続

## 変更ファイル

このチェックポイント作成時点で、実装コードの変更はない。

## 検証結果

- `deltaengine_clone`のプロジェクトメモ: 読了
- 実装指示書: 存在確認
- 現行Git: `main`、作業ツリーには実装指示書の未追跡追加のみ

## 制約・注意

- 完成済みの1分Flow Price Response、3段チャート、8パターン、OI、Flow Eventは意味を変更しない。
- 5m・10mを1分結果の引き伸ばしとして実装しない。
- 未完了のまま中断する場合は、このファイルを更新して再開位置を記録する。
## 2026-07-24 11:40 JST 更新

承認範囲: ユーザーのGOに基づくclone内実装。元のDeltaEngine系は変更していない。

完了:
- `src/orderflow/cvd.py`へ10mのUTC境界定義を追加。
- `src/config.py`の許可時間軸へ10mを追加。
- `src/orderflow/native_execution.py`を追加。raw normalized tradeを同じ入力から5m/10mへ別々に投入し、各時間軸で独立CVD、Candle、Footprintを生成する。
- `tests/orderflow/test_native_execution.py`を追加。5m/10m境界、独立CVD、snapshot非破壊、finalize、1m拒否を検証。
- 既存pipelineへの未使用import・空行だけの差分は除去。既存1m実行経路の意味は変更していない。

未完了:
- Native Flow state、Event、Outcome、コスト判定の時間軸別実装。
- native candles/footprints/events/outcomesの保存層、Replay/Live pipeline、API、UI接続。
- 5m/10m execution profileと観測Flow窓の分離。

変更file:
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/src/orderflow/cvd.py`
- `Delta_Engine_Pro4web/src/orderflow/native_execution.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_native_execution.py`
- 本チェックポイント

検証:
- 対象テスト: `13 passed`（native_execution, cvd, multi_timeframe）。
- configテストは15件が通過したが、24件はpytestのWindows一時ディレクトリ削除権限でsetup error。コード assertion failureではない。
- `pipeline.py`はAST構文確認済み。既存pipelineへの実質変更は残していない。

限定blocker:
- pytestのWindows temp/cache権限問題だけ。ネイティブ集計テスト実行は阻害していない。

次の再開位置:
- native_executionを基礎に、時間軸を含むNativeFlow snapshot/event/outcomeの純粋ロジックを追加し、まず単体テストで検証する。その後storage/pipelineへ接続する。

## 2026-07-24 追記（Native Flow基礎）

完了:
- `src/orderflow/native_flow.py`を追加。5m/10mのnative bar境界でのみFlow状態を確定し、BUY/SELL pressure、price response、STALLED/TRAPPED/EFFECTIVEを時間軸別に出力する。
- `tests/orderflow/test_native_flow.py`を追加。native境界発火と5m/10m独立性を検証。

検証:
- Native Flow追加テスト: `2 passed`

未完了:
- このNative FlowはまだReplay/Live、DB、API、UIへ接続していない。
- Outcome、コスト、板・スプレッド判定は未実装。

次の再開位置:
- Native FlowのEvent/Outcomeデータ構造と時間軸付き保存schemaを設計・実装し、既存1mテーブルを壊さず接続する。

## 2026-07-24 追記（Native Event / Outcome）

完了:
- `src/orderflow/native_flow.py`へ`NativeFlowOutcome`と`NativeFlowOutcomeTracker`を追加。
- state遷移Eventは`(symbol,timeframe)`単位で管理し、5mと10mを混ぜない。
- Outcomeはnative event時刻、timeframe、horizon、forward return、最大上下幅を保持。
- テスト3件（native Flow境界・独立性・Event/Outcomeキー）合格。

未完了:
- DB保存schema、StorageWriter、Replay/Live接続、API/UI。
- コスト・スプレッド判定。

検証: `tests/orderflow/test_native_flow.py` = `3 passed`。
次の再開位置: 既存1mテーブルを変更せず、native専用保存schemaを追加する。

## 2026-07-24 追記（Native保存schema）

完了:
- `src/database/schema.py`へ`native_flow_events` / `native_flow_outcomes`専用schema・DuckDB DDL・row変換を追加。
- 主キーへ`timeframe`を含め、5m/10mの同時刻イベント衝突を防止。
- 既存`flow_response_events` / `flow_response_outcomes`は変更していない。
- Native Flowテスト4件合格（rowのtimeframe保持を追加）。

未完了:
- StorageWriter/DuckDbWriterへの実書込み接続。
- Replay/Live/API/UI接続。
- コスト判定。

次の再開位置: storage.pyへnative専用buffer・insert・flushを追加し、DuckDB/Parquetの保存テストを作る。

## 2026-07-24 追記（Storage接続）

完了:
- `DuckDbWriter`へnative_flow_events/outcomesのDDL・insertを接続。
- `StorageWriter`へnative専用buffer、batch/interval flush、Parquet dataset、書込みcounterを接続。
- `BackgroundStorageWriter`へnative用queue methodを接続。
- DuckDB `:memory:`で両テーブルの列定義を確認。

検証:
- storage.py AST構文確認済み。
- DuckDB nativeテーブル定義確認済み。
- 既存storage pytestはWindowsのpytest temp権限でfixture setup前に失敗（コードassertion failureではない）。

未完了:
- Replay/Liveからnative event/outcomeをStorageWriterへ渡す接続。
- API/UI、コスト・スプレッド判定。

次の再開位置: ReplayPipelineへNativeExecutionAggregator/NativeFlowDetector/Trackerを接続し、native candle/event/outcomeを保存する。

## 2026-07-24 追記（Storage実装検証）

完了:
- StorageWriter/DuckDbWriter/BackgroundStorageWriterへnative専用保存処理を実装。
- native event/outcomeはParquet datasetとDuckDBへtimeframe付きで保存できる構造。
- 既存pipelineへの途中接続は、未接続のまま残すと1m経路を壊すため撤回した。現在pipelineは実質無変更。

検証:
- native_execution + native_flow: `8 passed`。
- DuckDB `:memory:`でnativeテーブル列定義を確認。
- 既存storage pytestはWindows temp権限でsetup前に失敗。

未完了:
- Replay/Liveからnative処理へ安全に接続。
- API/UI、コスト判定。

次の再開位置: ReplayPipeline専用の小さな統合関数を別モジュールで作り、既存pipeline本体を直接改変する前に統合テストを通す。

## 2026-07-24 追記（Native Coordinator）

完了:
- `src/orderflow/native_execution_pipeline.py`を追加。
- native candle・Flow Event・Outcomeを一つのCoordinatorで処理し、StorageWriterへ渡す境界を固定。
- fake storage統合テスト `1 passed`、native関連合計 `9 passed`。

未完了:
- Replay/Live本体への呼び出し接続。既存pipelineへの自動置換はLive側へ誤挿入しやすく、現在は未接続で安全に戻している。

次の再開位置:
- ReplayPipeline専用の依存注入テストを先に作り、run()本体へは明示的な小差分で接続する。

## 2026-07-24 追記（Replay接続）

完了:
- `ReplayPipeline`へ`NativeExecutionCoordinator`を接続。
- normalized raw tradeごとにnative 5m/10m処理を既存1m処理と並行実行。
- native candleは既存candle保存へtimeframe付きで、Flow Event/Outcomeはnative専用保存へ送る。
- `LivePipeline`は変更していない。

検証:
- native関連統合テスト `9 passed`。
- pipeline.py AST構文確認済み。

未完了:
- LivePipelineへの接続。
- native結果のAPI/UI表示。
- コスト・スプレッド判定。

次の再開位置: Replay実データを使う統合テストを追加し、保存された5m/10m件数とtimeframe分離を確認する。

## 2026-07-24 追記（Replay実接続完了）

完了:
- ReplayPipelineのReplay部分だけへCoordinatorを接続。
- raw normalized tradeごとにnative処理を実行。
- Replay終了時にnative未確定barをfinalizeし、candle/Eventを保存。
- LivePipeline側は変更していない。

検証:
- pipeline.py AST構文確認済み。
- native coordinator / flow / execution 統合テスト `9 passed`。

注意:
- ReplayStatsの`candles_stored`は既存1m candleにnative 5m/10m candleも加算されるため、従来の「1mだけの件数」とは意味が変わる。必要なら次段で`native_candles_stored`を独立counterに分ける。

未完了:
- Live接続、API/UI、実データでの保存件数確認、コスト判定。

## 2026-07-24 追記（件数分離）

完了:
- ReplayStatsへ`native_candles_stored`、`native_flow_events_stored`、`native_flow_outcomes_stored`を追加。
- 既存`candles_stored`は1m基準へ戻し、native candle件数を差し引いて意味を維持。
- native Coordinator自身もcandle件数を保持。

検証:
- native Coordinator/Flowテスト5件合格。
- pipeline.py AST構文確認済み。

未完了:
- Live接続、API/UI、実データReplay保存確認、コスト判定。

## 2026-07-24 追記（05M名称変更）

完了:
- root files `DeltaEngineClone_README.md` -> `DeltaEngine05M_README.md`。
- `DeltaEngineClone.bat` -> `DeltaEngine05M.bat`。
- `data_clone`の実体を`data_05M`へ移動。
- DuckDBを`orderflow_05M.duckdb` / `.wal`へ変更。
- config paths、起動bat、README、WebAppタイトルを`DeltaEngine05M` / `data_05M`へ更新。
- フロントbadgeは既に`05M`。

未完了・限定blocker:
- 親フォルダ`deltaengine_clone` -> `deltaengine_05M`のrenameはWindowsでAccess denied。残留pytestプロセスを終了して再試行したが、sandbox/ACLまたは外部プロセスのロックで拒否された。
- root folder renameだけ未完了。中身の命名変更は完了。

次の再開位置:
- VS Code/Explorer/ターミナル等で`deltaengine_clone`を開いているプロセスを閉じた後、親フォルダからrenameを再実行する。
