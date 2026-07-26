# Hook Detector / Trigger Observe — Stage 2B 完了報告

報告時刻: 2026-07-26 18:47 JST
対象: 承認済み `HOOK_STAGE2B_START_PROPOSAL_20260726.md`
状態: **Stage 2B完了、append-only収録継続中、Stage 2C未着手**

## 1. 結論

Stage 2Bの二つの工程を完了した。

1. **Stage 2B-R**: crash-safe収録、capacity gate、停止延長台帳、Windows自動復旧
2. **Stage 2B-D**: A/C/D/E/F/G detectorとsynthetic test

二度目の実機PC再起動では、人手によるDocker／Compose／resume script実行前に
Scheduled TaskがDockerを起動し、同一campaignの新sessionを開始し、GREENまで検証した。
boot前sessionのdurable commitも全hash、件数、sequenceを再検証できた。

Stage 2Bの完了は、統合ENTRY GO、較正完了、HookEvent発火解禁、Playbook選抜、
Stage 2C、LIVE注文の完成を意味しない。全thresholdは引き続き`UNCALIBRATED`、
`playbooks.yaml`は`OBSERVE`、`execution_enabled: false`、playbook空である。

完成済みFlow Price Response、3段チャート、8パターン、既存UIの計算・意味・表示は
変更していない。

## 2. Stage 2B-R 完了結果

### 2.1 容量

- Docker VHDX: 20,557,332,480 bytesから8,747,220,992 bytesへcompact
- compact後のDocker復旧・30分超安定時C:空き: 約18.38GB
- 二度目のboot正式検証時C:空き: 17,930,125,312 bytes
- Stage 2B受入gateの8,000,000,000 bytesを合格
- 削除対象は再生成可能なDocker build cache 2.267GBだけ
- 稼働image、rollback／保全image、container、volume、市場記録の削除0

### 2.2 crash-safe journal

- XZを最大1秒単位の独立frameへ変更
- data fileを`flush + fsync`後、manifestへ`FRAME_COMMIT`をappendして`fsync`
- `accepted`、`persisted`、`durably_committed`を分離
- summaryなしcrash sessionでもcommit済みframeだけを検証してreplay可能
- 未commit tailは削除・切詰めせず、byte数を報告して較正対象外にする
- liquidationはforceOrder受信batchごとにcommit

controlled hard-killでは、graceful summaryなしの旧sessionから729 frame、
16,253 recordを全件回収した。hash不一致、件数不一致、sequence gapは0、
uncommitted tailは0 bytesだった。復旧後は同一campaignの新sessionを開始し、
drop、disk reject、writer errorはいずれも0だった。

### 2.3 coverage／期限

- `coverage_events.jsonl`と`deadline_extension_events.jsonl`をappend-only／fsyncで追加
- original deadlineは改変しない
- 確認済みinvalid intervalだけを重複なしで延長
- DOM自動延長上限72時間、liquidation自動延長上限7日
- 較正gateは累計valid coverage、分布範囲、Hook別標本数の三重条件

二度目のreboot停止は、両streamへ173.113357秒ずつ1回だけ追記された。

| stream | original deadline | 累計延長 | effective deadline |
|---|---|---:|---|
| full | 2026-07-29 13:19:39.359895 JST | 877.042594秒 | 2026-07-29 13:34:16.402489 JST |
| liquidation | 2026-08-09 13:19:39.359895 JST | 877.048933秒 | 2026-08-09 13:34:16.408828 JST |

### 2.4 Windows自動復旧

Task `DeltaEngineHookCaptureStartup`を次で固定した。

- Windows startup 30秒delayとcurrent user logon trigger
- S4U、Highest
- 2分間隔、最大10回retry
- `ExecutionTimeLimit` 30分
- actionは`resume_hook_capture.ps1`の1コマンドだけ

初回実機再起動ではDocker、Compose、収録再開までは人手ゼロで成立したが、
15分health windowに対してGREEN待機が180秒だったためTask結果1となった。
GREEN条件は緩和せず、`HealthTimeoutSec`を1,200秒へ、Task上限を30分へ修正した。

二度目の実機再起動結果:

- boot: 2026-07-26 09:36:22.5000000 UTC
- Task開始: 2026-07-26 09:37:05 UTC
- Docker ready: 2026-07-26 09:38:37 UTC
- Compose started: 2026-07-26 09:38:39 UTC
- GREEN確認: 2026-07-26 09:39:12 UTC
- Task state: Ready
- `LastTaskResult`: 0
- campaign: `stage2a_20260726_xz`のまま
- post-boot full session:
  `session-20260726T093841.387745Z-595a71bc`
- post-boot liquidation session:
  `session-20260726T093841.419644Z-2e58c677`
- 人手によるDocker／Compose／resume script実行: 0

