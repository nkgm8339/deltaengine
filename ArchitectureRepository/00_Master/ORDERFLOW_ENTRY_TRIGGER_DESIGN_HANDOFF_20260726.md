# Order Flow ENTRY Trigger Design — 次セッション引継ぎ

作成時刻: 2026-07-26 01:25 JST
状態: **統合ENTRY未完成。設計から再開すること。**

---

## 0. 最上位命令 — クライアントであるユーザーの意向

このプロジェクトのクライアント、目的決定者、完成条件の決定者、最終採否の決定者は
ユーザーである。ユーザーの最新の明示意向を、過去文書、過去policy、エージェントの
都合、実装しやすさ、試験しやすさで上書きしてはならない。

次を絶対に行わない。

- ユーザーの趣旨を勝手に狭める
- 一部だけ実装して、全体を完成したように報告する
- ユーザーが求めた最終目的を、実装者に都合のよいproxy問題へ置き換える
- テスト件数、コード量、処理時間を、目的達成の証拠として扱う
- 過去の決定文書を理由に、ユーザーの最新明示指示を無効化する
- ユーザーが求めていない方向へ「改善」「安全」「研究」の名目で誘導する
- 不明点を勝手に補って、目的が変わる実装を進める

解釈に複数の可能性がある場合は、ユーザーの原文を引用し、何が未確定かを明示する。
目的や完成条件が変わる判断は、勝手に決めずユーザーへ確認する。確認待ちの間も、
承認範囲内の安全なコード監査、データ監査、文書化は継続する。

---

## 1. ユーザーが求めている本来のシステム

ユーザーが求めているのは、単一指標EAではない。

```text
注文フローを分析する
    ↓
相場で起きている現象を識別する
    ↓
その現象からentry根拠となるトリガーを定義する
    ↓
複数分析の支持・反対・無効条件を確認する
    ↓
最初の正しい瞬間だけENTRY GOを出す
    ↓
HFMへ自動発注する
    ↓
根拠、時刻、注文結果、ticket、約定価格を目視・監査できる
```

重要度は次のとおり。

1. 間違いのない分析
2. 間違いのないentryタイミング
3. そのGOを実発注へ接続すること
4. spread、SL/TP、決済最適化、安全制約は、その後に分離して扱う

分析項目を計算・表示していても、最終ENTRY根拠へ使用していなければ、
実取引システムとしては「分析していない」のと同じ、というのがユーザーの明示した基準である。

データ源と執行先:

- 主分析データ: Binance Futures実データ
- 実執行先: HFM MT5
- 分析・entry正確性はBinanceだけでなくHFM同一時刻価格でも確認する
- Binanceの分析価格をHFM注文価格として使わず、HFMの実Bid/Askで執行する

---

## 2. 今セッションで起きた重大な誤り

エージェントは、完成済みの分析全体ではなく、`Flow Price Response`単体の状態遷移だけを
HFM発注器へ接続した。

誤って接続した変換:

| Flow state | side |
|---|---|
| `BUY_EFFECTIVE` | BUY |
| `SELL_EFFECTIVE` | SELL |
| `BUY_TRAPPED` | SELL |
| `SELL_TRAPPED` | BUY |

これはFlow単体の機械的な変換であり、次を発注根拠に使用していなかった。

- CVD
- regular CVD divergence
- Footprint
- diagonal / stacked Imbalance
- Absorption
- Large Trade
- Sweep
- Exhaustion
- Unfinished Auction
- Tape
- Liquidation
- PRICE/CVD/Deltaの8パターン
- Open Interest context
- native 5m/10m Flow

その状態で「完成済み分析を発注へ接続した」と報告した。これは誤りであり、
**分析から自動発注まで完成という報告は撤回済み**。

この誤りにより、Flow単体のゼロスプレッド評価、発注配線、dashboard、回帰試験へ
何時間も使った。部品を再利用できることは、目的と順序を誤って時間を浪費した事実を
打ち消さない。

---

## 3. コード監査で確認した現在の事実

### 3.1 統合Signalは現在存在しない

`Delta_Engine_Pro4web/src/orderflow/signal.py`

- module docstringは`retired composite engine`
- `SignalEngine`はcompatibility shell
- `evaluate()`は入力に関係なく、固定で
  `signal="WAIT"`, `confidence=0`, `reasons=("NO_INPUT",)`を返す

