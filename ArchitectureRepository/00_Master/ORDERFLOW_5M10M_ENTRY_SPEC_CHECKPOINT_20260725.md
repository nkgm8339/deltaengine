# 5M/10M Episode entry specification checkpoint

最終更新: 2026-07-25 15:41 JST  
状態: **Entry Spec v1定義・実装・探索評価完了。HFM発注NO-GO。**

## 承認範囲

ユーザーの `OK GO` により、次を承認範囲とする。

- Episodeの買い／売りエントリー、見送り、仮説否定条件を文章で定義する
- 既存データだけを使う純粋なオフライン検証器とテストを追加する
- 1M観測窓と5M／10M outcome horizonを分離して比較する
- HFMコスト耐性を、利用可能な実測データの範囲内で評価する
- 検証結果と限定blockerを研究文書へ記録する

承認範囲外:

- LIVE注文
- MT5への発注コマンド生成または接続
- 既存1M Flow Price Responseの計算変更
- 完成済み3段チャート、8パターン、OI、Flow Event、UIの変更
- 現在の未コミット差分の巻き戻し

## 完了済み

- `PROJECT_MEMORY.md`全文確認
- `ORDERFLOW_5M10M_HANDOFF_20260725.md`全文確認
- 研究計画、固定Validation Protocol、既存Episode／Outcome／HFM time checkpoint確認
- `orderflow_episode.py`、`episode_dataset.py`、関連テストの現行実装確認
- 作業ツリーの既存未コミット差分を確認し、保護対象として扱う方針を固定
- HFM同一時計quote候補
  `data_05M/hfm/DeltaEngine_HFM_quotes_utf8.jsonl` が0バイトであることを確認

## 未完了

- エントリー仕様の固定
- 現行データでのEpisode再構築と独立候補抽出
- エントリー時点別の5分／10分MFE、MAE、終値、決着順評価
- 単純な1M状態固定保有との対照比較
- HFMコスト感応度評価
- 対象テストと回帰試験
- handoffへの結果反映

## 変更file

- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md`

## 検証結果

- 既存Episode Builderは、同一sideの
  `EFFECTIVE / STALLED / TRAPPED` の順序を一Episodeへまとめられる
- `SUSTAINED_CONFLICT`後の最初の`EFFECTIVE`を
  `AGGRESSOR_BREAKTHROUGH`、`TRAPPED`を`DEFENDER_REVERSAL`として因果的に閉じる
- 現在のOutcome evaluatorは終値、max up、max downを保存するが、
  MFE／MAEの先着順とHFMコスト閾値通過は未評価

## 限定blocker

- HFM同一時計quoteが未蓄積のため、実Bid／AskによるGate 3／4判定だけは実行不能
- blockerはHFM結合と実コスト最終判定に限定する
- Binance内の仕様固定、構造比較、概算cost hurdle評価は継続可能

## 次の再開位置

現行parquetからFlow observationとRAW価格列を再構築し、各stageで実際に利用可能な
情報を監査する。その結果を見ずに条件を後付けしないよう、比較するentry candidateを
先に本checkpointへ固定してから検証コードを追加する。

---

## 2026-07-25 15:48 JST: Entry Spec v1 事前固定

以下は集計結果を見る前に固定する研究仕様である。名称に`ENTRY`を含むが、
LIVE注文許可または売買推奨ではない。

### 1. 観測時間とOutcome時間を分離する

- 主観測は既存1M由来の`window_sec=60`とする
- 一つのEpisodeは最大600秒まで追跡する
- 観測間gapが120秒を超えたEpisodeは無効とする
- 固定5分状態の比較には`window_sec=300`を使う
- 5M／10Mは入口の状態窓ではなく、入口後の`300秒／600秒` outcomeとして比較する
- 現在存在しない`window_sec=600`を推測生成しない

### 2. 状態の意味

BUY pressureを例にすると、次のように区別する。SELLは完全に対称である。

| 観測 | 意味 | entry action |
|---|---|---|
| `BUY_EFFECTIVE`でEpisode開始 | 買い攻撃と価格上昇を初めて確認 | 早期対照候補。主entryにはしない |
| 最初の`BUY_STALLED` | 買い圧力に価格が追随しない | 待機 |
| 2回目以降の連続`BUY_STALLED` | 停滞下でも買い圧力が継続 | 早期対照候補。主entryはまだ待機 |
| 継続停滞後の`BUY_EFFECTIVE` | 買い側への突破を初めて確認 | BUY主候補 |
| 継続停滞後の`BUY_TRAPPED` | 買い攻撃に対する下方向への解放 | SELL主候補。BUYは見送り |
| opposite side／`UNCLEAR`／gap | 攻撃継続条件の消滅 | 無効・見送り |

したがって、単発の`BUY_EFFECTIVE`／`SELL_EFFECTIVE`を注文トリガーにしない。

### 3. 比較する三つの因果的入口

#### `ATTACK_V1`（早期対照）

- `AGGRESSION`を初めて観測した時刻
- 方向はpressure side
- そのEpisodeが後で停滞・突破・反転するかを入口選別へ使用しない

#### `PERSIST_PRESSURE_V1`（早期研究候補）

- `AGGRESSION → NON_RESPONSE → SUSTAINED_CONFLICT`を順番に観測した最初の時刻
- 方向はpressure side
- 後で突破したEpisodeだけを選ばない
- 目的は、解放確認前に入る価値と誤方向リスクを測ること

#### `RESOLUTION_CONFIRMED_V1`（主候補）

必須の過去列:

```text
AGGRESSION
  → NON_RESPONSE
  → SUSTAINED_CONFLICT
  → AGGRESSOR_BREAKTHROUGH または DEFENDER_REVERSAL
