# LIVE DOM 完全修復方法調査 checkpoint

- 更新時刻: 2026-08-04 10:53:53 +09:00
- 対象リポジトリ: `DeltaEngine05M`
- 承認範囲: 完全修復方法の特定、既存証拠とsourceの読み取り、報告書作成
- 非承認／非変更範囲: 製品source、protected、timeout値、UI freshness、runtime、container、image、設定値
- Git制約: `git add`、`git commit`、`git push`を実行しない

## 完了済み

- `PROJECT_MEMORY.md`全文確認（同一セッション内）
- Stage 2B-1 runtime soakとLIVE DOM停止事象の既存証拠を保全
- 調査・報告だけを行う作業境界を確定

## 未完了

- 正常時と故障時のpipeline／depth同期経路の照合
- 完全修復仕様の確定
- 回帰テスト、runtime検証、合格条件の確定
- 最終報告書の作成と整合性確認

## 変更file

- `ArchitectureRepository/00_Master/LIVE_DOM_COMPLETE_REPAIR_ANALYSIS_CHECKPOINT_20260804.md`（本checkpointのみ）

## 検証結果

- 未実施（調査開始前）

## blocker

- なし

## 次の再開位置

- `src/pipeline.py`、`src/acquisition/depth_sync.py`、関連テスト、soak／incident証拠を読み取り、故障経路と修復案を照合する。

## 電源断前 checkpoint

- 更新時刻: 2026-08-04T02:25:43.447Z（JST換算は再開時に確認）
- 中断理由: ユーザーがPCの電源を落とすため。
- 製品source／runtime／container／image変更: 0
- 今回追加した変更: 本checkpointのみ
- Git操作: `git add` / `commit` / `push` 0

### 確定済み

- LIVE DOM停止はbrowser／Footprint JSではなく、backendのBook同期停止。
- 実ログは `depth pu chain discontinuity after bridge` → 同じ破損bufferで3回retry → `SYNC_FAILED` を示す。
- `pipeline.py`ではreceiver coroutineとmain consumer coroutineが同じ`DepthSyncCoordinator`を直接変更している。
- Stage 2B-1のyieldにより、receiverが新しいdepthを先にprebufferし、その後main consumerがqueue内の古いdepthを同buffer末尾へ追加できる。
- 決定論的診断で `previous_u=109 / current_pu=105` の逆転を再現し、buffer 5件を保持したまま3/3で`SYNC_FAILED`になることを確認した。
- ADR-003はcoroutine間のmutable state直接共有を禁止しており、現行depth同期配線はこの契約に反する。
- `rollback-pre-footprint-20260728` imageは名前どおりpre-Footprintで、Footprint/Tape/Book projectionを欠くため完全復旧baselineには使えない。

### 未完了

- 正常baseline imageの最終選定。
- depth同期の単一owner化、破損buffer再利用禁止、fail-closed後の再armを含む恒久修復仕様の確定。
- 必須test matrixとruntime合格条件の確定。
- 最終報告書作成。

### 再開位置

- Phase 2-0-d-1のreceiver prebuffer契約とADR-003の矛盾を踏まえ、`src/pipeline.py`と`src/acquisition/depth_sync.py`の具体的変更仕様を確定する。
- 報告書作成までで停止し、source修正・rollback・container操作は別の明示承認を待つ。

## 最終調査完了 checkpoint

- 更新時刻: 2026-08-04 18:00:08 +09:00
- 承認範囲: 完全修復方法の特定、既存証拠とsourceの読み取り、報告書作成
- 製品source／runtime／container／image変更: 0
- Git操作: `git add` / `git commit` / `git push` 0

### 完了済み

- `src/pipeline.py`、`src/acquisition/depth_sync.py`、DataReceiver、queue、history recorder、
  offline Heatmap reconstructor、関連test、ADR-003、Phase 2-0-d-1正本を照合。
