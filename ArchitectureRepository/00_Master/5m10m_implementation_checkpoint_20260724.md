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

## 2026-07-24 19:34 JST 追記（PRICE・CVD・Delta・OI自動評価 着手前）

承認範囲:
- 対象は `C:\Users\user\Desktop\DeltaEngine05M` のみ。
- ユーザー考案の既存Price・CVD・Delta 8パターンを保持し、OIを第4軸にした自動評価を05M版へ追加する。
- 05Mイベントとして組み合わせを保存し、HFMの実行可能Bid/Askによる3分・5分・10分後の事後結果へ接続する。
- `DeltaEngine` と `DeltaEngine01M` は変更しない。
- 既存ファイル、既存1M機能、既存データを削除・上書きしない。

着手前監査:
- 既存8パターンは `webapp/static/index.html` の `CVD_PATTERNS` と `classifyCvdPattern()` で選択足に表示されている。
- OIは選択足へ時刻同期され、OPEN/CLOSE/CHANGEを表示している。
- PRICE・CVD・Delta・OIの8ケースは静的ガイドとして存在するが、選択足の4要素評価へ自動適用されていない。
- 5m/10m native candle・Flow Event・Outcomeの基礎と保存schemaは存在する。
- native処理はReplayへ接続済みだが、Live/API/UIとHFM実行価格評価は未接続。
- 着手前Git差分は、起動BATのDocker Compose内部名を小文字化した既知の1行だけ。

変更予定:
- 時間軸共通の組み合わせ評価器と単体テスト。
- 選択足詳細の4要素自動評価。
- native eventへ8パターン番号、OI方向、組み合わせ評価を保持する保存境界。
- Live 05M経路、履歴/API/UI、HFM quote/outcomeの安全な接続。

変更しない完成範囲:
- 既存8パターンの番号・方向判定・英語名。
- 完成済み1M Flow Price Response、3段チャート、OI raw保存、Flow Event、既存履歴。
- 単一score、確率、売買シグナルへの再統合は行わない。

検証計画:
- 全16方向ケースとOI unchanged/missingの純粋ロジックテスト。
- 既存8パターン不変テスト。
- OI時刻同期、欠測非補間、05M/10M分離、DB schema、WebSocket/UI表示テスト。
- HFM BUY Ask→将来Bid、SELL Bid→将来Askのスプレッド込み事後結果テスト。
- 対象テスト後に全体回帰と実ブラウザ相当確認。

次の再開位置:
- 共通評価器を新規追加し、既存8パターンを変えない単体テストから開始する。

## 2026-07-24 19:52 JST 追記（共通4軸評価器 完了）

完了:
- `src/orderflow/combined_context.py` を新規追加。
- ユーザー考案の既存8パターンの番号・方向条件・英語名を変更せず、OI BUILDING / UNWINDING を組み合わせた全16観測評価を定義。
- OI UNCHANGED / MISSING は別状態とし、方向を推測して補完しない。
- score、確率、売買シグナルは追加していない。
- `tests/orderflow/test_combined_context.py` を新規追加し、既存8ケース不変、全16ケース、同値規則、OI欠測を検証。

検証:
- `python -m pytest tests/orderflow/test_combined_context.py -q`
- 結果: `15 passed`（`.pytest_cache` の既知permission warningのみ）。

次の再開位置:
- 選択ローソク足詳細と組み合わせガイドを、同じ全16ケースの自動表示へ更新する。

## 2026-07-24 20:04 JST 追記（05M画面 4軸自動表示 完了）

完了:
- 選択ローソク足のOI詳細へ、PRICE・CVD・Delta・OIの4方向、組み合わせコード、評価名、日本語観測説明を自動表示。
- OI欠測は `OI DATA MISSING`、変化なしは `OI UNCHANGED` として明示し、増減を推測しない。
- 上部の組み合わせガイドを、既存8パターン × OI増減の全16ケースへ拡張。
- `CVD_PATTERNS` と `classifyCvdPattern()` の既存8分類は変更していない。

検証:
- `python -m pytest tests/orderflow/test_combined_context.py tests/webapp/test_push_broker.py -q`
- 結果: `41 passed`（`.pytest_cache` の既知permission warningのみ）。

次の再開位置:
- 既存テーブルを変えず、新規の4軸イベント表とHFM Bid/Ask事後結果表を追加する。

## 2026-07-24 20:32 JST 追記（05M蓄積・HFM実測接続 完了／全体回帰前）