```

- `AGGRESSOR_BREAKTHROUGH`ならpressure sideへ入る
- `DEFENDER_REVERSAL`ならpressure sideと反対へ入る
- entry時刻は解放状態を初めて観測したevent time
- Binance構造評価の基準価格は、そのcheckpointの`last_price`
- HFM評価ではBUYは観測後のAsk、SELLは観測後のBidを別途使用する
- `SUSTAINED_CONFLICT`を経ていない単発解放は対象外

### 4. BUY entryの再現可能な判定

BUY主候補は次のどちらか一方である。

1. BUY攻撃が`AGGRESSION → NON_RESPONSE → SUSTAINED_CONFLICT`と続き、
   次に`BUY_EFFECTIVE`を観測した
2. SELL攻撃が同じ三段階を通過し、次に`SELL_TRAPPED`を観測した

BUY攻撃が`BUY_TRAPPED`になった場合はBUYしない。SELL主候補である。
SELL entryは上記を完全に反転した条件とする。

### 5. entry直後の仮説否定

trade sideを`D`、反対側を`O`とする。

Flowによる否定:

- 最初の`D_TRAPPED`
- 最初の`O_EFFECTIVE`
- data gap、時刻逆行、非正値

価格による否定基準:

- BUYは、`NON_RESPONSE`から`SUSTAINED_CONFLICT`までに観測した
  checkpoint価格の最安値を下抜いた時刻
- SELLは、同区間のcheckpoint価格の最高値を上抜いた時刻

この価格は研究上の`invalidation reference`であり、HFMのLIVE SL価格ではない。
実SLはHFM Bid／Ask、最小stop distance、滑りを含む実測後に別途固定する。

### 6. outcomeとコストhurdle

各入口から次を同時に出力する。

- 300秒／600秒のtrade-side signed return
- MFE、MAE
- MFE時刻、MAE時刻
- favorable cost hurdleと同幅のadverse hurdleのどちらが先か
- 価格invalidationがhurdleまたは固定horizonより先か

HFM同一時計quoteが無い現段階のproxy:

- 実測中央値spread: 20 USD
- 1.5倍stress: 30 USD
- entry価格ごとにUSDをbps換算し、gross signed returnから一回だけ控除する

20 USD／30 USDは利益目標ではない。現在のBinance経路が、HFMで往復spreadを
払う余地すら持つかを見る最低hurdleである。実HFM Bid／Ask評価時はspreadを
別途二重控除しない。

### 7. 重複と判定

- raw candidate件数と、600秒horizonが重ならないpurged件数を両方出す
- 同じEpisodeの複数checkpointを独立標本数へ足さない
- 三入口の比較は同じEpisodeを可能な限りpairedで示す
- 現有期間は30日未満なので、結果は`EXPLORATORY_INSUFFICIENT_DATA`
- 30日以上、purge後200 Episode以上、untouched test、block bootstrapを満たすまで
  優位性を宣言しない
- 実HFM同一時計quoteが無い限りGate 3／4を通過扱いにしない

## 次の再開位置（Entry Spec v1固定後）

この仕様を変更せず、純粋なcandidate extractorとpath evaluatorを追加する。
人工時系列で先読み防止、方向反転、hurdle先着、gap、600秒重複purgeを試験した後、
現行データを一回だけ集計する。

---

## 2026-07-25 15:54 JST: 実装完了・本集計開始前checkpoint

### 完了済み

- Episodeへ任意の`max_episode_sec`境界を追加。既定値`None`で既存挙動を維持し、
  Entry Spec v1集計時だけ600秒を指定
- `episode_entry.py`へ三つの因果的candidate extractorを追加
- pressure sideとtrade sideを分離し、`DEFENDER_REVERSAL`時だけ方向を反転
- checkpoint価格からprice invalidation referenceを固定
- 300秒／600秒のsigned return、MFE、MAE、極値時刻、cost hurdle先着、
  price invalidation先着を計算する純粋evaluatorを追加
- symbol・観測窓・candidate type単位の600秒重複purgeを追加
- `evaluate_episode_entries.py`へParquet読取り、UTCセッション別集計、
  20 USD／30 USD proxy cost、paired比較、JSON／Markdown出力を追加

### 変更file

- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md`
- `Delta_Engine_Pro4web/src/orderflow/orderflow_episode.py`
- `Delta_Engine_Pro4web/src/orderflow/episode_entry.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_orderflow_episode.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_episode_entry.py`
- `Delta_Engine_Pro4web/tools/evaluate_episode_entries.py`