したがって、設定fileにCVD、Footprint、Imbalance、Flowのweightが存在しても、
現在のruntime entry判断には使われない。

### 3.2 AnalysisEngineも統合判断をしていない

`Delta_Engine_Pro4web/src/ai/analysis.py`

- `AnalysisEngine.evaluate()`は固定で
  `market_state="NEUTRAL"`, `confidence=0`, `summary="Independent indicators active"`
- BUY/SELL GOを生成しない

### 3.3 Pipelineは独立表示のため、意図的にscoreを外している

`Delta_Engine_Pro4web/src/pipeline.py`の`_evaluate_and_store()`:

- `s_cvd = None`
- `s_fp = None`
- `s_imb = None`
- `SignalEngine.evaluate()`へ上記Noneを渡す

これは2026-07-21の再誕時、説明不能な単一scoreへ各指標を混ぜることをやめ、
独立観測へ戻した設計による。独立化自体は正しい。ただし、その後に必要な
「説明可能な現象別ENTRYトリガー層」はまだ作られていない。

### 3.4 各分析器は実在し、runtimeで計算されている

| 分析 | 主な実装 | cadence | 現在の用途 | 統合ENTRY接続 |
|---|---|---:|---|---|
| CVD / Delta | `orderflow/cvd.py` | trade / bar | chart・保存 | なし |
| Footprint | `orderflow/footprint.py` | trade / bar close | chart・保存 | なし |
| Stacked Imbalance | `orderflow/imbalance.py` | bar close | wall表示・event | なし |
| Absorption | `orderflow/absorption.py` | tick | event・表示 | なし |
| CVD divergence | `orderflow/divergence.py` | confirmed bar | event・表示 | なし |
| Large Trade | `orderflow/flow_detector.py` | tick | Flow Event | なし |
| Sweep | `orderflow/flow_detector.py` | tick | Flow Event | なし |
| Tape | `orderflow/flow_detector.py` | tick | Flow Event | なし |
| Exhaustion | `orderflow/flow_detector.py` | bar close | Flow Event | なし |
| Unfinished Auction | `orderflow/flow_detector.py` | bar close | Flow Event | なし |
| Flow Price Response | `orderflow/flow_price_response.py` | rolling second | 6窓表示・Outcome | 誤って単体接続 |
| native 5m/10m CVD/FP | `orderflow/native_execution.py` | 5m/10m close | 保存・研究 | なし |
| native 5m/10m Flow | `orderflow/native_flow.py` | 5m/10m close | event・Outcome | なし |
| 8パターン + OI | `orderflow/combined_context*.py` | 5m/10m close | context・HFM Outcome | なし |
| Liquidation | `pipeline.py` / WebApp | event | 表示・集計 | なし |

### 3.5 分析の意味で重要な既存仕様

Absorption:

- `BUY_ABSORPTION`: sell aggressionが吸収されたbullish現象
- `SELL_ABSORPTION`: buy aggressionが吸収されたbearish現象

Divergence:

- bullish regular: price lower low、CVD higher low
- bearish regular: price higher high、CVD lower high
- confirmed candleと左右pivotを使うため、検出時刻とpivot時刻を区別する必要がある

Imbalance:

- diagonal buy/sell imbalance
- 連続価格levelが`stack_count`以上のときStacked Imbalance
- bar closeで成立するため、tick系トリガーとの時刻差を扱う必要がある

Flow Event:

- `large_trade`
- `sweep`
- `tape`
- `exhaustion`
- `unfinished_auction`

Flow Price Response:

- `EFFECTIVE`: aggression方向へ価格が反応
- `STALLED`: aggressionに対し価格が停滞
- `TRAPPED`: aggressionと反対へ価格が動く
- 状態は観測であり、それ単独を直接売買命令としてはいけない

8パターン + OI:

- PRICE/CVD/Deltaの8分類は既存UIルールを維持
- OIはBUILDING/UNWINDING/UNCHANGED/MISSINGのcontext
- module自身が明記する通り、score、probability、trade signalではない

---

## 4. これまでの試験が証明したこと／していないこと

### 証明したこと