- coordinatorの二重owner、Stage 2B-1 yieldでのbuffer順序逆転、破損bufferの3回再利用、
  terminal後requestなしをsourceと決定論的診断で確認。
- 5件bufferの`previous_u=109 / current_pu=105`を現行sourceで再現し、
  attempt 1→2→3の全てでbuffered_count 5、最後はSYNC_FAILED、後続depthでもrequestなしを確認。
- 完全修復仕様を次の3本に確定。
  1. main consumerによるcoordinator単一owner化
  2. `pu`不連続時のsnapshot＋buffer破棄後fresh retry
  3. terminal後の次valid depthによる明示rearm／新epoch
- 必須test matrix、runtime合格条件、停止条件、rollback境界を確定。
- 正本baselineをStage 2B-1 host source＋pin済みimage
  `sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c`
  に確定。
- 最終報告書を作成:
  `ArchitectureRepository/00_Master/LIVE_DOM_COMPLETE_REPAIR_ANALYSIS_REPORT_20260804.md`

### 検証結果

- 現行`src/pipeline.py` SHA:
  `7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae`
- 現行`src/acquisition/depth_sync.py` SHA:
  `131b0b773712e983179789316e8562dddc41b7330d8df23330ff5b871debb576`
- 決定論的診断: 再現PASS（故障契約を期待どおり再現）。製品source変更0。
- 18:00 JST read-only runtime sample: current bookはSYNCEDへ復帰しているが、health RED、
  直近に上流DNS/timeout。既知source defectが残るため完全正常とは判定しない。

### 未完了

- 製品source/testの実装
- regression
- candidate image build
- deployment／runtime soak
- 新しい正常baseline imageの確立

### blockerの限定範囲

- source/test/image/runtime変更の明示承認待ちだけ。
- 調査と修復仕様確定はblockされていないため完了。

### 次の再開位置

- ユーザー／統括が最終報告書を確認し、製品source・test変更の明示GOを出す地点。
- GO後は対象4fileの開始SHA・EOL・protected hash checkpointを作成し、
  coordinator単体testから実装する。

## 追加観測: Freshness瞬断とLIVE DOM再同期再発

- 観測時刻: 2026-08-04 19:41 JST前後
- 現container: `1ebe7a72fc3d8323e13c7be7d7c7efc16fac8f8ad73b7922c2d288aec85a3bf5`
- 現image: `sha256:bed8a0cabd894c62ecce06eea4c6d8752584997840c1dbcd9fe4522469c0e9f7`

### 確定事項

- `/api/health`: `YELLOW`、book gap 1、pipeline exception 0、Tape drop 0。
- `/api/stats`: `book_synced=false`、`book_projection_state=RESYNCING`、`book_resyncs=0`。
- container logで同じ失敗が大量反復:
  `depth sync attempt limit reached (3/3): depth pu chain discontinuity after bridge`
  （同一`buffer_index=605`、`previous_u=11208266447207`、`current_pu=11208247740551`）。
- これは既存checkpointで確定済みのreceiver prebuffer／main consumer順序逆転と同一系統であり、
  LIVE DOM backendの再同期失敗が現在も再発している直接証拠である。
- 赤帯の`WAITING_FOR_FRESH_TICK`はLIVE DOM状態文字列ではなく、frontend
  `MarketHeartbeatGuard`の状態。heartbeat timeout／upstream freshness喪失後、heartbeatが戻っても
  新規TICK受信まで`SYNCING`に留まり、TICK受信で`LIVE`（緑）へ戻る。
- 画像時刻帯の後続ログには`E2001 stream error: ... no close frame received or sent`
  （10:23:33Z）、続いてDNS失敗（10:23:39Z）がある。Binance upstream断・再接続が
  Freshnessの赤→緑フリップを説明する。
- 15秒の実WebSocket観測ではheartbeat 14件、TICK 45件、全heartbeat
  `upstreamFresh=true / pipelineAlive=true`で、その観測窓では正常だった。

### 切り分け

