# Stage 2C-3 le operator Hook threshold修正レポート
実行日時: 2026-07-30 19:10:18 JST
実行者: Codex
対象データ: stage2a_20260726_xz/full（全session）

## 実行境界

- 変更対象: `config/hook_thresholds.yaml`内のG01/G02/G07/G09/G10/G11の`quantile`と`value`、および本レポート。
- 非変更対象: 上記6 Hookの他field、他32較正Hook、対象外11 Hook、収録データ、`playbooks.yaml`、UI、稼働中liquidation stream。
- D08は整数tieにより16.454764%だったが、指示どおり据え置く。
- リプレイはホスト側Pythonを`Idle` priority・固定CPU affinityで実行し、稼働コンテナ内では実行しない。

## Step 1: 修正前後

| Hook ID | operator | 修正前quantile | 修正後quantile | 修正前value | 修正後value |
|---|---|---:|---:|---:|---:|
| G01 | le | 0.90 | 0.10 | 15.8790121078 | 0.6629559612 |
| G02 | le | 0.90 | 0.10 | 17.1345938592 | 0.4339221152 |
| G07 | le | 0.90 | 0.10 | 35.113490544 | 1.505498512 |
| G09 | le | 0.90 | 0.10 | 12.5287637773 | 0.0923975332 |
| G10 | le | 0.90 | 0.10 | 3.4887781038 | 0.3699275117 |
| G11 | le | 0.90 | 0.10 | 9.2906141325 | 0.3896227886 |

## Step 2: ThresholdBook.load検証

修正後の`ThresholdBook.load`は成功した。

- CALIBRATED: 38 Hook
- 対象外UNCALIBRATED: 11 Hook
- 新config hash: `c9b2402ad53656525f6f36961132b24583dc4279866cf55a00661b81024ca84d`
- HEAD版とのdeep compareで差分は次の12 pathだけ:
  - `thresholds.G01.quantile` / `thresholds.G01.value`
  - `thresholds.G02.quantile` / `thresholds.G02.value`
  - `thresholds.G07.quantile` / `thresholds.G07.value`
  - `thresholds.G09.quantile` / `thresholds.G09.value`
  - `thresholds.G10.quantile` / `thresholds.G10.value`
  - `thresholds.G11.quantile` / `thresholds.G11.value`
- 6 Hookの`metric`、`operator`、`status`、`input_manifest_sha256`、`sample_count`、`valid_days`: HEAD版と一致。
- D08を含む他32較正Hook: HEAD版と一致。
- `git diff --check -- config/hook_thresholds.yaml`: 成功。

## Step 3: 発火率再検証

`tools/calibrate_hooks.py --with-thresholds`をホスト側Pythonで全29 sessionに対して実行した。親processと2 workerは全て`Idle` priority、親affinity `12`、worker affinity `4`/`8`に固定した。稼働コンテナ内では実行していない。

- 実行開始: 2026-07-30 19:27:57 JST
- 実行完了: 2026-07-30 21:53:41 JST
- elapsed: 8,740.217秒
- session: 選択29 / 成功28 / 失敗1
- 成功sessionのrecord: 9,054,572
- candidate row: 15,667,491
- 統計対象Hook: 49
- 較正済み発火率対象Hook: 38
- input manifest SHA-256: `f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b`
- threshold config SHA-256: `c9b2402ad53656525f6f36961132b24583dc4279866cf55a00661b81024ca84d`
- 失敗session: `session-20260726T041939.403610Z-1e9ed663`
- エラー: `JournalIntegrityError: segment is not closed: raw-20260726T04.jsonl.xz`

上記1件は前回Stage 2C-3と同じ既知の未close XZである。成功session、record数、candidate row数、49 Hookの標本数は前回結果と一致した。

### 全38 Hook発火率

