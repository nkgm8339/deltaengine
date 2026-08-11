# Realtime UI Freshness 恒久対処 第二段
## Stage 2B-1 — backlog公平性chunk化 設計・実装指示書 V1

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2B1-INST-001
**版:** 1.0
**作成日:** 2026-08-04
**作成者:** Claude(統括)
**実施者:** Codex
**決定:** Stage 2B Stage 1調査承認済み。starvation主因は`LivePipeline.run_async`。
本Stageはbacklog公平性chunk化のみを実装する。単一event重処理はStage 2B-2に分離する。

---

## 0. 根拠(Stage 2B Stage 1報告 実測)

報告書 `126248823568255d62c16eb667abffde825a4749a1ecaa5f38d3ce5827b3b07a` を
Claudeが独立検証(manifest 43件全一致)。3000ms超過10件をClaudeが型分類した結果:

| 型 | 件数 | 特徴 |
|---|---:|---|
| backlog連続処理支配 | 6件 | burst 150〜354件、max単一raw <500ms |
| 前バーストの尾 | 1件 | burst開始前の待ち2807ms(seq13960) |
| loop内 raw以外処理 | 1件 | burst計時3380ms中 raw処理88msのみ(seq10868) |
| 単一event重処理支配 | 2件 | 単一trade 3407ms / 単一depth 3234ms(seq9703, seq14613) |

分布の裏付け(candidate_analysis_v2.json 実測):

- `pipeline.raw_event.depth`: p95 80.7ms / max 3234.5ms(n=5894)
- `pipeline.raw_event.trade`: p95 9.2ms / max 3407.3ms(n=24859)
- `burst_events`: p95 19 / max 418、`burst_max_qsize`: p95 18 / max 417
- queue非空率 82.535%

結論: 大多数のeventは高速(p95が80ms/9ms)、稀に単一eventが3秒級へ跳ねる。
3000ms超の支配要因はbacklog連続処理(8件が該当)。chunk化で8件に効く。
単一event重処理2件はchunk化(event間yield)では割れない。別Stageへ分離する。

---

## 1. 本Stageの範囲

### 1.1 やること

`LivePipeline.run_async`のready backlog drain loopに公平性chunk化を入れる。
一定のchunk境界(event数 または wall-time budget)ごとにloopへ制御を返し
(`await asyncio.sleep(0)`等)、event-loopの他task(heartbeat配信、canary、
health)を進行させる。

### 1.2 やらないこと

- 単一depth/trade event内部の分割・executor退避(Stage 2B-2)。
- storage処理の変更(storage.tick()はmax3.070msで主因でない、報告§5)。
- timeout値(1000/3000ms)の変更。
- PushBroker priority queue(Stage 2A完了済み)の変更。
- book構築ロジック・順序・ownershipの変更。ADR-003(単一loop・単一book owner)を維持。
- Heatmap/Tape/Flow/3段chart/Hook/Strategy/protectedの変更。

---

## 2. Stage 1調査(実装前・Codex実施・必須)

本指示書§0の計装overlay版pipeline.py(`4eec6645...`)は計装専用であり、
実装対象は正規Stage 2A版pipeline.pyである。両者は別物。実装前に次を確定する。

### 2.1 正規版アンカー確定

正規Stage 2A imageに含まれるpipeline.py実物のSHA-256をClaudeへ提出し照合する。
その正規版で、backlog drain loopの実体(計装版で
`overlay_candidate/src/pipeline.py:1960-2130`付近に相当する
`while not source_drained: ... norm_q.get() ... normalizer.process(raw)`のloop)の
正確な位置と構造をanchorとして確定する。計装版の行番号を実装に流用しない。

### 2.2 chunk境界の挿入点

drain loopのどこにchunk境界を置くか設計する。1 event処理の完了直後、
次のqueue取得の前が候補。book構築の途中(1 eventの正規化・book適用の内部)へ
yieldを挟まないこと。event単位の境界でのみ制御を返す。

### 2.3 book整合の非破壊確認

chunk境界でloopを離れる間に、他coroutineがbook状態を破壊しないことを確認する。
ADR-003で単一book ownerのため、book書込は本loopのみのはず。それをsourceで確認し、
yield中にbookが他所から変更されない設計であることを示す。

### 2.4 起動時テスト波及調査

chunk化で失敗し得る既存testを棚卸しする。特に「backlogを一度に全processして
から次を待つ」ことを前提にするtest、処理順序・完了タイミングをassertするtestを
実物で確認し、想定failとして事前列挙する。緩和・削除で通す計画がないことを明記する。

---

## 3. chunk境界の初期値(Claude提示・soakで妥当性確認)

実測(burst_events p95=19、burst_duration p95=194ms)に基づく初期値を提示する。
Codexはこれを起点に実装し、Stage 2B-1 soakで妥当性を検証して確定する。

- **event数budget**: 32件処理ごとにyield(p95=19件を上回る値。通常burstは
  1回のyieldも要さず、大backlog時のみ分割)。
- **wall-time budget**: 連続処理が50msに達したらyield(p95=194msより十分小さく、
  かつ per-event p95 80ms/9msに対し複数event分の余裕)。
