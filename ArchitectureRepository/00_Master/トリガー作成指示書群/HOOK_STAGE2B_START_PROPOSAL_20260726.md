# Hook Detector / Trigger Observe — Stage 2B 着手提案

作成時刻: 2026-07-26 14:27 JST
対象: `Delta_Engine_Pro4web` / Stage 2A完了後
状態: **着手提案。Stage 2B実装、Task Scheduler登録、PC再起動は未着手。**

参照:

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `HOOK_DETECTOR_TRIGGER_OBSERVE_DESIGN_PROPOSAL_20260726.md`
- `HOOK_STAGE2A_COMPLETION_REPORT_20260726.md`
- `detector_implementation_instruction.md`
- `フックトリガーカテゴリhook_trigger_catalog_v1.md`

## 0. 結論

Stage 2Bは、次の2系統を同じ承認範囲で進めることを提案する。

1. **Stage 2B-R — 収録の耐障害化、容量gate、自動再開**
2. **Stage 2B-D — A/C/D/E/F/G detector実装とsynthetic test**

2B-Rをlive配備の先頭に置く。ただし容量確保、Task Scheduler、再起動試験を待つ間も、
既存systemへ接続しないdetector実装とtestを進め、収録待ちを理由に全体を止めない。

Stage 2Bの完了条件は、detector codeが存在することだけではない。次を全て満たすこととする。

- 不意停止前にdurable commit済みの記録が、停止後もhash、件数、sequenceを検証して読める。
- Windows起動後、人手のコマンド操作なしでDocker、DeltaEngine、同一campaignの収録が再開する。
- 実機PC再起動で自動再開を確認し、boot前後artifactをappend-onlyで保存する。
- 自動再開が失敗した場合にも、復旧操作が1コマンドに固定されている。
- 較正gateと停止延長がcodeと文書で同じ規則を使う。
- A01-A24、C03-C09、D06-D08、E01-E06、F01-F05、G01-G11を実装し、
  未較正のまま発火0を維持する。

完成済みFlow Price Response、3段チャート、8パターン、既存UI、既存記録は変更しない。
Flow単体発注、Playbook発注、LIVE注文は引き続き禁止する。

## 1. 2026-07-26 14:25 JSTの現状

### 1.1 稼働状態

- `/api/health`: GREEN
- full capture: 51,303 accepted / 51,303 persisted
- liquidation capture: 0 accepted / 0 persisted
- queue drop: full 0 / liquidation 0
- writer error: fullなし / liquidationなし
- full deadline: 2026-07-29 04:19:39 UTC
- liquidation deadline: 2026-08-09 04:19:39 UTC
- Docker container: `deltaengine_05m-deltaengine_clone-1`
- Compose: `restart: unless-stopped`

現時点の収録は正常である。ただし、以下の2点は現状のままでは要求を満たさない。

### 1.2 不意停止耐性の現状判定: **未達**

現行journalはUTC時間単位の1本のXZ streamである。

- segment hashと`SEGMENT_CLOSE`は時間切替またはgraceful close時に確定する。
- manifestの各eventは`flush`するが、session終了前は毎回`fsync`していない。
- `session_summary.json`はgraceful close時だけ作られる。
- summaryなしsessionは、activeかcrash-incompleteかを区別できないためreplayがsession全体を拒否する。

したがって、graceful stopなら正常closeできるが、電源断・process kill時はactive segmentが
未確定となり、同じsession内の先にcloseしたsegmentも標準replayでは利用できない。
これは「停止までの記録が壊れないこと」をまだ確認できた状態ではない。

### 1.3 PC起動時自動再開の現状判定: **未達**

- Docker Desktop設定: `"AutoStart": false`
- DeltaEngine／Hook capture用Scheduled Task: なし
- Composeの`restart: unless-stopped`は、Docker engineが起動した後のcontainer再開には有効だが、
  PC起動時にDocker Desktop自体を起動しない。

よって現状では、PC再起動後に収録が人手ゼロで再開する保証はない。

## 2. ① 清算収録14日分のディスク容量

### 2.1 単位と前提

- 本節の`GB`は10進数、`GiB`は2進数で表す。
- Stage 2A報告時C:空き: **6,771,744,768 bytes = 6.772GB = 6.306GiB**
- 現行disk guard: **1,073,741,824 bytes = 1GiB**
- 既存記録は削除、改変、上書きしない。
- full rawは最初の3日で終了し、その後はliquidation rawだけが14日まで継続する。

