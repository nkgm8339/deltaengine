# Order Flow 分析・エントリー正確性 checkpoint

最終更新: 2026-07-25 23:39 JST
状態: **固定期間評価・詳細説明レポート完了**

## この作業の目的

DeltaEngine開発の中心を、次の二つとして分離検証する。

1. **分析の正確さ**
   - 観測時点で上方向／下方向と判断した内容が、その後の実価格方向と一致したか。
2. **エントリー時点の正確さ**
   - 同じ分析内容でも、どの状態・どの時点で架空エントリーした場合に正しい方向を捉えたか。

画面、保存基盤、Entry Specを完成させること自体を目的にしない。
スプレッド条件だけで分析またはエントリーを失敗と結論しない。

## ユーザーの最新承認範囲

- 最初はBinance実約定で検証する
- 実際の取引先はHFMなので、接続中MT5の実価格でも同じ検証を行う
- BinanceとHFMの両方を使用し、結果を別々に報告する
- ゼロスプレッドの架空取引を多数行い、分析とエントリー時点の正確さを出す
- 決済方法の最適化は後回しとし、10分から1時間後の固定時点を使う
- 工程ごとにユーザーへ報告する

## 今回の固定評価境界

### 市場データ

- `BINANCE`
  - 保存済みの実約定価格を使用する
  - signal時刻以後の最初の有効約定をentry価格とする
- `HFM_MT5`
  - 起動中の `HFM Metatrader 5` から `#BTCUSDr` の実tickを読み取る
  - Bid／Askは保存するが、今回の主評価価格はmid `(Bid + Ask) / 2`
  - HFM server timeをUTCと誤認しない
  - 保存済みのsource time／local received time対応と現在tickの実測で
    clock offsetが一致した場合だけ正規化する
  - 推測offset、旧日付だけの別録画、Binance価格によるHFM補間は使用しない

### 分析方向

完成済みFlow Price Responseの状態名の意味を変えず、次を方向仮説とする。

- `BUY_EFFECTIVE` → `BUY`
- `SELL_EFFECTIVE` → `SELL`
- `BUY_TRAPPED` → `SELL`
- `SELL_TRAPPED` → `BUY`

`BUY_STALLED`／`SELL_STALLED`は、それ自体では方向確定としない。
エントリー時点研究だけの対照として、pressure sideと反対sideを別candidateにして
両方の結果を出す。良かった側だけを後付け採用しない。

### 固定保有時間

- 600秒（10分）
- 1,200秒（20分）
- 1,800秒（30分）
- 2,700秒（45分）
- 3,600秒（60分）

結果を見て保有時間を変更しない。全時間を同時に出す。

### ゼロスプレッド架空取引

- spread控除なし
- 手数料なし
- slippageなし
- TP／SLなし
- 動的決済なし
- signal以後の最初の価格でentry
- entryから固定時間後の最初の価格でexit
- BUYは価格上昇、SELLは価格下落を正しい方向とする

### 分析とエントリーを混同しない集計

- **分析decision集計**
  - 全ての観測decisionを評価する
  - rolling更新や時間窓の重複を含むため、独立取引数とは呼ばない
- **エントリーreplay集計**
  - candidate種別、時間窓、固定保有時間ごとに、保有中の重複entryを除外する
  - 実際に一つずつ入った場合の架空取引勝率として扱う

各市場、状態、方向、観測窓、固定保有時間について最低限次を出す。

- decision／entry件数
- 正方向件数、逆方向件数、同値件数
- 正確率
- signed returnの平均・中央値
- MFE／MAEの中央値
- MFE／MAE到達までの時間中央値
- 欠測、entry lag、outcome lag、data gap

## 完了済み

- `PROJECT_MEMORY.md`全文確認
- Session handoff、Entry Spec v1 checkpoint、評価書を全文確認
- 既存Entry Spec v1はスプレッド評価を中心に結論したため、
  今回の目的を満たしていないと確認
- Binance `flow_response_events`:
  - 6,406行
  - 30s 3,005、60s 1,808、180s 753、300s 561、900s 166、1800s 113