- 各分析moduleの計算が個別仕様どおり動く
- Flow Price Responseが6窓で状態を生成・保存・配信する
- Flow単体状態のfixed horizon結果をBinance/HFMで計算できる
- HFM `#BTCUSDr` 0.01 lotのBUY/SELL requestが`order_check retcode=0`
- MT5へ注文を渡すexecution plumbingを実装できる
- 既存回帰472件が通る

### 証明していないこと

- オーダーフロー全体からENTRYトリガーを出せる
- divergenceなどを含む統合GOが正しい
- ENTRYタイミングがproductionで正しい
- どの現象を継続、反転、見送りと読むべきか
- 複数分析が矛盾した場合の判断
- 統合トリガーの勝率
- 統合トリガーからHFM実注文が出た

472件合格をENTRY完成の根拠にしてはならない。

---

## 5. Flow単体sidecarの状態

追加されたfile:

- `Delta_Engine_Pro4web/src/execution/__init__.py`
- `Delta_Engine_Pro4web/src/execution/flow_hfm_executor.py`
- `Delta_Engine_Pro4web/tools/run_flow_hfm_autotrader.py`
- `Delta_Engine_Pro4web/tests/execution/test_flow_hfm_executor.py`
- `Delta_Engine_Pro4web/docs/FLOW_TO_HFM_AUTOTRADER_RUNBOOK_20260726.md`

扱い:

- **ENTRYロジックとして採用禁止**
- execution plumbing、audit、dashboard部品は将来の統合GO接続時に再利用可能
- `FLOW_STATE_TO_SIDE`をproduction GOとして使わない
- runbookのLIVE手順を実行しない

停止確認:

- 2026-07-26 01:24 JST、check sidecar PID 21764を停止
- port 18081: stopped
- MT5 position: 0
- MT5 pending order: 0
- MT5 algorithmic trading: OFF
- LIVE注文: 0件

Dockerの分析WebAppとMT5 quote exporterは停止していない。

---

## 6. 次セッションの最初の成果物

コードを書く前に、次の文書を作り、ユーザーへ説明する。

仮称:

`ORDERFLOW_ENTRY_TRIGGER_DESIGN_REPORT_20260726.md`

目的:

「指標を何個一致させるか」ではなく、「相場で異なるどの現象をENTRY対象にするか」を
定義する。

トリガー数を先に5個、6個などと決めない。相場メカニズムが独立している数だけ定義する。
一つの現象を複数名に分けて水増しせず、異なる現象を一つのscoreへ潰さない。

### 各トリガーに必ず書く項目

1. Trigger ID / name
2. 狙う相場現象
3. BUY/SELLの意味
4. 主発火条件
5. confirmation条件
6. 反対根拠
7. hard reject / invalidation
8. armed時刻、confirmed時刻、GO時刻
9. 使用するpriceとentry時刻
10. expiry
11. duplicate防止
12. re-arm条件
13. 使用するtimeframe/window
14. 欠測時の扱い
15. その条件を選ぶ既存データ上の根拠
16. ゼロスプレッドでの正確性評価方法
17. Binance/HFM同時刻比較方法
18. dashboardへ表示する人間向け理由

### 各分析の役割を分類する

各moduleを必ず次のどれかへ置く。

- `PRIMARY_TRIGGER`: 現象発生を起こす
- `CONFIRMATION`: entry方向を支持する
- `VETO`: 反対なら発注しない
- `CONTEXT`: 意味を説明するが単独発注しない
- `DATA_QUALITY`: stale/欠測/時刻ずれを検出

全分析を無理に毎回一致させる必要はない。しかし、使わないmoduleを使ったように報告しては
ならない。各ENTRYには「使用したもの」「反対だったもの」「欠測だったもの」を全て残す。

---

## 7. 真剣に検討すべき現象候補

以下は採用済み仕様ではない。次セッションでデータと既存意味を突き合わせるための候補である。
数合わせで全部採用しない。

### A. Aggressive continuation / resolution

- same-side Sweep / Tape / Large Trade
- same-side Stacked Imbalance
- CVD/Delta aligned
- Flow ResponseがEFFECTIVEへ初回遷移
- 反対divergence、反対absorptionがあればreject候補

### B. Trapped aggression / absorption reversal

- 強いaggression
- STALLEDまたはTRAPPED
- aggressor反対側のAbsorption
- 反対方向へのprice response
- OI BUILDINGなら捕まった新規positionというcontext候補