- 両者のいずれか早い方でyieldする(event数と時間の二重budget)。

初期値の値自体は設定可能にし、magic number埋め込みを避ける。既定値を上記とし、
soak結果で過大/過小と判明したら調整する。値の根拠を設計文に記す。

---

## 4. 検証gate(Stage 2B-1完了後・全PASSでruntime反映可)

### 4.1 効果(直接測定・必須)

Stage 2B計装overlay方式(temporary image、可逆、親image ID照合復元)を再適用し、
600秒soakで次を測る。

- **canary lateness最大**: backlog型の超過が解消し、3000ms超件数が減ること。
- **browser受信間隔最大・server生成間隔最大**: 3000ms未満なら本Stageで完了。
  3000ms以上が残る場合、残存超過が単一event重処理(seq9703/14613型)由来か
  否かを相関表で判定する。単一event型のみが残るなら**Stage 2B-2へ**進む。
  backlog型が残るならchunk境界値を見直す。
- burst最大占有時間が短縮したこと(実装前 max 5413ms 対比)。

### 4.2 非破壊(必須)

- book gap 0、全SYNCED維持(chunk化がbook整合を壊していないこと)。
- heartbeat pipeline_alive/upstream_fresh維持。
- Tape drop/pending/send failure 0。
- 通常message順序・Flow/BAR配信継続。

### 4.3 protected・境界

- protected 3件(orderbook_heatmap.js `2da8849d...`、time_sales.js `f59fec3f...`、
  footprint_canvas.js `987c5da7...`)開始終了SHA一致。
- index.html `3a025cd2...`、market_freshness.js `65c94cf5...` 不変。
- Heatmap adaptive stale/gap/sequence、Tape順序の既存test差分ゼロ。

### 4.4 test・全体

- 専用test(chunk境界でyieldしbook整合を保つ)。
- §2.4で把握した波及testの正当な更新(緩和・削除でなく新挙動追随)。
- WebApp全体・repository全体test。既知baseline以外の新規failゼロ。
- pipeline.py編集後の実SHA-256。改行コード比率(混在の場合)保持。

---

## 5. 変更境界(Stage 2B-1)

| 対象 | 許可 | 禁止 |
|---|---|---|
| `src/pipeline.py` | drain loopのchunk境界yield挿入、budget設定 | book構築/順序/ownership変更、単一event内部分割 |
| config(budget値) | chunk budget設定項目の追加 | 既存config意味変更、timeout変更 |
| 波及test | §2.4事前列挙分の新挙動追随 | 緩和・削除・rename、契約test値の弱化 |
| storage | なし | storage.tick/BackgroundStorageWriter変更 |
| PushBroker(Stage 2A成果) | なし | priority queue/writer変更 |
| protected/consumer/Heatmap/Tape/Flow/3段/Hook/Strategy | なし | いかなる変更も |

---

## 6. 実装手順(段階stop)

1. §2 Stage 1調査(正規版anchor確定、挿入点、book非破壊、test波及)を報告しstop。
   Claude/ユーザー確認後に実装へ。
2. drain loopへchunk境界(event数32/時間50msの二重budget、設定可能)を実装。
3. 専用test作成、波及test更新。
4. 全体test。protected hash検証。pipeline.py改行検証。
5. temporary overlayで計装soak(§4.1)。max 3000ms未満、または残存が単一event型のみ
   であることを確認。
6. 実装後source実物一式と証拠を提出。Claude独立検証。

各段でbook破壊、protected変更、timeout変更、単一event内部への介入が無いことを確認。
git add/commit/pushはしない。

---

## 7. 完了条件(DoD)

1. §2 Stage 1調査結果(正規版anchor、挿入点設計、book非破壊証明、test波及一覧)。
2. §1設計に沿ったchunk化実装。
3. §4検証gate: 効果(backlog型超過の解消)、非破壊(book gap0)、protected一致、test。
4. 600秒soakでの canary lateness / browser・server間隔 実測。
5. 3000ms未満達成、または残存超過が単一event重処理型のみである直接証拠
   (後者ならStage 2B-2の必要性が確定)。
6. 実装後pipeline.py実SHA-256、改行比率。
7. 親image完全復元と7件SHA一致。
8. 単一Stage 2B-1報告書へ集約。証拠保持。

Stage 2B-1報告はClaudeが独立検証する。自己申告・test PASS・runtime GREENだけを
承認根拠にしない。実物diff・source hash・soak実測ログ・計装点を独立照合する。

---

## 8. Stage 2B-1後の分岐

- soakでserver/browser max 3000ms未満 → **恒久対処完了候補**。最終release gate
  (Stage 2A/2B統合soak)へ。
- 3000ms超が残り、それが単一event重処理型のみ → **Stage 2B-2**(単一depth/trade
  event内部の分割またはexecutor退避)へ。Claudeが2B-2設計をCodexに問う。
- backlog型が残る → chunk境界値を見直し2B-1内で再soak。

実装開始(手順2以降)はユーザー明示GOによる。手順1(調査)はStage 2B Stage 1承認で
着手してよい。決定はユーザーが下し、Claudeが文書化する。
