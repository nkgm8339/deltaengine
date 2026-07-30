# Stage 2C-4 較正済みHook observe発火解禁レポート
実行日時: 2026-07-30 22:17 JST
実行者: Codex
対象: 較正済み38 Hookのlive HookEvent（OBSERVEのみ）

## 作業境界

- `playbooks.yaml`は`mode: OBSERVE`、`execution_enabled: false`を維持する。
- `hook_thresholds.yaml`のthreshold値は変更しない。
- UNCALIBRATED 11 Hookは`ThresholdBook`のfail-closedを維持する。
- UI、収録データ、完成済みFlow Price Response、3段チャートは変更しない。
- live HookEventは観測・append-only永続化のみとし、Strategy runtimeおよび注文経路へ接続しない。

## Step 1: 発火抑止機構の調査結果

### 1. ThresholdBookのfail-closed

- `src/orderflow/hooks/config.py:254` `ThresholdBook.evaluate`は、Hook IDのentryがない場合、`status != CALIBRATED`の場合、metric不一致、quality不成立、manifest不一致、threshold未通過のすべてで`None`を返す。
- `src/orderflow/hooks/runtime.py:16` `HookRuntime`、同`:42` `submit`は、`ThresholdBook.evaluate`が返した較正済みcandidateだけを`HookEvent`へ変換する。
- 較正済み集合は`ThresholdBook.load(config/hook_thresholds.yaml)`で38件、UNCALIBRATEDは11件だった。threshold config hashは`c9b2402ad53656525f6f36961132b24583dc4279866cf55a00661b81024ca84d`。

### 2. グローバル発火設定

- 作業前の`hook_observer.yaml`にlive HookEvent発火の明示的なglobal flagはなかった。`enabled: true`は既存capture campaignの有効化にも使用され、campaign identityの一部なので変更できない。
- `config/playbooks.yaml`は`mode: OBSERVE`、`execution_enabled: false`、`playbooks: {}`。このファイルは変更していない。
- capture campaign identityを変えずfail-closedを保つため、独立設定`config/hook_live_observer.yaml`を新設した。schemaは`event_firing_enabled`、`mode`、`execution_enabled`、`calibrated_hook_ids`を必須とする。

### 3. live pipeline接続

- 作業前は`webapp/main.py`から`LivePipeline.run_async`が起動されていたが、既存の`HookRuntime`、A/C/D/G detector、`HookEventStorage`への接続がなかった。これが較正済みHookを含む全live発火の主抑止だった。
- 永続化実装自体は`src/observation/hook_storage.py:64` `HookEventStorage`、同`:103` `add_event`として存在していた。
- 最小変更は、既存pipelineの「正規化前trade」「適用済みauthoritative depth」「flow response snapshot」「closed candle」の各境界をobserve-only adapterへ渡すことである。Strategy Engine、playbook実行、注文経路には接続しない。

## Step 2: 解禁のために行った変更

### 設定

- `config/hook_live_observer.yaml`
  - `event_firing_enabled: true`
  - `mode: OBSERVE`
  - `execution_enabled: false`
  - allowlistはA01-A24、C06、D07-D08、G01-G11の正確な38件。
- `config/hook_live_observer.yaml.bak.20260730`
  - 解禁前のfail-closed baselineで、上記との差は`event_firing_enabled: false`だけ。
  - SHA-256: `D7DFBB9A46D529EF0C6E54752A5A01C06E770EBDCB835543C0CC69204F836ABF`
- `config/hook_observer.yaml.bak.20260730`
  - 既存capture設定の作業前backup。
  - SHA-256: `417B1F9D4F5ACFFD080A0855F060A722D1237CCD679A69F3C014DB8A899D6425`
- `config/hook_observer.yaml`、`config/hook_thresholds.yaml`、`config/playbooks.yaml`の最終内容はHEADから変更なし。capture campaign identityとthreshold値を維持した。