完了:
- 既存表を変更せず、新規 `combined_context_events` と `hfm_context_outcomes` を追加。
- native 5m/10m確定足をLivePipelineへ接続し、5m/10mを独立キーで保存。
- 5m/10m確定足を2本前と比較して既存8パターンを判定し、対象足OPEN/CLOSEに時刻同期した実OIを結合。
- OIは20秒以内の実観測だけをas-of結合し、欠測を補間しない。
- MT5 Common FilesのHFM Bid/Ask JSONLを読み取り専用でtailし、画面上部を `HFM SPREAD USD` のリアルタイム表示へ変更。
- HFMのエントリーquoteが2秒以内のときだけ事後追跡を開始。
- 3分・5分・10分後について、LONG Ask→将来Bid、SHORT Bid→将来Askの双方を保存。表示スプレッドはこの計算に内包され、二重控除しない。
- quoteが目標時刻から2秒超遅れた結果は `QUOTE_GAP` として明示。
- MFE/MAE、quote時刻、sequence、Bid/Ask、quote lagを監査用に保存。
- `/api/history/combined-context` と `/api/history/hfm-context-outcomes` を追加。
- 最新の閉じた05M 4軸評価を画面チャート上へ表示し、再起動時は履歴から復元。
- Docker永続volumeを `data_05M` に修正し、HFMファイルをread-only bind mount。
- 同期StorageWriterのnative event enqueue誤配線を修正し、既存Replay/native保存を正常化。
- LivePipeline終了時の未定義 `native_coordinator` 参照を、実際のlive接続とfinalizeによって解消。

変更していない範囲:
- 既存8パターンの番号・名称・方向判定。
- 既存candles、native_flow_events、native_flow_outcomes、OI raw、1M Flow関連のschema。
- `DeltaEngine`、`DeltaEngine01M`。
- 売買発注、単一score、確率、シグナル生成。

検証済み:
- `docker compose config` 成功。`data_05M`とHFM read-only mountの解決先を確認。
- 共通判定、runtime、storage、HFM parser、LivePipeline、API/UI関連: `78 passed`。

長時間検証前チェックポイント:
- 次に全pytestを実行。
- その後、05M Dockerだけをbuild/restartし、health、HFM spread、DB新規表、既存データ保持を実機確認する。

## 2026-07-24 20:38 JST 追記（全体回帰 完了）

検証:
- `python -m pytest tests -q -p no:cacheprovider`
- 結果: `403 passed`。
- 初回全体回帰で、旧テストがcandles表を1mの1行だけと仮定していたため1件失敗。
- 05M版では意図どおり1m・5m・10mがtimeframe別に保存されるため、既存1m行の値を検証しつつ5m/10m別キーも確認するテストへ更新。
- 更新後の全403件が通過。

次の再開位置:
- 05M Composeだけをbuild/restartし、health、HFMリアルタイム表示、DB新規表、既存件数保持を実機確認する。

## 2026-07-24 21:09 JST 追記（05M OI・HFM実装 最終）

実機確認:
- `docker compose -p deltaengine_05m up --build -d` で05Mだけを再構築・再起動。
- コンテナ `deltaengine_05m-deltaengine_clone-1` はUp。
- `GET /health` は `{"status":"ok"}`。
- Binance bookはSYNCED、gap 0、storage queue 0を確認。
- 05M画面で `HFM SPREAD USD`、全16ケースガイド、最新05M context領域をヘッドレスEdge実画面で確認。
- HFM quoteファイルはコンテナ内からread-onlyで読め、最終値 Bid 65751.411 / Ask 65771.411 / Spread 20.000を確認。
- HFM MT5プロセスは現在停止中で、quoteファイル最終更新も停止しているため、APIは `hfm_quote_status=STALE`、画面は古い20.000をLIVE表示せず `—` とすることを確認。
- HFM端末側にインストール済み `HFMQuoteObserver.mq5` と `.ex5` は正常。リポジトリ側だけにあった文字化け済み観測EAソースも正常なMQL5へ修復。

最終テスト:
- `python -m pytest tests -q -p no:cacheprovider`
- 結果: `405 passed`。

運用:
- HFM MT5で観測EAが動きquote更新が再開すると、上部に実HFM spread USDが表示される。
- 05M 4軸event成立後、3分・5分・10分のHFM両方向実行結果が順次 `hfm_context_outcomes` に蓄積される。
- 再起動直後は、同一run内のCVD基準を守るためnative 5mを3本確定してから最初の4軸eventを作る。過去CVDと再起動後CVDを不正に跨いで即時判定しない。

変更対象:
- `C:\Users\user\Desktop\DeltaEngine05M` のみ。
- `DeltaEngine` と `DeltaEngine01M` は未変更。

## 2026-07-24 21:12 JST 追記（HFM MT5起動後 LIVE確認）

- ユーザーがHFM MT5を起動。
- HFM quote JSONLの更新再開を確認（sequence 699、Bid 65054.941 / Ask 65074.385）。
- `/api/stats` が `hfm_quote_status=LIVE`、quote age 79ms、spread USD 20.000を返した。
- ヘッドレスEdge実画面でも `HFM SPREAD USD` がLIVE表示され、別瞬間の表示値18.402 USDを確認。
- 05Mコンテキスト履歴は再起動直後のためまだ空。native 5mを3本確定後、最初の4軸eventとHFM 3/5/10分outcomeが蓄積される。

## 2026-07-24 22:00 JST 追記（3段チャート上3列の固定化 着手前）

