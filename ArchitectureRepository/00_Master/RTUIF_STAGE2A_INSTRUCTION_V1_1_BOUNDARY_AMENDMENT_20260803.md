# Stage 2A 実装指示書 v1.1 追記指示書

**文書ID:** DE05M-RTUIF-HBPRI-STAGE2A-INST-001-AMEND
**版:** 1.0
**作成日:** 2026-08-03
**作成者:** Claude(統括)
**実施者:** Codex
**承認者:** ユーザー

---

## 1. 目的

Stage 2A実装指示書v1
(SHA-256 `521b09cfa16fdbf88207e97f7c25601bac5451ce727042cba0f416da96a2d223`、
12,861 bytes / 274行)をv1.1へ改訂する。変更は次の2点。

1. §1.1の境界矛盾解消。変更対象を「source 2件のみ」から
   「source 2件 + 波及test」に改める。§4.4/§6/§2.2のtest更新要求と整合させる。
2. Codex事前調査で確定した実装方式(PriorityQueue / client queue 256 /
   通常FIFO / heartbeat高優先 / overflow時は当該clientのみ切断)を確定値として
   §3へ反映する。

矛盾の性質: v1は§1.1でsource 2件に限定しながら、§2.2/§4.4/§6で既存test更新を
必須にした。testはsource 2件に含まれないため両立しない。これはClaude作成指示書の
欠陥であり、Codexが調査で検出・停止したのは規律どおりである。

本追記はドキュメント修正のみ。source/test/config変更は行わない。

---

## 2. 前提条件

対象file: `RTUIF_STAGE2A_PRIORITY_QUEUE_IMPLEMENTATION_INSTRUCTION_V1_20260803.md`

適用前SHA-256が次と一致することを確認する。不一致なら停止し報告。

```text
521b09cfa16fdbf88207e97f7c25601bac5451ce727042cba0f416da96a2d223
```

参考: 12,861 bytes / 274行 / LF / CR 0。
各anchorは対象file内で1回だけ出現することを確認済み。

---

## 3. 変更内容

### Edit 1: 版番号更新

**before:**

```text
**版:** 1.0
```

**after:**

```text
**版:** 1.1
```

### Edit 2: §1.1 見出しと対象範囲の改訂

対象: §1.1 の見出し行

**before:**

```text
### 1.1 変更対象file(2件のみ)
```

**after:**

```text
### 1.1 変更対象file(source 2件 + 波及test)
```

### Edit 3: §1.1 テーブル直後へtest許可範囲を追記

対象: §1.1 の改行保持規律の段落末尾

**before:**

```text
着手前に両fileの実SHA-256が上記と一致することを確認する。不一致なら停止し報告。
`main.py`はCRLF/LF混在(CRLF 1041 / LF 96)。指示書v1.1 §2.4の改行保持規律を適用する。
編集する行の改行コードを周辺既存行に合わせ、一括変換・normalizeを禁止する。
```

**after:**

```text
着手前に両fileの実SHA-256が上記と一致することを確認する。不一致なら停止し報告。
`main.py`はCRLF/LF混在(CRLF 1041 / LF 96)。指示書v1.1 §2.4の改行保持規律を適用する。
編集する行の改行コードを周辺既存行に合わせ、一括変換・normalizeを禁止する。

上記2 sourceに加え、配信意味の変更(enqueue即時・送信非同期化)により正当に
失敗する既存testの更新を許可対象に含める。ただし次を厳守する。

- 更新できるのは、§2.2の波及調査で「実装前に把握済みの想定fail」として列挙し、
  Stage 1調査報告へ記録したtestに限る。事前列挙のないtestを実装中に発見した場合は
  停止して報告し、更新前にStage 1節へ追記する。
- 更新は新挙動への追随に限る。既存assertionの緩和・削除・renameで通してはならない。
  同期完了前提のassertionを非同期配信前提へ書き換える場合も、検証する不変条件
  (最終的に全通常messageが相対順序で届く、heartbeatが届く等)は保持する。
- 配布default assertionや契約testを、値を弱めて通す変更は禁止する。
- test更新も変更境界(§5)とdiff管理の対象とし、更新したtest fileを開始終了で
  一覧化する。source 2件・許可testの外に新規diffがゼロであることを証明する。
```