1. 上段の赤帯: Binance streamの瞬断／再接続に伴うFreshness安全停止。
2. LIVE DOM: `pu`不連続bufferを3回再利用して`SYNC_FAILED`へ固定するbackend不具合。
3. 両者は同じ上流stream障害を契機に同時発生し得るが、別state／別修復箇所である。

製品source、runtime、container、imageはこの追加観測でも変更していない。

## 修復実装GO checkpoint

- GO受領時刻: 2026-08-04 20:26:22 +09:00
- 承認範囲: LIVE DOM恒久修正のsource/test実装とローカル回帰
- 未承認範囲: image build、container restart、runtime deployment、production soak、Git commit/push
- 変更対象予定: `src/acquisition/depth_sync.py`、`src/pipeline.py`、
  `tests/acquisition/test_depth_sync.py`、`tests/test_live_pipeline.py`
- 保護対象: `receiver.py`、`depth_history_recorder.py`、`heatmap/reconstruct.py`、
  `orderbook.py`、webapp/frontend、timeout、Flow Price Response、3段チャート、Footprint、Tape

### 開始SHA / EOL

```text
src/pipeline.py                    7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae
src/acquisition/depth_sync.py      131b0b773712e983179789316e8562dddc41b7330d8df23330ff5b871debb576
tests/acquisition/test_depth_sync.py 7398261143ef1bedabfde4050874742f03c62a2b8daf73514881df5076849f2f
tests/test_live_pipeline.py        bb9552c5c8970667ad8d393c83ad7c623a2fcef6f9e3bb9c99e77ff7655c0348
pipeline.py EOL                    CRLF 1336 / LF-only 877
```

### 次の再開位置

- coordinatorの破損buffer破棄、terminal後rearmを実装。
- receiver callbackによるcoordinator直接変更をproduction pipeline配線から除去し、
  main consumer単一ownerへ統合。
- coordinator単体test、live pipeline test、関連回帰を実行。
- 失敗時はsource変更を追加せずcheckpointへ停止理由を記録する。

## 2026-08-04 20:41 JST — 実装・対象回帰完了

### 承認範囲

- `じゃおGO` および `codex --approval-mode auto` により、source/testの実装・検証を実施。
- image build、runtime restart、deploy、commit、pushは未実施。

### 完了済み

- `src/acquisition/depth_sync.py`: pu chain discontinuity時に破損bufferを破棄。terminal failure後のfresh depthによる `rearm_after_failure()` を追加。
- `src/pipeline.py`: production配線からreceiver callbackのcoordinator直接更新を除去し、main consumerを唯一のmutable-state ownerに統一。
- coordinator/live pipelineの回帰テストを追加。

### 検証結果

- 対象テスト: `74 passed`。
- 追加回帰: `65 passed`。
- `py_compile`: 成功。
- `git diff --check`: 成功。
- 全体pytestは実行ハーネスの125秒制限で終了（テスト失敗結果ではなく、完走結果は未確定）。

### 次の再開位置

- 必要なら承認を得てimage build → runtime restart/deploy → LIVE DOMで赤→緑の再発監視。

## 2026-08-04 21:00 JST — runtime反映・初回確認

- `docker compose build deltaengine_clone`: 成功。
- `docker compose up -d --force-recreate deltaengine_clone`: 成功。
- `/api/health`: `GREEN`、sequence_gap=0、pipeline exceptions=0、ws_reconnect=0。
- `/api/stats`: `book_synced=true`、`book_projection_state=SYNCED`、book_snapshots_applied=1、book_diffs_applied=1346、book_gaps_detected=0。
- 再起動後2分ログに `depth sync attempt limit reached`、`SYNC_FAILED`、`chain discontinuity` はなし。
- tape accountingも `balanced=true`、dropped=0。

### 残課題

- WebSocket heartbeatの追加観測コマンドはshell inline構文エラーで未取得。ただしhealthとstats、同期失敗ログ確認は完了。
