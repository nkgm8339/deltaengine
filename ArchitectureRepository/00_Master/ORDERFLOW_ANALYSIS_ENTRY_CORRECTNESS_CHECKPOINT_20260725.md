# Order Flow 分析・エントリー正確性 checkpoint

最終更新: 2026-07-25 16:57 JST  
状態: **実装前仕様固定・入力監査中**

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