### 2.2 liquidation raw単体

XZ benchmarkでは、同型のsynthetic forceOrder 100件が1,208 bytesだった。ただし同じ形の値が
反復するため、これは実市場の下限寄りであり、そのまま14日見積りには使わない。

安全側に、時刻、価格、数量、envelope、frame／manifest overheadを含め、
**1件512 bytes・14日100,000件**をstress budgetとする。

| ケース | 件数 | 見積り |
|---|---:|---:|
| 較正最低件数 | 4,000 | 2.05MB |
| stress budget | 100,000 | 51.2MB |
| file／manifest／再起動session余裕込み採用値 | — | **64MB** |

清算rawだけなら64MB budgetであり、C:を支配する要因ではない。
容量を支配するのは、同じPCで継続する既存shadowと既存Parquetである。

### 2.3 PC全体で14日完走するための見積り

`flow_response_shadow.jsonl`は、2026-07-25 06:21:56 UTCから
2026-07-26 05:25:04 UTCまでの約23.05時間で275,912,319 bytes増加しており、
実測換算は約287MB/日である。安全側に300MB/日を採用する。

| 増分 | 採用日次値 | 日数 | 見積り |
|---|---:|---:|---:|
| 既存flow shadow | 300MB/日 | 14日 | 4,200MB |
| 既存Parquet／DuckDB | 60MB/日 | 14日 | 840MB |
| Stage 2A full raw XZ | 126.7MB/日 | 3日 | 380.1MB |
| liquidation raw XZ | stress budget | 14日 | 64MB |
| **予測増分合計** |  |  | **5,484.1MB** |

Stage 2A報告時の6,771,744,768 bytesを基準にしても、1GiB guardを残した余裕は
約214MBしかない。14日完走の机上最小値には届くが、相場活況、Parquet増加、停止延長、
Docker VHDX再拡張を吸収できず、運用上は不合格とする。

予測増分へ20% contingencyと1GiB guardを加えた必要量は:

```text
5,484,100,000 × 1.20 + 1,073,741,824
= 7,654,661,824 bytes
```

Stage 2Bの**収録開始／継続capacity gateは、Docker稼働後30分間のC:空き最小値が
8,000,000,000 bytes以上**とする。

### 2.4 6.77GB報告値の訂正

2026-07-26 14:22 JSTの再測定:

- C:空き: **約2.97GB = 2.77GiB**
- Docker VHDX physical size: **約20.56GB**

Stage 2A報告時の6.77GBはDocker／WSL停止直後にsparse blockがhostへ返った時点の値であり、
Docker稼働後の持続値ではなかった。2.97GBを現在の実効値として扱う。

現状のままでは、1GiB guardまでの使用可能量は約1.90GBである。最初の3日を
約486.7MB/日、その後を約360MB/日とすると、概算約4.2 active日でguardへ達する。
2026-08-09までの14日収録は完走できない。

容量blockerは次のように限定する。

- Stage 2Bのoffline detector実装／testは継続できる。
- live durability配備、実機再起動試験、14日完走判定は、安定空き8GB未満では合格にしない。
- 市場記録を削除して空けない。容量確保の具体操作が削除、移動、VHD変更を伴う場合は、
  exact targetと復旧方法を示して別途承認を得る。
- 5分ごとにfree bytesと残日数をappend-onlyで記録し、残り72時間予測で警告する。
- 既存1GiB hard guardは維持する。

## 3. ② 不意停止でも確定記録を壊さない構造

### 3.1 crash-safe XZ frame commit

時間単位の単一XZ streamを、同一segment内の**独立XZ frame commit**へ変更する。

1. raw arrival sequenceを最大1秒分だけbufferする。
2. そのbatchを独立したXZ frameへ圧縮する。
3. segment末尾へappendする。
4. data fileを`flush + fsync`する。
5. manifestへ`FRAME_COMMIT`をappendする。
6. manifestを`flush + fsync`する。

`FRAME_COMMIT`は最低限、次を持つ。

```text
file
offset
compressed_bytes
frame_sha256
first_sequence
last_sequence
records
first_received_time
last_received_time
committed_at
```