### 検証結果

- `py_compile`: pass
- Episode Builder／既存Outcome／新Entry evaluator: **14 passed**
- 人工時系列で確認した境界:
  - 順序を満たさない単発状態を主candidateにしない
  - 後で無効化されたEpisodeも`ATTACK_V1`から除外せず、先読み選別しない
  - Defender reversalでtrade sideを反転する
  - favorable／adverse hurdleの先着を区別する
  - price invalidationの先着を区別する
  - 600秒ちょうどのcandidateは次の非重複標本として保持する

### 限定blocker

- HFM同一時計quote 0バイトのblockerは継続。Binance proxy集計には影響しない
- 現有期間は約1.5日であり、統計的Gate判定は行わない

### 次の再開位置

現有Flow observationsとRAW tradesをEntry Spec v1で一回集計する。
出力先は研究JSONと新規Markdownに限定し、既存Parquet、ライブ処理、UIを変更しない。

---

## 2026-07-25 16:11 JST: 固定cutoff集計完了checkpoint

### 固定した再現境界

- entry cutoff: `2026-07-25T06:40:00Z`
- outcome price cutoff: `2026-07-25T06:50:30Z`
- 同一cutoffで2回実行し、episodes 865、raw candidates 572、
  purged candidates 277が一致
- 60秒未満の新規／書込み中Parquetをsnapshotから除外
- RAWはPyArrowでfile単位に読み、読めないfileと除外行を明示集計

### 入力監査

- Flow observations: 2,275
- RAW trade rows included: 777,683
- RAW期間: 2026-07-23 18:23:42.595 UTC ～ 2026-07-25 06:50:28.248 UTC
- 観測日数: 1.5186日
- RAW files rejected: 0
- raw root内のnon-trade schema files ignored: 995
- trade ID重複: 0
- 非正値価格: 0
- cutoff後のため除外: 7,078 rows

### Candidate件数

60秒観測:

- `ATTACK_V1`: raw 318 / purge後109
- `PERSIST_PRESSURE_V1`: raw 62 / purge後46
- `RESOLUTION_CONFIRMED_V1`: raw 35 / purge後27
- 主候補の有効Outcome: 300秒18件 / 600秒18件

300秒観測:

- `ATTACK_V1`: raw 145 / purge後84
- `PERSIST_PRESSURE_V1`: raw 7 / purge後6
- `RESOLUTION_CONFIRMED_V1`: raw 5 / purge後5
- 主候補の有効Outcome: 300秒2件 / 600秒2件

### 最重要結果

60秒観測の`RESOLUTION_CONFIRMED_V1`、30 USD stress:

| outcome | OK | gross中央値 | cost後中央値 | positive net | favorable hurdle first | adverse hurdle first |
|---:|---:|---:|---:|---:|---:|---:|
| 300秒 | 18 | -0.990bps | -5.668bps | 1/18 | 4/18 | 5/18 |
| 600秒 | 18 | -0.749bps | -5.397bps | 0/18 | 5/18 | 8/18 |

事前固定したprice invalidationで撤退した場合も、30 USD stress後中央値は
300秒`-6.623bps`、600秒`-6.834bps`、positive netはいずれも0/18だった。

同一Episodeのpaired比較では、解放確認entryは早期entryよりgrossで遅かった。

