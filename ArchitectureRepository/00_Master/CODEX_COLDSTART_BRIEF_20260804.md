# Codex 復帰ブリーフ(cold start用)
## 記憶リセット後、最初に読む1枚

**作成日:** 2026-08-04
**宛先:** 記憶を持たない新規Codexセッション
**発行:** Claude(統括)経由・ユーザー承認のもと

---

## 0. あなたの状況

あなた(Codex)はセッションが新しくなり、過去のやり取りを覚えていない。
だが問題ない。**必要な情報はすべてリポジトリ内のファイルとSHA-256で残っている。**
あなたは「思い出す」必要はなく、「ファイルを読んで現在地を確認する」だけでよい。

リポジトリ: `C:\Users\user\Desktop\DeltaEngine05M`
ドキュメント集約先: `ArchitectureRepository\00_Master\`

役割分担(不変):
- ユーザー = 方針決定・最終承認・実装GO。
- Claude(web) = 検証・指示書作成・統括。あなたの成果を実物SHAで独立検証する。
- Codex(あなた) = 実装担当。自己申告では承認されない。実物提出とSHA照合を必ず経る。

---

## 1. 今どこにいるか(2系統)

### 系統A: Phemex統合 — Phase 0実装GO待ち

- 仕様書 `PHEMEX_INTEGRATION_DETAILED_SPEC_20260802.md` は **v1.3-draft確定**。
  - 正しい版のSHA-256: `bd965d88d6c649df51f4e34ea1e1968808b91c830a5b4d52d8bbb37939a9a7ba`
- Phase 0指示書 `PHEMEX_PHASE0_BOUNDARY_LOCK_PREFLIGHT_INSTRUCTION_V1_20260803.md` 承認済み。
- 次: Phase 0実装(production変更ゼロ、checkpoint一本、GO待ち)。ユーザーGO後。
- この系統は現在停止中。系統Bが優先。

### 系統B: Realtime UI Freshness恒久対処 — Stage 2B-1 実装直前(主戦線)

不具合: UIが `MARKET DATA STALE ... TICK_TIMEOUT` / `HEARTBEAT_TIMEOUT` を誤発報。
原因は「約定や配信滞留を心拍と誤認」。多段で根本修正中。

**完了済み(触るな・戻すな):**
- Stage 2A = client単位 single-writer + priority queue。**実装完了**。
  これで共有broadcast lock待ち(超過の86%)を除去済み。
- Stage 2B Stage 1 = starvation主因の特定調査。**完了・承認済み**。
  主因は `LivePipeline.run_async`(pipelineのbacklog連続処理 + 稀な単一event重処理)。

**今から着手:**
- Stage 2B-1 = **backlog公平性chunk化**。指示書は発行済み:
  `RTUIF_STAGE2B1_BACKLOG_CHUNKING_INSTRUCTION_V1_20260804.md`
  - SHA-256: `7fe490ba5188fc2608f311d0cc4a0382f7bfdfbc2efd6b551c2de0ab482422a2`

---

## 2. 現在の正規runtime基準(この値が真)

正規Stage 2A imageへ復元済み。次のSHA-256が現時点の正しい実装後の値。
着手前に必ず実物と照合し、一致を確認してから作業する。

```text
webapp/push_broker.py : 953180e969679111fb502f0405cb4d2a691caf707d5b7594c2476a6ec8548a02
webapp/main.py        : adf09b07612ef0817a20779706990f946b50cb17c7879657918e40dd3372d20b
```

protected(絶対変更禁止・開始終了hash一致で証明):

```text
orderbook_heatmap.js : 2da8849d8e77ce82066f02e95c996dde75a952f2a900fc02018e4ea74467388b
time_sales.js        : f59fec3f3478cc5a9b977c74978c3d8eb7c66e27a479a0b40fcf6d5f18f8d4c2
footprint_canvas.js  : 987c5da72a7375495eb44bd9910a1b79b076226b2f0206cc8e3d3de2f08c01be
index.html           : 3a025cd2ef7425e922a962fa80a438b0d31f5e77b9a16732aacfc4f3577c513c
market_freshness.js  : 65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48
```

正規Stage 2A image ID: `sha256:508bb78281aeb797f5e69d90e47a3bcb6c45e5f93e43ebd6273897f87ef6acb6`
劣化時の親image(計装overlayの親): `sha256:9c4674c5b56638ae7f8ca629091558dd654e4b2c3572c46fbccf3a5525d88f10`

Stage 2B Stage 1の証拠とoverlayは `C:\tmp\rtuif_stage2b_stage1_20260803_234500` に保持。
削除は別承認まで禁止。

---

## 3. あなたが次にやること(Stage 2B-1 手順1)

指示書 `RTUIF_STAGE2B1_..._V1_20260804.md` の §2 Stage 1調査を実施する。実装はまだしない。

1. 指示書実物のSHA-256が `7fe490ba...` と一致することを確認。
2. §2.1: 正規Stage 2A版 `src/pipeline.py` の実物SHA-256をClaudeへ提出し照合。
   その正規版で、backlog drain loop(`while not source_drained: ... norm_q.get()
   ... normalizer.process(raw)` 相当)の位置をanchor確定。
   **注意: 計装overlay版pipeline.pyの行番号を実装に流用するな。別物。**
3. §2.2: chunk境界の挿入点(1 event処理完了直後・次のqueue取得前。book構築の
   途中には挟まない)。
4. §2.3: ADR-003(単一loop・単一book owner)で、yield中にbookが他所から
   変更されないことをsourceで確認。
5. §2.4: chunk化で失敗し得る既存testを棚卸しし、想定failとして事前列挙。
   緩和・削除で通す計画がないことを明記。
6. 上記を調査報告書にまとめて提出し **停止**。Claude検証とユーザーGO後に実装へ。

chunk境界の初期値(Claude提示、soakで確定): event数32件 または 連続50ms、
早い方でyield。値は設定可能にしmagic number化を避ける。

---

## 4. 絶対規律(記憶が無くてもこれだけは守る)

- production/test変更前に、対象実物のSHA-256を基準値と照合する。不一致なら停止・報告。
- `main.py` はCRLF/LF混在。編集行の改行を周辺に合わせる。一括normalize禁止。
  開始終了でCRLF/LF比率を記録。
- protectedと consumer(Heatmap/Tape/Flow/3段chart/Hook/Strategy)は触らない。
  開始終了SHA一致で不変を証明する。
- timeout値(1000/3000ms)は変えない。
- 計装が要るときはtemporary overlay image方式(親image ID pin、対象fileのみCOPY、
  env既定OFF、image ID照合で復元)。リポジトリsource直接編集で計装するな。
- 段階stop方式。各Stageは調査→停止→承認→実装→検証→提出。勝手に次段へ進まない。
- git add/commit/push/branchは指示があるまでしない。
- 指示書の中に境界矛盾(許可範囲と要求が食い違う等)を見つけたら、隠さず報告して停止する。
  過去2回それで正しく止めた。それが正しい。

---

## 5. 迷ったら

- 全体像は `HANDOVER_20260803.md`(Stage 2A時点まで)+ 本ブリーフ(Stage 2B分)。
- 各Stageの詳細は対応する指示書ファイル(§1にID記載)。
- 現在地が分からなくなったら、リポジトリ内の最新の完了報告書・checkpointの
  日付とSHAを見れば、どこまで進んだかが確定する。
- 判断に迷う技術論点は、勝手に決めず調査結果を添えてClaude/ユーザーへ返す。
```