| Hook ID | candidate数 | 発火数 | 発火率 | 判定 |
|---|---:|---:|---:|---|
| A01 | 723,556 | 72,354 | 9.999779% | 正常 |
| A02 | 723,265 | 72,328 | 10.000207% | 正常 |
| A03 | 423,212 | 42,322 | 10.000189% | 正常 |
| A04 | 416,832 | 41,684 | 10.000192% | 正常 |
| A05 | 935,052 | 93,506 | 10.000086% | 正常 |
| A06 | 931,297 | 93,130 | 10.000032% | 正常 |
| A07 | 1,011,389 | 101,139 | 10.000010% | 正常 |
| A08 | 1,007,302 | 100,731 | 10.000079% | 正常 |
| A09 | 1,194,226 | 119,423 | 10.000033% | 正常 |
| A10 | 1,080,611 | 108,061 | 9.999991% | 正常 |
| A11 | 41,240 | 4,124 | 10.000000% | 正常 |
| A12 | 40,084 | 4,009 | 10.001497% | 正常 |
| A13 | 40,302 | 4,031 | 10.001985% | 正常 |
| A14 | 41,429 | 4,143 | 10.000241% | 正常 |
| A15 | 41,438 | 4,144 | 10.000483% | 正常 |
| A16 | 40,251 | 4,026 | 10.002236% | 正常 |
| A17 | 285,761 | 28,579 | 10.001015% | 正常 |
| A18 | 316,051 | 31,607 | 10.000601% | 正常 |
| A19 | 423,212 | 42,643 | 10.076038% | 正常 |
| A20 | 416,832 | 42,413 | 10.175083% | 正常 |
| A21 | 2,274,837 | 227,459 | 9.998914% | 正常 |
| A22 | 2,274,837 | 227,502 | 10.000804% | 正常 |
| A23 | 88,938 | 8,894 | 10.000225% | 正常 |
| A24 | 93,831 | 9,384 | 10.000959% | 正常 |
| C06 | 670,740 | 67,074 | 10.000000% | 正常 |
| D07 | 2,039 | 204 | 10.004904% | 正常 |
| D08 | 63,787 | 10,496 | 16.454764% | 要注意（据え置き） |
| G01 | 3,935 | 394 | 10.012706% | 正常 |
| G02 | 3,935 | 394 | 10.012706% | 正常 |
| G03 | 620 | 62 | 10.000000% | 正常 |
| G04 | 710 | 71 | 10.000000% | 正常 |
| G05 | 307 | 31 | 10.097720% | 正常 |
| G06 | 334 | 34 | 10.179641% | 正常 |
| G07 | 3,963 | 397 | 10.017663% | 正常 |
| G08 | 3,963 | 397 | 10.017663% | 正常 |
| G09 | 3,963 | 397 | 10.017663% | 正常 |
| G10 | 3,963 | 397 | 10.017663% | 正常 |
| G11 | 3,935 | 394 | 10.012706% | 正常 |

全38 Hookで`eligible_count == candidate_count`を確認した。正常37、要注意1（D08）、異常0である。

### 修正6 Hookの前後比較

| Hook ID | 修正前発火数 | 修正前発火率 | 修正後発火数 | 修正後発火率 | 修正後判定 |
|---|---:|---:|---:|---:|---|
| G01 | 3,541 | 89.987294% | 394 | 10.012706% | 正常 |
| G02 | 3,541 | 89.987294% | 394 | 10.012706% | 正常 |
| G07 | 3,566 | 89.982337% | 397 | 10.017663% | 正常 |
| G09 | 3,566 | 89.982337% | 397 | 10.017663% | 正常 |
| G10 | 3,566 | 89.982337% | 397 | 10.017663% | 正常 |
| G11 | 3,541 | 89.987294% | 394 | 10.012706% | 正常 |

修正6 Hookは全て指定正常範囲5–15%に入った。未変更32 Hookについて、新旧JSON間でcandidate数、eligible数、発火数、発火率が完全一致した。D08は整数tieによる16.454764%のまま、指示どおりthresholdを変更していない。

## Step 4: テスト

### 指定detectorテスト

```text
python -m pytest tests/orderflow/test_stage2b_dom_detectors.py tests/orderflow/test_stage2b_context_detectors.py -q
..............                                                           [100%]
14 passed in 0.24s
```

### 全体回帰

最初の実行は60秒のcommand timeoutで中断したため、同じコマンドを5分枠で再実行して完走させた。

```text
python -m pytest -q -p no:cacheprovider
1 failed, 737 passed, 1 skipped in 151.29s (0:02:31)
```

失敗1件:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