- 300秒: Attack比中央値 -3.170bps、Persist比 -2.149bps
- 600秒: Attack比中央値 -2.775bps、Persist比 -1.682bps

ただし早期entry自体も30 USD stress後中央値がすべて負である。

- 60秒`ATTACK_V1`: 300秒 -4.417bps / 600秒 -4.574bps
- 60秒`PERSIST_PRESSURE_V1`: 300秒 -4.497bps / 600秒 -5.418bps

300秒観測のPersistはgross MFEが相対的に大きいが、OK 3件しかなく、
30 USD stress後中央値は300秒 -3.072bps、600秒 -1.949bpsである。
主候補はOK 2件だけで、いずれもstress後positive net 0件である。

### Entry Spec v1判定

**`NO_GO_FOR_HFM_ENTRY_V1`**

意味:

- 単発`EFFECTIVE`を発注トリガーへ戻さない
- 5分／10分へ保有時間を延ばすだけではHFM costを越える証拠がない
- 解放確認まで待つと、この標本では残存値幅がさらに小さくなった
- 解放前に早く入っても、30 USD stressを越えるnet結果は残っていない
- price invalidation撤退も、この標本ではEntry Spec v1を救っていない
- MT5 bridge／LIVE発注へ進まない

これは1.5186日の探索標本に対する**発注NO-GO**である。
30日／purge後200 Episode／untouched testを満たさないため、
注文フロー原理全体または将来の別仕様を統計的に棄却したとは扱わない。

### 成果物

- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md`
- `Delta_Engine_Pro4web/data_05M/research/episode_entry_v1_20260725.json`

### 限定blocker

- HFM同一時計quoteは0バイト。Gate 3／4は未評価のまま
- blockerを推測offset、旧日付quote、Binance価格補間で回避しない

### 次の再開位置

1. 対象試験と全体回帰を完了する
2. handoffへEntry Spec v1とNO-GO判定を追記する
3. Entry Spec v1を結果に合わせて変更せず、同じ固定仕様でデータを継続蓄積する
4. 別Entry Specを検討する場合はv2として事前固定し、今回データは探索／学習扱いにする

---

## 2026-07-25 16:18 JST: 最終checkpoint

### 完了済み

- Entry Spec v1を結果確認前に文章固定
- 三入口の純粋candidate extractorとpath evaluator実装
- 1M観測と5M／10M outcomeの分離
- 20 USD／30 USD proxy cost、hurdle先着、MFE／MAE、price invalidation撤退評価
- 600秒重複purge、固定UTC session、固定cutoff再現境界
- 固定cutoffを2回実行し、865 Episode／572 raw candidates／277 purged candidates一致
- `NO_GO_FOR_HFM_ENTRY_V1`判定を評価書、handoff、PROJECT_MEMORYへ反映
- Entry Spec対象試験 **27 passed**
- 全体回帰 **451 passed**

### 最終変更file

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_HANDOFF_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md`
- `Delta_Engine_Pro4web/src/orderflow/orderflow_episode.py`
- `Delta_Engine_Pro4web/src/orderflow/episode_entry.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_orderflow_episode.py`
- `Delta_Engine_Pro4web/tests/orderflow/test_episode_entry.py`
- `Delta_Engine_Pro4web/tests/tools/test_evaluate_episode_entries.py`
- `Delta_Engine_Pro4web/tools/evaluate_episode_entries.py`
- `Delta_Engine_Pro4web/data_05M/research/episode_entry_v1_20260725.json`

### 検証結果

- `python -m pytest ...Entry Spec対象... -q`: **27 passed**
- sandbox内full suite: pytest temp ACLによりsetup error。機能failureではない
- sandbox外専用basetempで同一full suite: **451 passed in 16.13s**
- RAW file rejected 0、trade ID重複0、非正値価格0
- HFM quote bytes 0
- LIVE／MT5 order 0

### blockerの限定範囲

- HFM同一時計Bid／Askが0バイトのためGate 3／4だけ未評価
- 30日／purge後200 Episode／untouched test未達のため統計的最終判定は未完了
- 現在のEntry Spec v1をLIVEへ出せないことはblockerではなく、検証結果に基づくNO-GO

### 次の再開位置

- まず更新済みhandoffと本checkpointを読む
- MT5発注作業を再開しない
- Entry Spec v1を変更せずデータを蓄積する
- HFM同一時計quote保存を0バイトから正常な連続記録へする
- v2を考える場合は今回結果を学習期間として隔離し、条件を先に新文書へ固定する