正式artifact
`boot-verification-20260726T094441.8131558Z-bb523bca.json`は
`success: true`、errors空である。

### 2.5 boot前sessionの回収検証

boot前full session
`session-20260726T073619.006422Z-18e43667`は不意停止のためsummaryなしだが、
`JournalReplay(..., allow_active=True)`で次を検証した。

- commit済みframe: 6,406
- record: 126,707
- sequence: 1から126,707まで連続
- 全frame SHA-256、record件数、first／last sequence: 一致
- uncommitted tail: 0 bytes

preboot artifactに保存したsequence 125,885..125,896のframe SHA-256
`2ed7fd8750601cdddba4d8e70923d486fd93616882b64ede74eba1ebf615ab81`
も旧manifestと再照合一致した。

boot前liquidation sessionはrecord 0、uncommitted tail 0 bytesである。

### 2.6 post-boot収録

2026-07-26 09:46:05 UTCの再確認:

- health: GREEN
- full: 6,924 accepted / 6,908 persisted / 6,908 durably committed
- pending: 0
- queue drop: 0
- disk reject: 0
- writer error: なし
- liquidation: accepting、0 committed

自動復旧artifactのGREEN確認時31 committedから継続増加しており、
boot後の新sessionが実際に収録を続けている。

## 3. Stage 2B-D 完了結果

既存検出器の外側に、較正前の測定candidateを作る独立detectorを追加した。

- A01-A24: DOM wall、pull、depth変化、asymmetry、quote移動、spread、
  iceberg／spoofing suspected、vacuum、wall追従
- C03-C09: absorption failure／repeat、wall collision／consumption、
  liquidation absorption
- D06-D08: Flow EFFECTIVE→TRAPPED、TRAPPED解消、多窓方向一致
- E01-E06: forceOrder単発、side別cascade、価格無反応、exhaustion
- F01-F05: OI変化×価格方向4象限、OI shock
- G01-G11: 直近高安、break／failed break、session VWAP、
  Volume Profile HVN、round number、range edge

candidate生成前にstale、DOM gap／invalid、crossed book、future-dataを拒否する。
数値採否は共通`ThresholdBook`へ委譲し、
`config/hook_thresholds.yaml`は`default_status: UNCALIBRATED`、
`thresholds: {}`のままである。今回実装した56 Hook候補のHookEvent発火は0。

detector moduleは既存trade pipelineの計算を置換せず、Stage 2Bでは発注経路へ接続していない。

## 4. 試験・性能

- detector synthetic単独: **14 passed**
- Stage 2A契約＋Track R＋Stage 2B対象: **28 passed in 2.99s**
- orderflow＋observation回帰: **199 passed in 4.27s**
- repository全体回帰: **516 passed in 61.10s**
- Python compile／import: 成功

二度目のboot後、commit直前にも同じorderflow＋observation対象を再実行し、
**199 passed in 3.99s**を確認した。通常sandboxで先に出た10件のsetup errorは、
pytest一時directoryのWindows ACLによる`PermissionError`であり、通常権限で全件合格した。

r3 image内DOM benchmark、10,000 frame、50 level／side:

- mean: 0.830ms
- p99: 4.314ms
- max: 12.733ms

提案gateのp99 10ms未満、max 25ms未満を合格した。
queue overflow、disk reject、writer errorはlive受入時0である。

## 5. 保全境界

- 稼働image:
  `sha256:fbc594ed132d0ced7195364c26c6781c99798df50bd3e4b0c3b041cdb797b4ab`
- image tag:
  `deltaengine_05m-deltaengine-clone:stage2b-20260726-r3`
- host UI SHA-256:
  `c23001dbc13882cb5b5c50bc9c797f9e00768fb5f0a1f741adf52d267515cef3`
- 稼働container UI SHA-256:
  `c23001dbc13882cb5b5c50bc9c797f9e00768fb5f0a1f741adf52d267515cef3`

UIは1 byteも変更していない。既存市場記録は削除、修正、truncateしていない。

## 6. 未完了・次の判断

Stage 2Bとして未完了項目はない。ただし、次は別工程であり未着手である。

- DOM 72時間とliquidation 14日の収録完了
- coverage／分布／Hook別標本数gateの最終判定
- threshold較正とmanifest生成
- HookEvent発火解禁
- Playbook候補の選抜と期間外評価
- Stage 2C
- check／LIVE移行
- LIVE注文

特にliquidationは報告時点で0件であり、E01-E06／C09を較正済みと扱えない。
収録はeffective deadlineまでbackgroundで継続する。

ユーザー確認前にStage 2Cへ進まない。

## 7. Version control

- Stage 2B本体commit:
  `394cd83 feat(observation): complete Hook Stage 2B`
- 対象: 31 file、4,587 insertions、88 deletions
- commit直後のvisible未コミット差分: 0
- remoteへのpush: 未実施