既存fileのtruncate、修正、上書きは行わない。不意停止で末尾に未commit byteが残った場合も
そのまま保存し、replayはmanifestでcommit済みのbyte rangeだけを読む。

session summaryが無い場合でも、commit済みframeはframe hash、record count、sequenceを
個別検証して`RECOVERED_COMMITTED`として利用できるようにする。
未commit末尾は`CRASH_TAIL_UNCOMMITTED`として件数またはbyte数を報告し、較正へ混ぜない。

保証境界を曖昧にしない。

- `accepted`: capture queueが受理した。
- `persisted`: writerがserializeした。
- `durably_committed`: dataとmanifestの両方がfsync済み。

「停止まで壊れない」の受入条件は、**停止前の全`durably_committed` recordが停止後も
1件もhash不一致・sequence欠落なく読めること**とする。
RAMまたは未commitの最大1秒分は、電源断で消える可能性を隠さずgapとして記録する。

liquidation streamは疎であるため、1秒を待たず、forceOrder受信batchごとにcommitを要求する。
既存market pipelineをblockしないbackground writer構造は維持する。

### 3.2 controlled crash試験

actual PC再起動前に、限定containerだけをhard killして次を確認する。

1. kill前にcommit済みの最終sequenceとhashをcheckpointへ保存。
2. graceful stopを経由しないprocess killを行う。
3. 同じ1コマンド復旧scriptでcontainerを再開する。
4. 旧sessionにsummaryが無くても、全commit済みframeをreplayできる。
5. 未commit末尾だけが明示除外される。
6. 新sessionが同じcampaignを継続する。
7. drop 0、writer error 0、market health GREENへ戻る。

既存Flow Price Response、DB、Parquet、UIの既存行／既存内容を変更・削除しない。
通常live運転による新規appendは継続し、その追加分を既存記録の改変と混同しない。

## 4. PC起動時の自動再開

### 4.1 追加するWindows側file

```text
Delta_Engine_Pro4web/tools/windows/
  resume_hook_capture.ps1
  install_hook_capture_startup_task.ps1
  verify_hook_capture_boot.ps1
```

`resume_hook_capture.ps1`は次を1回で行うidempotent scriptとする。

1. 同時実行をnamed mutexで排他する。
2. Docker Desktopを起動し、engine readyまでtimeout付きで待つ。
3. pinned Stage 2A/2B imageを使い、次と同等のComposeを実行する。

```text
docker compose -p deltaengine_05m -f docker-compose.yml -f docker-compose.stage2a.yml up -d --no-build deltaengine_clone
```

4. `/api/health`と`/api/stats`をpollする。
5. campaign ID、original/effective deadline、session、accepted、committed、drop、errorを検証する。
6. 1回ごとの結果を新規JSONL／JSON fileへappend-only保存する。
7. success時だけexit 0、失敗時は非0と具体的reasonを返す。

### 4.2 Scheduled Task

Task名を`DeltaEngineHookCaptureStartup`へ固定し、次の条件で登録する。

- Windows startup trigger、30秒delay
- current userで「ログオンしているかどうかにかかわらず実行」
- highest privilege
- AtLogOn triggerも冗長系として併設
- 失敗時2分間隔、最大10回retry
- 多重起動はmutexで1回へ集約
- Task actionは上記1コマンドscriptだけ

Docker Desktop内蔵AutoStartだけに依存しない。Scheduled TaskがDockerの起動、Compose、
health確認までを一つの復旧unitとして扱う。

### 4.3 手動fallbackの1コマンド