### Edit 4: §3.1 実装方式の確定(Codex調査結果の反映)

対象: §3.1 の方式選択の段落

**before:**

```text
実装方式は次のいずれかをStage 1で選び設計文に明記する(実装はStage 2A本体)。

- (方式1)`asyncio.PriorityQueue`にpriority付きでenqueue。同一priority内は
  投入順(FIFO)。heartbeatを高優先度、通常messageを低優先度とし、通常message間の
  相対順序はsequence番号で保つ。
- (方式2)高優先queueと通常queueの2本を持ち、writerが高優先を先に排出。

いずれでも「通常message同士の相対順序維持 + heartbeat割込」を満たすこと。
方式選択の根拠(実装単純性、順序保証の確実性)を記す。
```

**after:**

```text
実装方式はCodex事前調査で次に確定した。

- `asyncio.PriorityQueue`方式を採用する。
- clientごとにqueueを持ち、queue上限は256件とする。
- heartbeatを高優先、通常message(TICK/BOOK/Tape/Flow/BAR)を低優先とする。
- 同一priority内は投入順(FIFO)。通常message間の相対順序をsequence番号で保つ。
  heartbeat同士が同時滞留した場合も投入順を保つ。
- priority比較でpayload本体を比較対象にしない(dictの大小比較例外を避けるため、
  (priority, sequence)のtupleキー等で順序を決め、payloadは比較に含めない)。

queue上限256件の根拠と、Stage 2A soakでの妥当性確認方法を設計文に記す。
256件が過大/過小と判明した場合はsoak結果に基づき見直す。
```

### Edit 5: §3.5 overflow挙動の確定

対象: §3.5 のoverflow時挙動の記述

**before:**

```text
- overflow時挙動: 通常messageはoldest drop または client切断のいずれかを選び
  根拠を記す。heartbeatはoverflowで捨てない(生存信号のため)。
```

**after:**

```text
- overflow時挙動: queueが256件上限に達した場合、黙ってmessageを捨てず、
  当該clientのみを切断する(writer終了 + unregister)。他clientへ波及させない。
  これは第一是正のslow-client隔離原則と一致する。「黙ってdrop」は
  consumerが欠落を検知できないため採らない。切断はconsumer側のWebSocket
  close検知→再接続→再同期へ繋がり、欠落した状態のままLIVE表示を続けるより安全。
- heartbeatはoverflow起因でも生存信号として扱うが、そもそもqueue上限に達する前に
  当該clientを切断するため、heartbeatだけを特別に残す分岐は要さない。
```

---

## 4. 適用後の検証手順(Codex実施・報告)

1. 適用前SHA-256一致確認。
2. 全5 Editの適用結果(適用/anchor不一致で停止)。
3. grep確認:
   - `**版:** 1.1` が1件、`**版:** 1.0` が0件。
   - `### 1.1 変更対象file(source 2件 + 波及test)` が1件。
   - `queue上限は256件` が1件。
   - `当該clientのみを切断する` が1件。
   - `asyncio.PriorityQueue`方式を採用する が1件。
4. 適用後SHA-256、bytes、行数、CR数を報告。Claudeドライラン期待値は次のとおり。
   一致するはずである。不一致なら差分箇所を特定して報告。

   ```text
   expected SHA-256: ddc8310b20251a1d72470406f1688137a3a98d3ebfc107498d622d1728747f8f
   expected bytes:   14,715
   expected lines:   295 (LF, CR 0)
   ```
5. 対象file以外に差分がないことを確認。
6. git add/commit/pushは行わない。

---

## 5. 禁止事項

- 本追記に記載のない箇所の変更(整形・rename・空白正規化を含む)。
- source/test/config/runtimeへの変更。
- 対象fileの改行コード(LF)・エンコーディング(UTF-8)の変更。
- git commit/push/branch操作。

---

## 6. 適用後の流れ

本追記適用でStage 2A指示書はv1.1として確定する。境界矛盾は解消され、
test更新がsource 2件と並ぶ正規の許可対象になる。

その後、Codexはv1.1に従いStage 2A手順1(§2 Stage 1調査の最終確定)を提出済みの
調査へ統合し、ユーザーの明示GObをもって手順2以降(実装)へ進む。
実装開始はユーザー明示GOによる。決定はユーザーが下し、Claudeが文書化する。