### コード

- `src/orderflow/hooks/live.py:45` `STAGE2C4_CALIBRATED_HOOK_IDS`
  - 38件をコード側でも固定し、設定allowlistおよび`ThresholdBook`の較正済み集合と完全一致しない場合は起動しない。
- `src/orderflow/hooks/live.py:57` `LiveHookConfig`、同`:66` `load_live_hook_config`
  - `OBSERVE`以外、`execution_enabled != false`、型不正、未知／不足key、重複Hookをfail-closedで拒否する。
- `src/orderflow/hooks/live.py:111` `LiveHookObserver`
  - 既存のDOM wall/liquidity/quote-motion/iceberg、interaction、flow-transition、price-structure detectorを呼び、`HookRuntime`経由で較正済みHookEventだけをappend-only storageへ渡す。
- `src/pipeline.py:1216`以降
  - `HOOK_LIVE_CONFIG`または`hook_observer.yaml`と同じdirectoryの`hook_live_observer.yaml`を読む。
  - `src/pipeline.py:1305` `notify_hook`がobserver例外をmarket pipelineから隔離する。
  - callback接続はflow response（`:1575`）、closed candle（`:1625`）、applied depth（`:1700`ほか）、raw trade（`:1981`ほか）。
- UI、Flow Price Response、3段チャート、Strategy runtime、execution codeは変更していない。

### container反映

- 未関係dirty sourceを混入させないため、開始HEAD `a404d50`のclean archiveへ本タスクの`src/pipeline.py`と`src/orderflow/hooks/live.py`だけを重ねてbuildした。
- 稼働image: `delta_engine_pro4web-deltaengine_clone:stage2c4-20260730`
- image ID: `sha256:99769af020b3d772a9eebad7b64bf29d8d95f6432fd41fe914e91be544e82f06`
- 最終起動: 2026-07-30 23:01:58 JST、restart count 0。
- 途中の最初の派生imageは旧imageの依存不足で起動できず、次の試行では旧imageと現pipeline APIの不一致でpipeline REDになった。いずれもraw/capture dataは変更していない。最終clean imageでwebapp import smoke test後に再作成し、23:02:14 JST sampleでhealth GREENを確認した。

## Step 3: live発火の観測結果

- HookEvent session: `session-20260730T140203.429173Z-2f5d27bf`
- 観測窓: 2026-07-30 23:02:03.429 JST ～ 23:07:38 JST（5分34.571秒）
- 最初のevent: 23:02:09.793 JST
- 観測窓内最後のevent: 23:07:37.952607 JST
- 読み取ったParquet part: 72、read failure: 0
- 合計HookEvent: 3,563

| Hook ID | 発火数 |
|---|---:|
| A01 | 89 |
| A02 | 222 |
| A03 | 109 |
| A04 | 90 |
| A05 | 252 |
| A06 | 258 |
| A07 | 262 |
| A08 | 293 |
| A09 | 66 |
| A10 | 343 |
| A11 | 21 |
| A12 | 9 |
| A13 | 9 |
| A14 | 21 |
| A15 | 18 |
| A16 | 11 |
| A17 | 67 |
| A18 | 436 |
| A19 | 0 |
| A20 | 0 |
| A21 | 361 |
| A22 | 309 |
| A23 | 16 |
| A24 | 28 |
| C06 | 250 |
| D07 | 0 |
| D08 | 15 |
| G01 | 0 |
| G02 | 1 |
| G03 | 0 |
| G04 | 2 |
| G05 | 0 |
| G06 | 0 |
| G07 | 1 |
| G08 | 0 |
| G09 | 3 |
| G10 | 0 |
| G11 | 1 |

UNCALIBRATED 11件（C03、C04、C05、C07、C08、D06、F01-F05）は全件0。38件allowlist外の予期しないHook IDも0だった。