- Binance native 5m／10m Flow:
  - event 292件
  - outcome 680件
- HFM Common Files実quote:
  - 63,292,519 bytes
  - 530,518 valid JSON rows
  - `#BTCUSDr`
- 保存済みlocal-clock HFM outcome:
  - 553件
  - `OK` 528件、`QUOTE_GAP` 25件
- 起動中MT5への読み取り専用接続:
  - `initialize_ok=true`
  - `terminal_connected=true`
  - server `HFMarketsGlobal-Live8`
  - positions 0、orders 0
  - `#BTCUSDr` Bid／Ask取得成功
- MT5 history APIから直近10分の実tick 2,110件取得成功

## 重要な訂正

従来の「HFM同一時計quote 0 bytes」は、ワークスペース内のbind mount targetを
host sourceと誤認した確認結果だった。実ファイルはMT5 Common Filesにあり、
63MB以上存在する。

ただしCommon Files JSONLはsource server timeだけであり、過去行ごとのlocal received
timeを持たない。今回のHFM履歴利用では、保存済みlocal-clock対応点と現在tick実測の
双方でclock normalizationを検証する。

## 変更file

- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_CHECKPOINT_20260725.md`

## 既存変更の保護

作業ツリーには本作業前から多数の変更・未追跡fileがある。巻き戻さない。
完成済み1M Flow Price Response、3段チャート、8パターン、OI、Flow Event、UIを変更しない。
Entry Spec v1のコードと結果を上書きしない。

## 現在の限定blocker

- MT5 Quote Observerは2026-07-25 15:12:47 JSTにchartから外され、
  Common Filesへのlive追記は停止中
- ただし起動中MT5 history APIから実tickを直接取得できるため、
  現在のBinance／HFMオフライン検証は継続可能
- 長期のlocal received time付き継続保存は別途復旧が必要

## 次の再開位置

1. HFM server clock offsetを保存済み対応点とlive tickで厳格監査する
2. MT5実tickを再現可能なParquet snapshotへ保存する
3. 市場共通のゼロスプレッド評価器を人工時系列で試験する
4. 固定cutoffでBinanceとHFMを別々に一回集計する


## 2026-07-25 22:50 JST checkpoint

### 完了済み

- HFM server clockを保存済み対応点199件とlive sample 20件で監査し、UTCとの差を+10,800秒と確定
- MT5 history APIから実tick snapshot 594,229件を作成
  - `2026-07-23T16:55:00.183Z`から`2026-07-25T07:55:04.962Z`
  - 最大gap 57.547秒、120秒超gap 0、invalid 0、duplicate 0、注文送信0
- 共通ゼロスプレッド評価器、実行tool、単体testを実装
- 区間extrema queryの親node更新漏れによる無限loopを特定・修正
- 対象test 9件合格
- Binance保存済み生約定＋HFM実tickの初回全評価を57.8秒で完走
  - decision 9,208件、全decision outcome 92,080件、非重複entry outcome 9,704件
  - 同時刻で有効な価格方向は市場間で約98.6%一致、signed return相関は約0.9997
- HFMは高coverage。Binance保存済み生約定には長い収録停止区間があり、`ENTRY_LAG`が多数発生
- 保存済みBinance 1分足も対象期間1,689行を監査
  - duplicate 9、60秒超gap 82、最大gap 25,920秒のため代替には不使用

### 現在の承認範囲と評価境界

- BinanceはFlow eventへ保存されたsignal時点の実約定価格をentryに使う
- 固定時間後の価格と区間OHLCは公式Binance Futures APIの確定1分足snapshotを使う
- HFMは実tick midを使う
- spread、手数料、slippage、TP／SL、動的決済は使わない
- 固定保有時間10／20／30／45／60分は変更しない

### 変更file

- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_CHECKPOINT_20260725.md`
- `Delta_Engine_Pro4web/src/orderflow/analysis_entry_correctness.py`
- `Delta_Engine_Pro4web/tools/snapshot_mt5_hfm_ticks.py`
- `Delta_Engine_Pro4web/tools/evaluate_analysis_entry_correctness.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_analysis_entry_correctness.py`
- `Delta_Engine_Pro4web/tests/tools/test_snapshot_mt5_hfm_ticks.py`
- `Delta_Engine_Pro4web/tests/tools/test_evaluate_analysis_entry_correctness.py`
- `Delta_Engine_Pro4web/data_05M/research/hfm_mt5_ticks_20260725.parquet`
- `Delta_Engine_Pro4web/data_05M/research/hfm_mt5_ticks_20260725.metadata.json`
- `Delta_Engine_Pro4web/data_05M/research/analysis_entry_correctness_20260725.json`
- `Delta_Engine_Pro4web/data_05M/research/analysis_entry_correctness_20260725.parquet`
- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_EVALUATION_20260725.md`

### 限定blocker

- Binanceローカル生約定と1分足の収録停止区間
- 影響はBinance outcome用公式snapshot取得だけに限定。HFM評価、試験、文書化は継続可能
- MT5 Quote Observerのlive追記停止は長期保存だけに影響し、現在snapshotの評価を妨げない

### 次の再開位置

1. 公式Binance Futures APIから固定期間の確定1分足snapshotを取得・監査
2. Binanceをsignal実約定価格entry＋公式1分足outcomeで再集計
3. 対象test・全回帰test
4. 評価書と`PROJECT_MEMORY.md`へ確定結果を反映

## 2026-07-25 23:13 JST checkpoint

状態: **欠損補正済み両市場評価完走・回帰試験前**

### 完了済み

- 公式Binance Futures公開REST APIから固定期間の確定1分足snapshotを取得
  - 2,341本、expected 2,341、missing 0、duplicate 0、invalid 0、gap 0
  - `2026-07-23T16:55:00Z`から`2026-07-25T07:55:59.999Z`
  - authenticated false、orders sent false
- Binance entryをFlow eventに保存されたsignal時点の実約定価格へ固定
- fixed exitとMFE／MAEを欠損ゼロの公式確定1分足へ接続
- Flow signal実価格6,234観測を公式同時刻OHLCと照合し、6,234件すべて範囲内
- 固定cutoffでBinance／HFM再集計を約51秒で完走
  - decision 9,208
  - 全decision outcome 92,080
  - 非重複entry outcome 9,704
  - Binance OK: 全decision 46,040、entry 4,852
  - HFM OK: 全decision 43,935、entry 4,651
- 市場間一致
  - 全decision paired 43,935、方向結果95.83%、return相関0.993651
  - 非重複entry paired 4,651、方向結果95.94%、return相関0.992723
- 分析内容とentry時点を分離した主要結果
  - TRAPPED reversal 10分: 全更新ではBinance 46.64%／HFM 46.26%
  - 同じTRAPPED reversalを最初の非重複entryに限定するとBinance 57.31%／HFM 55.95%
  - EFFECTIVE continuation 30分の最初の非重複entryはBinance 54.36%／HFM 54.26%
  - 全状態・全時間が一律に正しいわけではなく、entry時点の分離が必要と確認
- 新規対象test 13件合格、py_compile合格
- 注文送信0、spread／fee／slippage／TP／SL／動的決済0

### 追加変更file

- `Delta_Engine_Pro4web/tools/snapshot_binance_futures_klines.py`
- `Delta_Engine_Pro4web/tests/tools/test_snapshot_binance_futures_klines.py`
- `Delta_Engine_Pro4web/data_05M/research/binance_futures_1m_20260725.parquet`
- `Delta_Engine_Pro4web/data_05M/research/binance_futures_1m_20260725.metadata.json`

### blockerの限定範囲

- 現在の固定期間評価にblockerなし
- MT5 Quote Observer live追記停止は将来期間の継続収録だけに残る
- 現在の結果は約39時間の探索期間であり、production entry仕様を確定するには期間外追試が未完了

### 次の再開位置

1. repository全回帰testを実行
2. `PROJECT_MEMORY.md`へ目的・方法・結果・未完了を追記
3. checkpointを完了状態へ更新
4. ユーザーへ結論と次の収集工程を報告

## 2026-07-25 23:21 JST final checkpoint

### 完了

- 最終artifact再生成: 2026-07-25T14:20:02Z
- direction decision 9,208、全fixed-horizon outcome 92,080
- 非重複entry outcome 9,704
  - Binance有効unique decision 2,627
  - HFM有効unique decision 2,510
- 新規対象test 13 passed
- 全体回帰test 464 passed in 16.72s
- `PROJECT_MEMORY.md`へ目的、旧spread結論の限定、入力訂正、結果、未完了を追記
- 完成済みFlow Price Response、3段チャート、8パターン、OI、Flow Event、UI変更なし
- 注文送信0

### 残る未完了の限定範囲

- 現在約39時間と同じ期間で見つけたentry条件を、production仕様へ確定していない
- 次回は事前に条件を固定し、新しい期間外データで再評価する
- MT5 Quote Observerの継続追記復旧は、将来データ収集の独立作業として残る
- spreadその他の取引コスト適用は、期間外で分析・entry時点の正確性を再確認した後の別工程

### 再開位置

1. 今回の探索値から追試条件を事前固定する
2. 新しいBinance／HFM実データを継続収集する
3. 同じゼロスプレッドfixed horizon評価を一度だけ実行する
4. 正しい／不正確を期間外で判定し、その後に取引コストを別評価する

## 2026-07-25 23:28 JST 詳細説明レポート着手checkpoint

### ユーザー承認範囲

- 聞き手が途中を飛ばさず理解できる詳細レポートを今から作成する
- 目的、用語、入力、1件の判定方法、重複除外、件数、全結果、意味、未確定を細分化する
- 既存の機械集計表は残し、説明用レポートを別fileとして追加する
- 新たな最適化・再評価・条件変更・発注は行わない

### 完了済み

- 確定JSON／Parquetからdecision内訳、market別status、lag、aggregate、主要window別結果を再抽出
- report構成を固定

### 未完了

1. 詳細説明レポート本文作成
2. 数値・用語・artifact link照合
3. checkpoint／PROJECT_MEMORYへ成果物を追記

### blocker

- なし

## 2026-07-25 23:38 JST 詳細説明レポート本文完了checkpoint

### 完了済み

- `ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_DETAILED_REPORT_20260725.md`を新規作成
- 24段階、774行、約19,700文字
- 目的、用語、ゼロスプレッド理由、期間、実データ、入力訂正、clock、状態方向、1件の判定例を記載
- 全decisionと非重複entryの違いを時系列例で記載
- candidate／outcome／unique ID／除外件数を区別
- EFFECTIVE、TRAPPED、STALLED pressure／reversalの全10〜60分aggregateを記載
- window別の正しい例と不正確な例を両方記載
- Wilson区間、言えること／言えないこと、期間外追試の意味、次工程、再現手順を記載

### 検証結果

- 主要数値を確定JSON／Parquetと再照合
- 必須section 0〜24存在
- code fence偶数・閉鎖確認
- 参照artifact存在確認
- `git diff --check`合格

### 未完了

1. `PROJECT_MEMORY.md`とcheckpoint最終状態へ成果物linkを追記
2. ユーザーへReport pathと読み順を報告

### blocker

- なし

## 2026-07-25 23:39 JST 詳細説明レポートfinal checkpoint

### 完了

- 詳細説明レポート本文完成
- heading階層、code fence、必須section、主要数値、artifact存在、diff whitespaceを再検証
- `PROJECT_MEMORY.md`の正式成果物一覧へ詳細レポートと用途を追記
- 既存機械評価書、JSON、Parquetは変更せず参照元として保持
- コード、Flow Price Response、3段チャート、UIへの追加変更なし

### 未完了

- なし

### 次の再開位置

- ユーザーが詳細レポートを読み、理解しにくいsectionを指定した場合、そのsectionからさらに具体例を追加する
