# RTUIF Stage 2A — 内部timing再測定(§4.1)ディスパッチ

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2A-REMEASURE-003
**版:** 1.0
**作成日:** 2026-08-03
**作成者:** Claude(統括)
**宛先:** Codex(実施者)
**決定:** Stage 2A報告書を検証済みNO-GOとして承認済み。Stage 2Bの標的を確定する前に、
正本§4.1で要求され未実施のまま停止した内部timing再測定を、準備済みoverlayで実施する。

---

## 0. 位置づけと承認済み前提

### 0.1 Claude独立検証で確定済みの事実(本ディスパッチの前提)

Claudeが実物一式を独立照合した結果、以下を確定した。本ディスパッチはこの上に立つ。

- source 2件・protected 3件・consumer 2件・soak証拠4件の実SHA-256が報告書主張値と全一致。
- 生observer.jsonlからの再計算がanalysis.jsonと完全一致
  (server最大12,627.091ms seq255→256 / browser最大12,951.594ms / 超過9件 / gap 0)。
- 超過9件のうち8件はpipeline健全区間(seq<263、`pipeline_alive=true`)で発生。
  最大12,627msも健全区間内。storage障害排除後も健全区間max 12,627ms・超過8件でgate不達。
- pipelineはseq263(2026-08-03T12:45:13.928Z)で`pipeline_alive=false`かつ
  `upstream_fresh=false`へ転落し、seq618まで356件連続で異常。
- 超過は開始約3分無傷の後、seq251→263の約60秒でカスケード的に悪化しpipeline転落へ至る。

### 0.2 本再測定の目的

lock wait除去後も健全区間で12.6秒級のheartbeat飢餓が残る。その残余内訳を実測し、
次の2点を確定する。

1. Stage 1Aで支配的だった共有lock wait寄与(86.083%)が、Stage 2A実装で実測上
   消失したか。消失していればStage 2Aの構造是正は所期どおり効いている。
2. 健全区間の残余がwake lateness(event-loop starvation)主体か。主体であれば
   Stage 2Bの標的をevent-loop / CPU飽和に正しく絞れる。
3. 併せて、heartbeat飢餓カスケードとstorage障害(E4001/E4003)が単一の資源飽和
   イベントの症状か、独立事象かを切り分ける観測データを採る。

### 0.3 本ディスパッチが拡張しないこと

- production source(push_broker.py / main.py / protected / consumer)を変更しない。
- storage実装(E4001/E4003の原因箇所)を修正・rollback・無効化しない。観測のみ。
- timeout値・Heatmap・Tape・Flow・3段チャート・Hook・Strategyに触れない。
- 計装はStage 1Aと同じ可逆overlay方式に限定する。repository source直接編集を禁止する。

---

## 1. 使用するimageと復元基準

### 1.1 正規Stage 2A image(親・復元先)

```text
image ID: sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6
```

### 1.2 準備済み計装overlay(展開対象)

Stage 2A報告書§11.2で作成・isolated probe済み。新規計装コードの追加は不要。

```text
overlay image ID: sha256:dd3c5ec726817c117977fb4dbac68eb7d5ef0a3ecd7e044d3b505b4e427957f5
```

- overlay layerの変更は`/app/webapp/main.py`と`/app/webapp/push_broker.py`の計装点だけ。
- 計装はenv既定OFF。本測定でのみenv ONで起動する。
- 展開前に上記2 image IDが実在し一致することを確認する。不一致なら停止・報告。

### 1.3 復元後に一致を証明するSHA(無改変証明)

測定完了後、正規Stage 2A image由来のclean containerへ戻し、以下の一致を証明する。

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

## 2. 測定手順(段階stop)

### 2.1 展開前checkpoint

- 現行runtimeを記録(container ID / health / restart / OOM)。
- 親image `508bb782...` と overlay `dd3c5ec...` の実在・ID一致を確認。
- maintenance window・clean recreate前提を確認(劣化runtimeで測らない)。

stopして状態を報告。異常があればここで停止。

### 2.2 計装ON soak(健全区間確保を主目的)

