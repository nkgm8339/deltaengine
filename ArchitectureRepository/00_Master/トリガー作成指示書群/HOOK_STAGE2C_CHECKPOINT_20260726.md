# Hook Detector / Trigger Observe — Stage 2C Checkpoint

最終更新: 2026-07-26 20:10 JST
状態: **収録継続中。Hook実市場妥当性・Trigger検証・継続PDCA仕様は承認待ち。threshold較正は停止中。**

## 承認範囲

- 正本承認書:
  `HOOK_STAGE2C_START_APPROVAL_20260726.md`
- Stage 2Cは次の順で進める。
  1. 2C-1: full／liquidationそれぞれの収録完了判定
  2. 2C-2: gate合格Hookだけのthreshold較正
  3. 2C-3: replay発火頻度検証とユーザー報告
  4. 2C-4: ユーザー承認後、較正済みHookだけobserve発火解禁
- fullとliquidationは期限が異なるため、2C-1を個別に報告する。
- 各工程完了後、次工程へ進む前にユーザー承認を得る。

2026-07-26 20:10 JST、ユーザーの最新指示により、現行工程には次の必須要件が不足していると
確認した。

- 88 Hookが生データ上の現象を正しく捉えたかの独立照合
- 日、session、side、regimeをまたぐ実市場耐性
- 検証済みHookを時系列・確認・否定条件で意思決定へ結ぶTrigger検証
- 新旧版を同じraw inputで比較し、再検証・昇格・rollbackできる継続PDCA

この不足を解消する承認案を
`HOOK_TRIGGER_VALIDATION_PDCA_SPEC_V1_20260726.md`へ記録した。正本承認書は履歴として
改変しない。本仕様が承認された場合、2C-1以後の順序を同仕様の2C-H1以後へ置き換える。

## 禁止境界

- Playbook選抜、check移行、LIVE注文はStage 2Cの範囲外。
- `execution_enabled`を`true`にしない。
- `playbooks.yaml`は`OBSERVE`のまま維持する。
- 較正gate未達Hookへ手動thresholdを設定しない。
- UNCALIBRATED Hookを発火させない。
- 収録データを削除、修正、truncateしない。
- 完成済みFlow Price Response、3段チャート、8パターンの計算・表示を変更しない。

## 着手時の確認済み状態

確認時刻: 2026-07-26 19:32:38 JST

- `/api/health`: GREEN
- campaign: `stage2a_20260726_xz`
- full session:
  `session-20260726T093841.387745Z-595a71bc`
- full: 53,713 accepted / 53,706 durably committed
- full pending 0、drop 0、disk reject 0、writer errorなし
- liquidation session:
  `session-20260726T093841.419644Z-2e58c677`
- liquidation: accepting、0 accepted / 0 committed
- liquidation drop 0、disk reject 0、writer errorなし
- C:空き: 17,456,898,048 bytes
- 8GB安全基準: 合格
- campaign全体: 54,388,384 bytes / 69 files
- full stream: 53,243,421 bytes / 41 files
- liquidation stream: 9,163 bytes / 25 files

## 期限

### full

- original deadline: 2026-07-29 13:19:39.359895 JST
- confirmed extension: 877.042594秒
- current effective deadline: 2026-07-29 13:34:16.402489 JST

### liquidation

- original deadline: 2026-08-09 13:19:39.359895 JST
- confirmed extension: 877.048933秒
- current effective deadline: 2026-08-09 13:34:16.408828 JST

今後確認済みinvalid intervalが追加された場合、append-only台帳の規則に従って
effective deadlineだけが延長される。判定時は固定転記値ではなくAPIと台帳の最新値を正本とする。

## fail-closed確認

- `hook_thresholds.yaml`: `default_status: UNCALIBRATED`
- `hook_thresholds.yaml`: `thresholds: {}`
- `playbooks.yaml`: `mode: OBSERVE`
- `playbooks.yaml`: `execution_enabled: false`
- `playbooks.yaml`: `playbooks: {}`
- threshold変更0、HookEvent解禁0、注文操作0

## 2C-1 full期限到達時に行うread-only判定

