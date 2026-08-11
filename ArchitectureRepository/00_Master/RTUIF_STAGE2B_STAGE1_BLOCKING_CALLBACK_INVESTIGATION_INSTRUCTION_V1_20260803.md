# Realtime UI Freshness 恒久対処 第二段
## Stage 2B — Stage 1調査:event-loopブロッキングcallback特定 指示書 V1

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2B-STAGE1-INST-004
**版:** 1.0
**作成日:** 2026-08-03
**作成者:** Claude(統括)
**実施者:** Codex
**決定:** Stage 2A内部timing再測定を承認済み。残余遅延はevent-loop wake starvation主体
(健全区間wake最大27,886.800069ms、lock wait実消失、CPU飽和、cgroup throttleなし)。
本Stage 1でstarvationの発生源(loopを同期占有するcallback)を実測特定する。実装しない。

---

## 0. 目的と範囲

### 0.1 目的

single-writer + priority queue化(Stage 2A)後も、健全区間でheartbeatが数十秒遅延する。
その原因は共有lockでもqueueでもなく、event-loopのwake latenessである(再測定で確定)。
本Stage 1は、event-loopを数十秒にわたり同期占有しているcallback / coroutineを、
production source上で実測特定する。特定結果はStage 2B是正方式(chunk化 / executor退避 /
その他)の設計根拠になる。

### 0.2 確定済み前提(Claude独立検証済み・本調査の出発点)

- `shared_broadcast_lock_present` は全157トレースでFalse。lock wait最大は健全区間0.0176ms。
  → 共有lockは構造上除去済み。lockは原因でない。
- wake_lateness健全区間最大27,886.800069ms(seq155、同時刻lock_wait 0.0019ms)。
  全区間最大は約53,354ms(seq156)。wake_lateness>=3000msは29件。→ 残余の主因。
- adjusted CPU: mean 98.4 / p95 115.6 / max 131.7(cgroup生usage_usecからClaude独立再計算)。
  → CPU飽和。
- cgroup `throttled_usec=0` / `nr_throttled=0`。→ コンテナquota throttleではない。
  starvationはプロセス内(単一event-loopが同期処理でブロック)の可能性が高い。
- E4001/E4003 = 0でstarvation再現。→ storage障害とstarvationは独立。

### 0.3 本Stageでやらないこと(厳守)

- production source(push_broker.py / main.py / pipeline / analysis / storage / heatmap /
  footprint / tape / flow / hook / strategy)を変更しない。観測のみ。
- 是正実装(chunk化・executor退避・throttle・優先制御)を一切行わない。設計はStage 2で。
- ADR-003(asyncio単一ループ・スレッドなし)への変更判断を本Stageで下さない。
  本Stageは「どの処理がloopを同期占有するか」を事実として出すに留める。
- timeout値・protected・consumerに触れない。

---

## 1. 使用するimageと復元基準

### 1.1 対象image(正規Stage 2A image・親/復元先)

```text
image ID: sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
```

現行runtimeは劣化(sequence gap / reconnect でRED)している。調査soakは
maintenance windowでのclean recreate後に開始する。劣化runtimeで測らない。

### 1.2 計装方式(可逆overlay限定)

Stage 1A / 再測定と同一の可逆overlay方式に限定する。repository source直接編集を禁止する。

- 親image `508bb782...` をpinし、計装点のみをCOPYするoverlay imageを作る。
- 計装はenv既定OFF。本調査でのみenv ONで起動する。
- overlay layerの変更は計装点fileに限定し、変更file一覧を開始終了で提示する。
- image ID照合で正規imageへ復元し、無改変を証明する。

### 1.3 復元後に一致を証明するSHA(無改変証明)

測定完了後、正規Stage 2A image由来のclean containerへ戻し、以下7件の一致を証明する。