承認範囲:
- ユーザーの明示指示により、3段チャート上のCVD divergence、Flow Response、05M contextを常設し、数字・状態だけを更新する。
- 3列の出現・消失や折返しで3段チャート領域が伸縮しないよう、3列と3段チャートの寸法を固定する。

確認済み:
- `cvddiv` はデータなしで `display:none`、検出時に `block` へ切り替わる。
- `flowresponse` はデータなしで `display:none`、到着時に `flex` となり、さらに折返しで高さが変わる。
- `nativecontext` は初期 `display:none`、最初の05M context到着時に `block` となる。
- 上記3要素が同じ固定高コンテナに入っておらず、表示切替のたびに `chartwrap` の高さへ直接影響している。

変更予定:
- 3列を固定高の常設領域へ入れる。
- 欠測時も項目名を残し、値だけ `—` とする。
- Flow 6時間窓は常に同じ6枠を出し、折返さない。
- 3段チャート本体の従来表示寸法を維持する分だけ外側panel高を確保する。
- OI線追加、既存項目削除、判定ロジック変更は行わない。

未完了:
- UI実装、回帰テスト、実ブラウザでの寸法不変確認、05Mコンテナ反映。

次の再開位置:
- `webapp/static/index.html` のCSS、3列DOM、3つのrender関数を最小差分で固定化する。

## 2026-07-24 22:10 JST 追記（3列固定化 実装・実ブラウザ確認完了）

完了:
- CVD divergence、Flow Response 6窓、05M contextを固定高94pxの常設領域へ配置。
- 欠測時も項目と時間窓を残し、値だけ `—` にした。
- `display:none` / `block` / `flex` の動的切替を3列から撤去。
- Flow Responseは6列固定・折返しなしとし、各枠の項目名と寸法を維持したまま値だけ更新する。
- 外側panelを94px拡張し、既存3段チャートのSVG座標と表示高を維持した。
- OI線追加、項目削除、判定ロジック変更は行っていない。

検証:
- WebApp対象テスト: `29 passed`。
- JavaScript構文確認: OK。
- 1920x1200の実Edgeで初期、全データ表示、欠測復帰の3状態を測定。
- 3状態すべてでstatus領域94px、chartwrap 426px、chart SVG 422px、各行26/38/26pxが完全一致し、1pxも変動しなかった。

変更file:
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- 本チェックポイント

未完了:
- 全pytest回帰。
- 05Mコンテナへの反映とライブ画面での最終確認。

次の再開位置:
- 全pytestを実行し、合格後に05M Composeだけを再build/restartする。

## 2026-07-24 22:16 JST 追記（全体回帰 完了／05M反映前）

検証:
- 最初の全pytestは既定のWindows temp `pytest-of-user` がAccess Deniedとなり、実行済み307件合格・99件setup error。コードassertion failureではない。
- workspace内basetempもsandbox ACLでAccess Deniedとなった。
- sandbox外の明示basetempで全件を再実行。
- 結果: `406 passed in 17.07s`。

限定blocker:
- pytestのsandbox内temp ACLだけ。サンドボックス外実行で全回帰合格済みのため、実装品質のblockerではない。

未完了:
- 05M Composeの再build/restart。
- ライブ画面で3列常設と3段チャート寸法不変を最終確認。

次の再開位置:
- `docker compose -p deltaengine_05m up --build -d` を05Mディレクトリだけで実行する。

## 2026-07-24 22:25 JST 追記（3列固定化 最終完了）

05M反映:
- `docker compose -p deltaengine_05m up --build -d` を実行。待機側は60秒でtimeoutしたが、Docker側は正常完了。
- `deltaengine_05m-deltaengine_clone-1` は再作成後Up。
- `/health` はok、bookはSYNCED、storage queue pending 0、HFM quoteはLIVE。
- 配信HTMLに固定status領域と594px panel定義が含まれることを確認。

ライブ実ブラウザ最終確認:
- 1920x1200 Edgeでライブデータ更新前後を比較。
- CVD divergence行26px、Flow Response行38px、05M context行26pxは常時表示。
- FLOW 6時間窓はデータ有無にかかわらず6枠を維持。
- 実際に30s/1mの状態・数値が更新され、3m/5m/15m/30mが欠測 `—` のままでも、status領域94px、chartwrap 426px、chart SVG 422pxは不変。
- 05M OIが欠測時も `OI MISSING` の項目を残し、列自体を消さない。

文書化:
- `PROJECT_MEMORY.md`へ「必要項目は常設し値だけ変える」「3段チャートを固定保護」「表示方式変更は事前相談」を恒久原則として追記。
- `UI_Spec_CommandCenter_v2.md`へ固定3列とprotected chart geometryを正本仕様として追記。

最終検証:
- 対象WebApp: `29 passed`。
- 全体回帰: `406 passed`。
- JavaScript構文: OK。
- 実ブラウザ寸法不変: OK。

一時物:
- 今回作成したpreview PNGとpytest専用temp 2フォルダは削除済み。

未完了:
- なし。OI線追加や別の表示変更は、ユーザーとの相談前のため実施していない。