### C. Confirmed CVD divergence reversal

- confirmed regular divergence
- divergenceだけで即entryしない
- Flowの停滞／trap、absorption、反対方向effectiveのいずれかでentry時刻を確認
- detected_timeとpivot_timeを混同しない

### D. Exhaustion / auction completion

- extremeのExhaustionまたはUnfinished Auction
- 反対方向Tape/Sweepまたはprice reclaimを待つ
- 単独eventはprimaryではなくarm条件の可能性

### E. Liquidation / position unwind reversal or continuation

- long/short liquidationのburst
- OI UNWINDING
- absorption/trapなら反転候補
- effective continuationなら投げ継続候補
- liquidation閾値と時刻同期の既存実装を先に監査

### F. Native 5m/10m resolution context

- native 5m/10m FlowとPRICE/CVD/Delta/OI context
- tick/30s entryの上位timeframe confirmationまたはveto
- bar close後にしか分からない情報を過去時点entryへ混ぜない

---

## 8. entry設計で避けるべき誤り

- indicatorの多数決だけでGOを出す
- weightを付けて説明不能な単一scoreへ戻す
- Flow state単体をGOにする
- divergence検出前のpivot時刻でentryしたことにする
- 5m/10m bar close情報をbar途中のentryへ先読み利用する
- OI future sampleをas-of時刻より前の判断へ使う
- 同じ現象の継続更新を何件ものentryとして数える
- 同時刻の複数windowを独立現象として水増しする
- 良かった条件だけを同じ期間の結果後に採用する
- spreadを入れて分析方向の正誤を判定する
- unit test合格を相場で正しい証拠にする

---

## 9. 次セッションの作業順

1. `PROJECT_MEMORY.md`と本handoffを全文読む
2. `signal.py`、`analysis.py`、`pipeline.py`の固定WAIT/NEUTRALを再確認
3. 各moduleのevent time、cadence、side意味を表にする
4. 保存済み実データで各eventの発生数、同時発生、順序、欠測を監査
5. 現象候補を重複のないtrigger familyへ整理
6. 詳細Trigger Design Reportをユーザーへ提示
7. ユーザー意向を確認する前に大量評価・発注実装へ進まない
8. 合意後、trigger state machineと根拠payloadを実装
9. zero-spreadで分析方向とentry時点を評価
10. Binance/HFMで方向一致を確認
11. 統合GOだけをexisting execution plumbingへ接続
12. dashboardで全根拠と反対根拠を目視確認
13. ユーザー承認後にのみLIVE発注

---

## 10. 最初に読むコード

- `Delta_Engine_Pro4web/src/orderflow/signal.py`
- `Delta_Engine_Pro4web/src/ai/analysis.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/orderflow/divergence.py`
- `Delta_Engine_Pro4web/src/orderflow/imbalance.py`
- `Delta_Engine_Pro4web/src/orderflow/absorption.py`
- `Delta_Engine_Pro4web/src/orderflow/flow_detector.py`
- `Delta_Engine_Pro4web/src/orderflow/flow_price_response.py`
- `Delta_Engine_Pro4web/src/orderflow/combined_context.py`
- `Delta_Engine_Pro4web/src/orderflow/combined_context_runtime.py`
- `Delta_Engine_Pro4web/src/orderflow/native_execution.py`
- `Delta_Engine_Pro4web/src/orderflow/native_flow.py`

---

## 11. 変更禁止と保全

- 完成済みFlow Price Responseを勝手に変更しない
- 完成済み3段チャートを勝手に変更しない
- ユーザーの未コミットUI変更を上書きしない
- 既存の独立指標を説明不能な旧composite scoreへ戻さない
- Flow単体sidecarをLIVE起動しない
- 誤った記録も削除せず、なぜ不採用かを残す
- 実注文を送らない

---

## 12. 再開位置

次セッションは実装から始めない。

最初の仕事は、保存済み実データと既存moduleの意味を使い、
**現象別ENTRYトリガーを何種類に分けるべきかを真剣に設計し、ユーザーへ詳細報告すること**。

「5つか6つ」という数はユーザーが例として言っただけであり、固定要件ではない。
数を先に決めず、相場現象とentry時刻を一意に説明できる単位から決める。
