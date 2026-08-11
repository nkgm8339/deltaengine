# Big Trades実装前 baseline復元点 CHECKPOINT

- 更新時刻: 2026-08-11 22:36:01 JST
- user承認: 現在の主要状態を即時復元できるcheckpoint commit／tagの作成
- 作業branch: `feature/footprint-dom-tape`
- 開始HEAD: `778289d63f744adbe452186845d3709bbbdcfa0b`
- Big Trades source実装: 未着手

## 目的

現在完成しているFlow Price Response、3段チャート、Footprint、DOM、Tape、Heatmap、Absorption、market freshness、Binance Spot referenceと、そのsource／config／tests／正本文書をBig Trades実装前の一つのGit復元点へ固定する。

## 開始時事実

- tracked未コミット変更: 30 file。
- untracked status entry: 146件。
- staged change: 0件。
- untracked実file: 211 file、418,909,576 bytes。
- 大容量untrackedにはDuckDB、Parquet、JSONL、pytest生成物が含まれる。
- 現HEADは2026-08-04であり、現行3段チャート表示、market freshness、spot reference、Absorption等の最新状態を完全には含まない。

## commit対象

1. 現在のtracked変更全30 file。
2. 現在のuntracked runtime source／test 4 file。
3. Big Trades logic正本、V1.0／V1.1実装指示書、作業checkpoint。
4. 現行主要機能の復元判断に必要なMarkdown／text／small script。
5. 本checkpointと除外manifest。

## Gitへ入れない対象

- `*.duckdb`
- `*.parquet`
- runtime／validationのraw `*.jsonl`
- `__pycache__`、`*.pyc`
- pytest temporary output
- 再取得可能な測定／benchmark database

これらを削除しない。Git commitから除外するだけとし、path、size、SHA-256をmanifestへ記録する。

## 完了済み

- `AGENTS.md`と`PROJECT_MEMORY.md` 1,725行を全文再読した。
- branch、HEAD、dirty状態、untracked容量をread-only監査した。
- Flow Price Response本体はclean／commit済み、現行3段チャート関連fileは未コミットを含むことを確認した。

## 未完了

- exact stage対象と除外manifestの生成。
- baseline test。
- checkpoint commit。
- annotated tag。
- Big Trades専用作業branch。
- 最終restore検証。

## 変更file

- 本checkpointだけ。

## 検証結果

- source変更: 0件。
- config変更: 0件。
- runtime／container操作: 0件。
- test: 未実行。

## blocker

- なし。

## 次の再開位置

- 大容量生成物を除外したexact stage対象を確定し、baseline testを実行する。

## Preflight更新 — 2026-08-11 22:23:53 JST

- commit対象untracked: Markdown、text、Python、JavaScript、JSONの198 file、25,840,811 bytes。
- Git除外: 23 file、414,527,145 bytes。
- 除外全23 fileのpath、size、SHA-256を`BIG_TRADES_PREIMPLEMENTATION_GIT_EXCLUSIONS_20260811.md`へ記録した。
- 除外fileは変更・移動・削除していない。
- 未完了: baseline test、exact staging監査、commit、tag、作業branch、復元検証。
- 次の再開位置: 現行baseline testを実行する。

## Baseline test再実行checkpoint — 2026-08-11 22:26:28 JST

- `python -m pytest -q`の初回実行はcommand側120秒timeoutに到達した。
- timeout後も残った当該pytest processはPIDとcommand lineを照合し、そのprocessだけを停止した。
- source、config、test dataの変更は0件。
- blocker限定範囲: test timeout設定だけ。test failureはまだ観測されていない。
- 次の再開位置: timeoutを600秒へ広げ、同じfull pytestを再実行する。

## Baseline test完了 — 2026-08-11 22:32:12 JST

- command: `python -m pytest -q`
- working directory: `Delta_Engine_Pro4web`
- result: **846 passed, 1 failed, 1 skipped**。
- duration: 294.77秒。
- baseline failure:
  - `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
  - current `index.html`に旧selector文字列`body.phase5-fusion #right>#left{display:none!important}`が存在しないというassertion failure。
- 同failureは`PROJECT_MEMORY.md`の2026-07-31記録にある既存Heatmap layout selector／旧test不一致と同一であり、Big Trades実装前baselineとして固定する。
- testのためのsource修正は行っていない。
- 未完了: exact staging監査、commit、tag、作業branch、復元検証。
- 次の再開位置: commit対象だけをstageし、除外23 file混入0件を確認する。

## Exact staging監査完了 — 2026-08-11 22:34:56 JST

- staged: 229 file（追加199、変更30、削除0）。
- staged diff: 148,723 insertions、128 deletions。
- staged対象は、開始時のtracked変更全30 file、runtime source／test、正本文書、checkpoint、small evidence source／manifestである。
- unstaged tracked change: 0 file。
- Git除外拡張子（`*.duckdb`、`*.parquet`、raw `*.jsonl`、`*.log`、`*.patch`、`*.pyc`）のstaged混入: 0 file。
- remaining untracked: 除外manifest記載の23 fileだけ。
- `git diff --cached --check -- Delta_Engine_Pro4web`: pass。
- staged全体の`git diff --cached --check`は、既存Markdown evidenceに保存されていた行末2-space／blank-at-EOFを検出した。runtime source、config、test側の検出は0件であり、現在状態の完全保存を優先して既存文書を整形変更していない。
- source／configへの追加修正: 0件。
- blocker: なし。
- 未完了: checkpoint commit、annotated tag、Big Trades作業branch、復元検証。
- 次の再開位置: 本checkpoint更新をstageし、同一監査を再確認してcheckpoint commitを作成する。

## Baseline snapshot commit検証 — 2026-08-11 22:36:01 JST

- baseline snapshot commit: `ba0cc4476f60d0bcae2a3bfe5ba190df08cfde0c`。
- parent: `778289d63f744adbe452186845d3709bbbdcfa0b`。
- tree object: `07801cc9c444da4beee45887431d6f8485fed6d9`。
- commit subject: `checkpoint: preserve pre-Big-Trades baseline`。
- commit直後の状態: staged 0、unstaged tracked 0、untracked 23。
- `git fsck --no-dangling --no-progress`: pass。
- 除外manifest全23 fileを再計算し、missing 0、size／SHA-256不一致0を確認した。
- 最終記録commitの次に作成する固定復元tag: `pre-big-trades-20260811`。
- 同tagから分離する実装用branch: `feature/big-trades-v1`。
- Big Trades source実装: 未着手。
- 残作業: 本最終記録をcommitし、そのcommitへannotated tagを作成、同じcommitから実装用branchを作成して参照一致を検証する。
- 復元境界: tagはtracked source／config／tests／文書を復元する。除外manifestの23 local生成物はtag管理外で、現在pathに保持する。