これは本タスク開始前からdirtyだった`webapp/static/index.html`のUI selectorと既存test期待値の不一致であり、threshold修正とは無関係である。禁止範囲のUIおよびtestは変更していない。

## 事後状態

- 確認日時: 2026-07-30 22:02–22:07 JST
- container: `delta_engine_pro4web-deltaengine_clone-1` — Up 12 hours
- ports: `127.0.0.1:15555->5555/tcp`, `0.0.0.0:18080->8080/tcp`, `[::]:18080->8080/tcp`
- C:空き: 92,718,620,672 bytes
- 負荷終了直後health（22:02）: RED
  - latency RED: 35,880ms
  - memory YELLOW: 1,032MB
  - sequence gap / reconnect / pipeline / bar flow / tape: GREEN
- 回復確認（22:07:33）: YELLOW
  - latency GREEN: 202ms
  - memory YELLOW: 1,009MB
  - sequence gap / reconnect / pipeline / bar flow / tape: GREEN
- 最終poll（22:07:45）: YELLOW
  - latency GREEN: 1,359ms
  - memory YELLOW: 1,010MB
  - sequence gap / reconnect / pipeline / bar flow / tape: GREEN

長時間ホスト負荷終了直後のlatency REDは約5分後にGREENへ回復した。health全体はmemoryのみYELLOWのためYELLOWである。containerの停止・再起動・設定変更は行っていない。

## 作業checkpoint

- checkpoint日時: 2026-07-30 22:08 JST
- 承認範囲: le 6 Hookの`quantile`/`value`だけのp10修正、host側read-only全量replay、発火率検証、指定test、指定成果物のcommit。
- 完了済み: `PROJECT_MEMORY.md`全1192行再読、preflight、6 Hookの修正前field確認、container/health/C:空き確認、出力先不存在確認、指定12 fieldのYAML修正、ThresholdBook load、38/11件、deep diff、D08/他field不変、diff check、同一条件の全量replay、前回JSONとの機械比較、全38 Hook発火率表、修正6 Hookの正常化、未変更32 Hook不変確認、指定test、全体回帰、事後health/C:空き。
- 未完了: 最終diff検証、exact stage、commit、commit後確認。
- 開始HEAD: `0709a09c0b1ea56d2877527dc075d428c43e4f8c`
- 開始staging: 0件。
- 開始対象status: clean。
- 開始container: `delta_engine_pro4web-deltaengine_clone-1` — Up 9 hours。
- 開始health: YELLOW。memory 977MBのみYELLOW、sequence gap/reconnect/pipeline/bar flow/latency/tapeはGREEN。
- 開始C:空き: 92,896,055,296 bytes。
- 既存dirty entry: 64件。本タスク外として保持し、broad stageしない。
- 修正後config hash: `c9b2402ad53656525f6f36961132b24583dc4279866cf55a00661b81024ca84d`。
- YAML差分: 指定6 Hookのquantile/value、計12 fieldだけ。
- 全量run開始: 2026-07-30 19:27:57 JST。
- host親PID: 11388、worker PID: 5200/8720。
- priority: 全process `Idle`。
- affinity: 親`12`、worker`4`/`8`。
- 出力JSON: `C:\tmp\stage2c3_le_fix_full_20260730.json`。
- 開始直後health: YELLOW。memory 968MBのみYELLOW、sequence gap/reconnect/pipeline/bar flow/latency/tapeはGREEN。
- 開始直後C:空き: 92,860,682,240 bytes。
- 全量run完了: 2026-07-30 21:53:41 JST、8,740.217秒。
- session: 選択29 / 成功28 / 既知ERROR 1。
- records/candidates: 9,054,572 / 15,667,491。前回と一致。
- 修正6 Hook: 全て10.012706–10.017663%、正常。
- 未変更32 Hook: candidate/eligible/発火数/発火率が前回と完全一致。
- 全38 Hook: 正常37 / 要注意1（D08据え置き）/ 異常0。
- 指定test: 14 passed。
- 全体回帰: 737 passed / 1 skipped / 既存UI selector差分による1 failed。
- 事後health: 負荷直後REDからlatency GREENへ回復。memoryのみYELLOW。
- 事後C:空き: 92,718,620,672 bytes。
- blocker: なし。
- 次の再開位置: 最終diff検証、exact stage、commit、commit後確認。