```text
push_broker.py      : 953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
main.py             : adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
orderbook_heatmap.js: 2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
time_sales.js       : f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
footprint_canvas.js : 987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
index.html          : 3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
market_freshness.js : 65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

---

## 2. 調査手順(段階stop)

### 2.1 展開前checkpoint

- 現行runtime状態を記録(container ID / health / restart / OOM / sequence gap / reconnect)。
- 親image `508bb782...` の実在・ID一致を確認。
- maintenance window・clean recreate前提を確認。

stopして状態を報告。

### 2.2 asyncio slow-callback一次観測(最小計装)

まず最小の計装で、loopを長時間占有するcallbackの存在と桁を掴む。

- event-loopを`loop.set_debug(True)`相当にし、`loop.slow_callback_duration`を
  小さめ(例: 0.1秒)に設定して、閾値超のcallback実行を警告として採る。
  これは既存ハンドラの実行時間を、source本体を書き換えずに炙り出せる。
- 併せて、各loop iterationのwall間隔(select/poll復帰間隔)を採り、
  「1回のcallbackがどれだけloopを止めたか」を秒単位で記録する。
- storage flush(parquet直列化)がloop上の同期処理としてブロックに寄与するかを、
  この一次観測の警告対象に含める(storage障害とは別問題として、直列化のCPU同期性を見る)。

一次観測で、ブロック源の候補(関数 / coroutine / モジュール)と最大占有時間を列挙する。

### 2.3 候補callbackの区間計時(可逆overlay)

一次観測で挙がった候補について、関数境界に可逆overlayで計時を入れ、
1呼び出しあたりの所要時間分布(n / mean / p95 / max)を採る。候補例(実物で確認して確定):

- heatmap集計 / レンダリング前処理。
- footprint計算。
- tape / DOM更新の重い経路。
- pipeline処理callback(analysis callback群)。
- storage flush / parquet直列化。

各候補について、CPU飽和時(mean 98%超の区間)における占有時間と、
直後のheartbeat wake_lateness spikeとの時間相関を採る。

### 2.4 wake spikeとの相関確定

wake_lateness>=3000msが発生した各heartbeat(全区間で29件)について、その直前の
loop iterationでどのcallbackがCPU時間を最も消費していたかを対応付ける。
「wake spike直前に一貫して同一callbackが長時間占有している」ことを示せれば、
そのcallbackがstarvationの主因と特定できる。

### 2.5 復元

- clean containerを正規image `508bb782...` へ戻す。
- §1.3の7件SHA一致、health、計装痕跡なしを証明する。
- overlay image / context / logはClaude検証完了まで削除しない。

---

## 3. 集計と提出(Codex・Claudeが独立検証)

### 3.1 必須アウトプット

1. slow-callback一次観測の結果(閾値超callback一覧、最大loop占有時間)。
2. 候補callback区間計時の分布表(候補ごとに n / mean / p95 / max)。
3. wake spike 29件と直前callback占有の相関表(spike毎に最占有callbackを対応)。
4. starvation主因callbackの特定(単一か複数か、CPU飽和との関係)。
5. storage flush(parquet直列化)がloop同期ブロックに寄与するか否かの事実判定。

### 3.2 Stage 2Bへの設計判断材料(事実のみ・判断はしない)

特定したブロッキングcallbackについて、次の事実を添える。Stage 2の設計はこれに基づく。

- 当該処理が分割可能(chunk化して複数loop tickに分散可能)か、単一の不可分計算か。
- 当該処理がCPU-boundか、I/O待ち(同期I/O)か。
- 呼び出し頻度と1回あたり占有時間。
- ADR-003(単一ループ・スレッドなし)を保ったまま是正できる見込みがあるか、
  executor退避等ADR-003の再検討が要る見込みか。※判断はStage 2でユーザーが下す。

---

## 4. 遵守事項(逸脱時は停止報告)

- production source・protected・consumer・storage実装を変更しない。観測のみ。
- 計装はoverlay方式のみ。repository source直接編集を禁止する。
- 是正実装(chunk化・executor・throttle等)を行わない。設計・実装はStage 2の別指示で。
- 測定後は必ず正規image `508bb782...` へ復元し、§1.3の7件一致を証明する。
- timeout・protected・Heatmap・Tape・Flow・3段・Hook・Strategyに触れない。
- git add / commit / push はしない。
- 劣化runtimeで測らない。clean recreate後に開始する。

---

## 5. 段階stop

次で停止し報告すること。

- image ID不一致、または親imageが実在しないとき。
- 復元後7件SHAが§1.3と一致しないとき。
- 計装痕跡が正規imageに残るとき。
- 是正実装が必要と判明したとき(→ Stage 2設計としてユーザーへ諮る。本Stageでは実装しない)。
- production source変更を要する観測しか設計できないとき(計装方式を再設計して報告)。

---

## 6. 完了条件(DoD)

1. 展開前checkpoint(runtime状態・image ID一致)。
2. slow-callback一次観測ログ + loop iteration間隔 log(生)。
3. 候補callback区間計時の生ログと分布表。
4. wake spike 29件との相関表。
5. starvation主因callbackの特定と、§3.2の設計判断材料。
6. 復元証明:正規image復元後の§1.3 7件SHA一致・health・計装痕跡なし。
7. 単一のStage 2B Stage 1調査報告書へ集約。証拠保持。

Claudeが生ログからloop占有・相関を独立再計算する。自己申告・集計結果だけを承認根拠に
しない。計時点・区間境界・SHAを実物から照合する。

Stage 2B是正方式(chunk化 / executor退避 / その他)の設計着手は、本調査の主因特定完了と、
ユーザーの明示GOを得てからとする。決定はユーザーが下し、Claudeが文書化する。