観測終了時healthはYELLOW。sequence gap 1件、WS reconnect 1件がYELLOWで、pipeline、bar flow、latency、memory、tapeはGREENだった。23:10:24 JSTの事後sampleではpipelineは引き続きGREEN、gap/reconnect各1件とlatency 7,584msがYELLOWだった。23:10時点のcontainer瞬間CPUは99.38%、memoryは464.6MiB / 3.708GiB。thresholdや発火設定は変更せず、実測値として記録する。

## Step 4: 事後確認結果

- 起動時health: GREEN（2026-07-30 23:02:14 JST sample）。全check GREEN、pipeline exception 0、latency 180ms、memory 235MB。
- 事後health: YELLOW（2026-07-30 23:10:24 JST sample）。pipeline GREEN、上記gap/reconnect/latencyのみYELLOW。
- container: `delta_engine_pro4web-deltaengine_clone-1`、Up、restart count 0。
- C:空き: 92,692,930,560 bytes。
- liquidation:
  - campaign: `stage2a_20260726_xz`
  - 新session: `session-20260730T140201.347728Z-7ba519d5`
  - `accepting: true`
  - pending 0、dropped_queue_full 0、rejected_disk_low 0、writer_error null
  - 10秒間隔の`COVERAGE_HEARTBEAT`が継続している。
- full stream: `/api/stats`のactive streamにはliquidationだけが存在し、deadline通過済みfull streamの継続収録はない。
- playbooks: `mode: OBSERVE`、`execution_enabled: false`、`playbooks: {}`。
- `hook_thresholds.yaml`: HEADから差分なし。CALIBRATED 38件、UNCALIBRATED 11件。
- observer error log: 0行。storage queue full、writer_error、callback failure、runtime start failureはいずれもなし。

## テスト

- Stage 2C-4固有／live pipeline:
  - `python -m pytest tests/orderflow/test_stage2c4_live_hooks.py tests/test_live_pipeline.py -q`
  - 22 passed in 8.96s
- 指定detector test:
  - `python -m pytest tests/orderflow/test_stage2b_dom_detectors.py tests/orderflow/test_stage2b_context_detectors.py -q`
  - 14 passed in 0.36s
- 全体回帰:
  - `python -m pytest -q -p no:cacheprovider`
  - 765 passed、1 skipped、1 failed in 169.07s
  - failure: `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
  - 期待CSS selector `body.phase5-fusion #right>#left{display:none!important}`が、作業前からdirtyだった`webapp/static/index.html`に存在しない既知のUI差分。本タスクはUI変更禁止のため修正していない。Stage 2C-4の設定／runtime／pipeline testはpass。

## 変更ファイル