- overlay `dd3c5ec...` をclean recreateで展開し、計装envをONにする。
- 起動後readinessを確認(health GREEN / SUBSCRIBED / BOOK SYNCED / restart 0 / OOM false)。
- 600秒soakを実施する。storage障害で途中転落しても測定は継続し、記録は破棄しない。
- Stage 1Aと同一の計装点で、heartbeat 1件ごとに次の内訳を採取する。
  - 共有lock wait(該当構造が残る場合の待ち時間)。
  - gather / scheduling待ち。
  - wake lateness(loop起床遅延)。
  - actual send。
- 併せて各heartbeatの `pipeline_alive` / `upstream_fresh` / sequence / published_time /
  receive_monotonic_ns を採る(健全区間分離のため)。
- CPU / memory / pids を1秒間隔でcgroupから採る。
- storage worker(E4001/E4003)の初出時刻・以後の反復時刻をcontainer logから採る。

### 2.3 復元

- clean containerを正規Stage 2A image `508bb782...` へ戻す。
- §1.3の7件SHA一致、health GREEN、計装痕跡なしを証明する。
- overlay image / context / logはClaude検証完了まで削除しない。

---

## 3. 集計と判定(Codex提出・Claude独立検証)

### 3.1 健全区間分離集計(必須)

- `pipeline_alive=true` かつ `upstream_fresh=true` のheartbeatだけを健全区間とする。
- 健全区間のheartbeat間隔について、内訳(lock wait / gather / wake / send)の
  寄与割合と各最大値を出す。
- 転落区間(`pipeline_alive=false`)は分離して別集計とし、健全区間へ混ぜない。

### 3.2 確定したい問い(この2つに実測で答える)

- Q1: 健全区間でlock wait寄与はStage 1Aの86.083%からどこまで下がったか。
  実質消失(数%以下)なら「Stage 2Aの構造是正は所期どおり」と結論できる。
- Q2: 健全区間の残余最大遅延はwake lateness主体か。主体なら
  「Stage 2Bはevent-loop starvation / CPU飽和を標的とする」を実測で確定できる。

### 3.3 storage因果の切り分け(観測のみ)

- storage flush失敗の初出時刻と、heartbeat飢餓カスケード開始(健全区間の最初の
  内訳悪化)・CPU飽和サンプルの前後関係を時系列で並べる。
- どちらが先行するか、共起するかを事実として記録する。原因修正はしない。

### 3.4 判定

- Q1消失 かつ Q2 wake主体 → Stage 2Bをevent-loop starvation対処として設計着手可。
- Q1でlock waitが残存 → Stage 2A実装に見落としがある。Stage 2Bへ進まず実装を再点検。
- storageが飢餓に先行する明確な証拠 → storage是正を飢餓対処の前提工程へ繰上げ検討。

---

## 4. 遵守事項(逸脱禁止・逸脱時は停止報告)

- production source・protected・consumer・storage実装を変更しない。観測のみ。
- 計装はoverlay方式のみ。repository source直接編集を禁止する。
- 測定後は必ず正規image `508bb782...` へ復元し、§1.3の7件SHA一致を証明する。
- timeout・Heatmap・Tape・Flow・3段・Hook・Strategyに触れない。
- git add / commit / push はしない。
- 劣化runtimeで測らない。soakはclean recreate後に開始する。

---

## 5. 段階stop

次で停止し報告すること。

- image ID不一致、または親image/overlayが実在しないとき。
- 復元後の7件SHAが§1.3と一致しないとき。
- 計装痕跡が正規imageに残るとき。
- storage実装・production sourceの変更が必要と判明したとき(→設計判断をユーザーへ)。

---

## 6. 完了条件(DoD)

1. 展開前checkpoint(runtime状態・image ID一致)。
2. 計装ON 600秒soakの生ログ(heartbeat内訳・pipeline_alive・cgroup・storage log)。
3. 健全区間分離集計(§3.1)とQ1/Q2への実測回答(§3.2)。
4. storage因果切り分けの時系列(§3.3)。
5. 復元証明:正規image復元後の§1.3 7件SHA一致・health GREEN・計装痕跡なし。
6. 単一の再測定報告書へ集約。証拠保持。

Claudeが生ログから内訳と健全区間分離を独立再計算する。自己申告・集計結果だけを
承認根拠にしない。calibration値・区間境界・SHAを実物から照合する。

Stage 2Bの設計着手は、本再測定でQ1/Q2が確定し、ユーザーの明示GOを得てからとする。
決定はユーザーが下し、Claudeが文書化する。