1. health、campaign、session、original／effective deadlineを保存する。
2. C:空きとcampaign／stream別実消費量を報告し、残り8GB以上を確認する。
3. coverage ledgerのhash／sequence／重複なし停止延長を検証する。
4. full session群のcommit済みframeを全replayし、hash、件数、sequence、tailを検証する。
5. 累計valid DOM coverage 72時間以上を確認する。
6. valid depth diff 2,000,000件以上を確認する。
7. 3つ以上のUTC日binが各18時間以上validか確認する。
8. Asia／London／New Yorkを各3巡以上含むか確認する。
9. episode型Hookのside別eligible episode 100件以上を確認する。
10. Hookごとに`GATE_PASS`／`GATE_FAIL`と不足量を報告する。

この判定結果をユーザーへ報告する。`HOOK_TRIGGER_VALIDATION_PDCA_SPEC_V1_20260726.md`が
承認され、Hook claimの独立照合と実市場耐性gateを通過するまでthresholdを変更しない。

## liquidation期限到達時に行うread-only判定

- 累計valid coverage 336時間以上、暦span 14日以上
- UTC 6時間帯binの分布
- 4つ以上の異なるweekend UTC date
- normalized forceOrder 4,000件以上
- long／short liquidation各1,000件以上
- side別active cascade window各250件以上
- E05／E06／C09 eligible episode各30件以上
- drop 0、writer error 0、disk reject 0

未達ならE01-E06／C09を`UNCALIBRATED`のまま報告する。
full側でgate合格した他Hookの工程を、この不足だけで止めない。

## 今回の変更file

- `HOOK_STAGE2C_START_APPROVAL_20260726.md`（ユーザー提示済み原文を正本採用、本文変更0）
- `HOOK_STAGE2C_CHECKPOINT_20260726.md`
- `引き継ぎ_20260726.md`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

source code、config、UI、runtime、収録データの変更0。

## 文書commitと最終稼働確認

- Stage 2C開始文書commit:
  `90b9b1a docs(observation): start Hook Stage 2C waiting phase`
- 4 file、305 insertions。push未実施。
- commit直後のstaged／unstaged差分0。
- 2026-07-26 19:37:10 JST: health GREEN。
- full durably committed: 58,226。
- full drop 0、disk reject 0、writer errorなし。
- C:空き: 17,456,787,456 bytes。8GB安全基準合格。

## Blockerの限定範囲

- 収録継続と2C-1 read-only判定にblockerなし。
- Hook manifest、独立validator、Trigger validatorの実装は新仕様のユーザー承認待ち。
- threshold較正は、仕様承認後もHook独立照合・実市場耐性gate完了まで停止する。
- liquidation 0件は現時点の観測事実であり、期限到達前のgate failureとは判定しない。
- 次の工程は時間依存のため、full effective deadline到達までは収録継続が正しい待機状態である。

## 次の再開位置

最初の再開位置は、`HOOK_TRIGGER_VALIDATION_PDCA_SPEC_V1_20260726.md`のユーザーレビューである。
承認された場合、期限前でも88 Hook claim監査と独立validator実装から開始する。
full effective deadline到達後は、承認状況にかかわらず上記2C-1 read-only判定を実施する。
期限前に停止や容量警告が発生した場合は、その限定工程だけを先に監査し、収録保全を優先する。
ユーザー承認前に新仕様を実装せず、Hook妥当性gate前に2C-2 threshold較正へ進まない。

## 2026-07-26 20:10 JST 追加checkpoint

- 承認範囲: Hook／Trigger検証・PDCAの仕様作成のみ。実装、較正、発火解禁は未承認。
- 完了済み: 既存catalog、detector、runtime、threshold、playbook、Stage 2C文書の再監査。
- 完了済み: `HOOK_TRIGGER_VALIDATION_PDCA_SPEC_V1_20260726.md`承認案の作成。
- 未完了: ユーザー仕様レビュー、88 Hook claim監査、独立reference実装、市場耐性検証。
- 変更file: 新仕様書、本checkpoint、`PROJECT_MEMORY.md`。
- source code、config、runtime、UI、raw収録データの変更0。
- 検証結果: 仕様467行、trailing whitespace 0、SHA-256
  `d8289069b4d9e473c8340bbcf0432b975323f5d656f50bb4f080ce59cf6c840b`。
- 検証結果: `git diff --check`合格。変更対象は本仕様、checkpoint、PROJECT_MEMORYの文書3件だけ。
- blockerの限定範囲: 新仕様を必要とする実装・較正だけ。収録と2C-1は継続する。
- 次の再開位置: ユーザーの仕様承認または修正指示。