- `config/hook_live_observer.yaml`
- `config/hook_live_observer.yaml.bak.20260730`
- `config/hook_observer.yaml.bak.20260730`
- `src/orderflow/hooks/live.py`
- `src/pipeline.py`
- `tests/orderflow/test_stage2c4_live_hooks.py`
- `tests/test_live_pipeline.py`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_STAGE2C4_OBSERVE_FIRE_REPORT_20260730.md`

`hook_observer.yaml`、`hook_thresholds.yaml`、`playbooks.yaml`、UI、収録データに最終task差分はない。

## 作業checkpoint

- checkpoint日時: 2026-07-30 22:17 JST
- 承認範囲: 較正済み38 Hookだけのobserve発火解禁、必要な最小設定／コード、設定バックアップ、container反映、5分以上のlive観測、指定test、レポート、指定commit。
- 開始HEAD: `a404d508833877d1ff5264f683f7000ceaa33d52`
- 開始staging: 0件。
- 開始dirty entry: 33件。本タスク外変更として保持し、broad stageしない。
- 開始container: `delta_engine_pro4web-deltaengine_clone-1` — Up 13 hours。
- 開始health: YELLOW。latency 2,727msとmemory 1,053MBがYELLOW。sequence gap／reconnect／pipeline／bar flow／tapeはGREEN。
- 開始C:空き: 92,709,978,112 bytes。
- `PROJECT_MEMORY.md`: 全1192行再読済み。SHA-256 `C5084355120DB3B1F831D2110613DC4785F02821B4F31760107CE082998C9D98`。
- 完了済み: preflight、Hook設定／runtime／live起動の初期横断調査。
- 確認済み主抑止: `webapp/main.py`はcaptureだけを起動し、`HookRuntime`／detector／`HookEventStorage`をlive pipelineへ接続していない。
- 未完了: 詳細設計、バックアップ、実装、静的検証、container反映、5分観測、事後確認、test、最終差分、commit。
- 既存dirty注意: `docker-compose.yml`、Heatmap関連を含む。本タスクでは上書き・stageしない。
- blocker: なし。
- 次の再開位置: A/C/D/G detectorの既存較正runnerとlive pipeline event境界を照合し、最小のobserve-only接続を設計する。

### 変更反映前checkpoint

- checkpoint日時: 2026-07-30 22:46 JST
- 完了済み: 抑止機構調査、設定バックアップ、38 Hook限定live observer実装、pipeline接続、設定／runtime／pipelineの個別試験。
- 変更file: `config/hook_observer.yaml`、`config/hook_observer.yaml.bak.20260730`、`src/orderflow/hooks/config.py`、`src/orderflow/hooks/live.py`、`src/pipeline.py`、`tests/orderflow/test_hook_contract.py`、`tests/orderflow/test_stage2c4_live_hooks.py`、`tests/test_live_pipeline.py`、本レポート。
- 検証結果: task固有試験27件pass（9.58秒）、指定detector試験14件pass（0.19秒）、`ThresholdBook`はCALIBRATED 38件／UNCALIBRATED 11件を確認、task差分の`git diff --check` pass。
- 設定backup SHA-256: `417B1F9D4F5ACFFD080A0855F060A722D1237CCD679A69F3C014DB8A899D6425`。
- container反映方式: 稼働イメージ`sha256:3d1d1e...`を基底にtaskの3ソースだけを重ねた派生イメージ`delta_engine_pro4web-deltaengine_clone:stage2c4-20260730`（image ID `sha256:ca003910...`）を使用する。既存dirty sourceはイメージへ含めない。
- 未完了: container再作成、health確認、5分以上のlive観測、全体回帰、事後確認、レポート確定、commit。
- blocker: なし。初回派生image buildはimage IDの解釈によりregistry認証エラーとなったが、container／dataは未変更。local base tagで再build済み。
- 次の再開位置: compose overrideと`--no-build`でcontainerを再作成し、healthとobserver起動ログを確認する。

### commit前checkpoint

- checkpoint日時: 2026-07-30 23:11 JST
- 完了済み: 独立observe設定への切り分け、capture identity復元、clean image build/import smoke、container最終再作成、health GREEN確認、5分34.571秒live観測、Hook別集計、UNCALIBRATEDゼロ確認、liquidation継続確認、指定test、全体回帰、事後状態、レポート。
- 最終変更file: `config/hook_live_observer.yaml`、同backup、`config/hook_observer.yaml.bak.20260730`、`src/orderflow/hooks/live.py`、`src/pipeline.py`、`tests/orderflow/test_stage2c4_live_hooks.py`、`tests/test_live_pipeline.py`、本レポート。
- 検証結果: Stage 2C-4固有22件pass、指定detector 14件pass、全体765 pass／1 skip／既知UI 1 fail。live 3,563 events、UNCALIBRATED全0、observer error 0。
- blockerの限定範囲: 全体回帰の既知UI selector 1 failureのみ。UI変更禁止のため本タスクでは扱わない。Hook／pipeline testとlive稼働を妨げない。
- 未完了: exact staging、指定commit、commit後確認。
- 次の再開位置: task対象8fileだけをexact stageし、cached diffを検証して指定messageでcommitする。