Scheduled Taskが環境依存で失敗した場合も、再開手順は次の1コマンドだけとする。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\user\Desktop\DeltaEngine05M\Delta_Engine_Pro4web\tools\windows\resume_hook_capture.ps1"
```

このscript内でDocker起動、Compose、health／campaign検証まで完結させる。

### 4.4 実機再起動の受入試験

Stage 2B承認後、Task登録とdry-runに成功したら、実際にPCを再起動する。
再起動直前に再開可能checkpointを保存し、boot後は自動生成artifactで次を確認する。

- boot time < Scheduled Task LastRunTime
- Docker Desktop status `running`
- pinned DeltaEngine container `running`
- `/api/health` GREEN
- campaign IDが同じ
- original deadlineが改変されていない
- reboot downtimeがcoverage ledgerへ1回だけ記録されている
- effective deadlineが規則どおり延長されている
- boot前sessionのcommit済みframeが全件valid
- boot後に新sessionが作られ、accepted / durably_committedが増える
- queue drop 0、disk reject 0、writer errorなし
- 人手のDocker／Compose／PowerShell操作0

再起動後に上記を確認できるまで「自動再開成功」と報告しない。

## 5. ③ 較正gateは連続稼働か、累計標本数か

結論は、**完全な連続稼働は要求しない。ただし累計標本数だけでも不可**とする。

較正解禁には次の三つを全て要求する。

1. 累計valid coverage
2. 日・時間帯・週末を含む分布範囲
3. Hook別のeligible sample／episode数

fileが存在した時間、processが起動していた時間、raw件数の多さだけでは合格にしない。

### 5.1 valid coverageの共通条件

次を全て満たす区間だけをvalidとする。

- capture heartbeatが継続
- 対象streamがaccepting
- acceptedとdurably committedの差が解消
- queue drop 0
- writer errorなし
- disk guard reject 0
- Binance combined streamが接続中
- event時刻が非正値／非有限／未来参照でない

DOMはさらに、Snapshot同期済み、initial bridge成立、diff連続、gap後はresnapshot済みを要求する。
liquidationが0件の静穏時間も、combined streamが健全ならcoverageには数えるが、
標本数gateには寄与しない。

### 5.2 DOM較正gate

- 累計valid DOM coverage: **72時間以上**
- valid depth diff: **2,000,000件以上**
- 3つ以上のUTC日binが、それぞれ18時間以上valid
- Asia／London／New Yorkの各時間帯を3巡以上
- queue drop 0、writer error 0、disk reject 0
- episode型Hookはside別eligible episode 100件以上

72時間が途中停止で4日以上の暦日に分かれても、上記を全て満たせば較正候補にできる。

### 5.3 liquidation較正gate

- 累計valid liquidation-stream coverage: **336時間以上**
- valid coverageの暦span: **14日以上**
- 4つのUTC 6時間帯binすべてに十分なcoverageがある
- 4つ以上の異なるweekend UTC dateにvalid coverageがある
- normalized forceOrder: **4,000件以上**
- long / short liquidation: **各1,000件以上**
- side別active cascade window: **各250件以上**
- E05/E06/C09 eligible episode: **各30件以上**
- queue drop 0、writer error 0、disk reject 0

336時間だけ、または4,000件だけの片方では解禁しない。

### 5.4 gate未達時

effective deadlineで標本数不足だったHookは`UNCALIBRATED`のままとする。
市場が静かで件数が不足したことは停止時間ではないため、自動延長しない。
実件数、不足数、coverageを報告し、追加収録はユーザー承認を求める。

## 6. ④ 停止期間があった場合の期限

### 6.1 延長対象

original deadlineは改変しない。次の確認済みinvalid intervalだけを停止時間とする。

- PC shutdown／reboot
- Docker engine停止
- DeltaEngine container停止
- capture process停止
- Binance stream切断
- streamがnot accepting
- writer error、queue drop、disk guard reject
- DOM gapから有効resnapshotまで

heartbeatは10秒ごとにdataとmanifestをfsyncし、停止区間は保守的に
`last durable heartbeat`から`first recovered durable heartbeat`までとする。

### 6.2 append-only延長台帳

`campaign_meta.json`は書き換えず、例えば次を新設する。

```text
coverage_events.jsonl
deadline_extension_events.jsonl
```

各延長eventは、stream、start、end、duration、reason、evidence、boot ID、event IDを持つ。
重複intervalはunionし、同じ停止を二重加算しない。

```text
effective_deadline
= original_deadline
+ 承認規則に合う重複なし停止秒数
```

停止がoriginal/effective capture windowの外なら延長しない。gate完了後も延長しない。
APIと報告ではoriginal deadline、累計停止、effective deadlineを並べる。

### 6.3 無期限化の防止

- DOM自動延長上限: **累計72時間**
- liquidation自動延長上限: **累計7日**
- sample不足、静穏相場、Hook episode不足は自動延長理由にしない。
- 上限到達時は収録を無断で延ばさず、Hookを`UNCALIBRATED`のまま停止報告する。

この規則により、短いPC停止はその時間だけ補填しつつ、収録が無期限にはならない。

Stage 2B導入前に既に生じた停止は、session metadata、summary、manifest、Docker eventから
開始・終了を証明できる区間だけをappend-only correction eventとして登録する。
時刻を証明できない区間は推測で延長せず、invalid coverageとして報告する。

## 7. Stage 2B Detector実装

収録と耐障害化に並行して、次の順序で実装する。

1. DOM feature cache
2. A01-A16、A21-A22
3. A17-A20、A23-A24
4. C03-C08
5. E01-E06
6. C09
7. F01-F05
8. G01-G08、G10-G11
9. G09 offline Volume Profile
10. D06-D08

A17-A20は`ICEBERG_SUSPECTED`／`SPOOFING_SUSPECTED`の名称を維持し、意図を断定しない。
全detectorはsynthetic正例、境界、反対side、非発火、gap、stale、future-data禁止を試験する。

Stage 2B中は全Hook thresholdを`UNCALIBRATED`のまま維持する。
detectorがcandidateを作れてもHookEvent発火は0、Playbookは空、executionは無効とする。

performance gateは第1段階提案を維持する。

- DOM Hook hot path p99 < 10ms
- max < 25ms
- storage／journal queue overflow 0
- 既存trade内部遅延p95悪化 < 10ms

## 8. 工程とcheckpoint

### Track R — 耐障害・容量

1. 2B-R1: frame commit、coverage ledger、effective deadlineのunit test
2. 2B-R2: controlled container hard-killとreplay検証
3. 2B-R3: 1コマンド復旧scriptとScheduled Task dry-run
4. 2B-R4: reboot前checkpoint保存
5. 2B-R5: 実機PC再起動
6. 2B-R6: boot後artifact、health、同一campaign、commit replay確認

### Track D — Detector

Track Rの外部待ちと独立して、上記A/C/D/E/F/G detectorとsynthetic testを進める。
live接続はTrack R合格後だけ行う。

次の時点でcheckpointを更新する。

- 最初のcode変更前
- frame commit test完了後
- hard-kill前後
- Scheduled Task登録前後
- PC再起動直前
- boot後の最初の自動検証後
- detector各category完了後
- Stage 2B未完了でturnを終える前

Stage 2B完了時に結果を報告し、ユーザー確認前にStage 2Cの閾値生成へ進まない。

## 9. 予定変更file

```text
src/observation/raw_journal.py
src/observation/hook_replay.py
src/observation/capture_coverage.py
src/orderflow/hooks/dom_features.py
src/orderflow/hooks/dom_wall.py
src/orderflow/hooks/dom_liquidity.py
src/orderflow/hooks/dom_quote_motion.py
src/orderflow/hooks/dom_iceberg.py
src/orderflow/hooks/interaction.py
src/orderflow/hooks/liquidation.py
src/orderflow/hooks/open_interest.py
src/orderflow/hooks/price_structure.py
src/orderflow/hooks/flow_transition.py
tools/windows/resume_hook_capture.ps1
tools/windows/install_hook_capture_startup_task.ps1
tools/windows/verify_hook_capture_boot.ps1
tests/observation/*
tests/orderflow/*
config/hook_observer.yaml
```

必要なruntime callbackは既存処理の横へoptional copyとして追加し、既存計算結果を変更しない。
`webapp/static/index.html`は変更しない。

## 10. 承認を求める内容

次をStage 2Bの承認対象とする。

1. Stage 2BをTrack RとTrack Dの並行工程にする。
2. crash-safe XZ frame commit、coverage ledger、append-only延長台帳を追加する。
3. 較正gateを「累計valid coverage + 分布範囲 + Hook別標本数」とする。
4. 確認済み停止時間だけを延長し、DOM 72時間／liquidation 7日を自動延長上限とする。
5. Windows Scheduled Taskと1コマンド復旧scriptを構築する。
6. 構築後に実機PC再起動を行い、人手ゼロの自動再開を検証する。
7. A/C/D/E/F/G detectorを実装するが、全Hookを`UNCALIBRATED`、発火0、
   全注文経路無効のままにする。
8. Stage 2B完了報告後に停止し、Stage 2Cへ自動で進まない。

容量については、安定空き8GBをlive受入gateとする。現在の実測約2.97GBでは未達である。
既存市場記録の削除・改変は承認対象に含めない。
