# Heatmapライン 引き継ぎ書(統括交代用)
**作成日: 2026-07-30 / 作成者: 統括(Claude web、本セッション) / 宛先: 次期統括セッション**

---

## 1. 体制と役割

- お館様: 最終意思決定者。統括はお館様の部下であり、Codexへの指示はすべて
  「指示文案を用意しお館様の裁可を得て、お館様がCodexへ渡す」形式を取る。
  統括がお館様に作業を割り振る物言いは厳禁(本セッションで一度叱責を受けた)。
- 統括(Claude web): 検証・指示書作成。すべての主張はファイル:行番号または実物SHA-256で
  根拠を示す。Codexの自己申告のみを根拠に承認しない。実物を受領して独立検算する。
- Codex(Claude Code): 実装。CLAUDE.md記載の統制ルール(停止条件・Task単位停止・
  報告フォーマット)に従い、Task完了ごとに停止して個別承認を待つ運用が確立している。

## 2. 統制文書の現況

- **正本: HEATMAP_指示書_v1.5.md**(リポジトリにコミット済み。`f0390eb`に含まれる)。
- **v1.6は未確定**。本セッションで一度作成したが、v1.5の既存記載(Phase 0/1/2-0完了記録)を
  統括判断で圧縮したためお館様が却下(「書き直せ」)。旧v1.6は破棄済み。
  **次期統括への指示: v1.6はv1.5本文を一切改変せず、追記のみで作成すること。**
  追記すべき内容は本書§4・§5に全て記載してある。

## 3. リポジトリ現況(2026-07-30時点、すべて実報告で確定)

- パス: `C:\Users\user\Desktop\DeltaEngine05M`(旧`DeltaEngine`から変更されている)
- HEAD: `f0390eb68a93b5289f22c3a8fadfa588e7c4660f`
- 直近履歴: `e358a0f`(Phase 1最終)→ Hookライン`bffe6f5`→`0709a09`→
  `a47f21a`(Phase 2-0-d、11ファイル)→ `f0390eb`(Phase 2-1、38ファイル)
- 全pytestベースライン: **1 failed / 737 passed / 1 skipped**。
  唯一のfailは既知の`tests/webapp/test_dom_tape_fusion_ui.py`(Phase 5 UI契約、本ライン無関係)。
  新規fail 0が承認基準。
- 未コミット残存(意図的): tracked 10件 = [X]他ライン6件
  (ORDER_BOOK_HEATMAP旧文書2、WebSocketPayload_Spec、hook_thresholds.yaml、
  push_broker.py、time_sales.js)+ [P]保護対象4件(webapp/main.py、docker-compose.yml、
  tests/webapp/test_book_update.py、webapp/static/index.html)。
  untracked残存はp21_evidence(57)、Task 0保全証拠(2)、VWAP(14)、Hook文書(7)、実データ(9)。
- 復元担保: `ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch`
  SHA-256 `E3DE49359AFC63117433DDF9B8183CA2C4B0AE2C6E21ADE08963EF14997C1B70`
  (108,960 byte / 2,413行 / tracked 16 section)。

## 4. Phase 2-1 完了内容(v1.6追記用素材)

**状態: 実装・検証・コミット完了。実質クローズ。**

### 実装物(すべて新規、既存ファイル変更ゼロ、`f0390eb`にコミット済み)
- `Delta_Engine_Pro4web/src/heatmap/__init__.py`(空、SHA-256 01BA4719...)
- `Delta_Engine_Pro4web/src/heatmap/reconstruct.py`
  (20,394 byte / LF 573行 / SHA-256 `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`)
  クラス: `DepthHistoryReader` / `DepthReconstructor` / `ReconstructionEvent` /
  `SegmentInfo` / `SegmentIntegrityError`
- `tests/heatmap/test_reconstruct.py`(14,290 byte / 501行 / SHA-256 0C2D734F...)。10 passed
- `tests/heatmap/fixtures/make_real_fixture.py` + `real_validation/`縮約fixture
  (JSONL 2本: SHA-256 FC947A96... / 2E79BA05...。provenanceに元セグメントSHA-256を記録:
  58048404... / 1AAF0643...)
- `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py`
  (4,987 byte / 156行 / SHA-256 84C15DFB...)

### 設計契約(統括が実物コードで全経路検証済み)
- 既存`DepthSyncCoordinator`(src/acquisition/depth_sync.py、I/O非依存の純粋state machine)と
  `OrderBookStateManager`(src/orderflow/orderbook.py:97)を無改造で流用。
- **固定適用手順**: Coordinator verified → `apply(SNAPSHOT)` →
  `apply_initial_sync(snapshot_u)` → verified bridge以降のdiffs順次適用。
  lenient分岐(orderbook.py:236-243)に入るのはCoordinator検証済みbridgeのみ。
  未検証diffがbookへ入る経路は存在しない(統括がreconstruct.py全経路を読んで確認)。
- Decimal文字列変換のみ、float再帰拒否、bool偽装int拒否。
  manifest三重照合(byte_size/record_count/SHA-256)。`.part`とmanifest欠如はskip記録。
- SYNCED後のgap → `start_resync` → 録画内後続snapshotで再同期。SYNC_FAILED後のdepthは
  `diffs_discarded_after_fail`計数。tradeは`trades_skipped`計数のみ。
- 出力主契約: `sample_states(records, interval_ms)` → `(sample_time_ms, OrderBookSnapshot)`。
  event-time基準で厳密単調増加。GAP/SYNC_FAILED跨ぎでサンプル時刻リセット
  (欠損区間を描画で埋めない)。

### 検証確定値(統括がp21_evidence実物で独立検算した値。次期統括はこれを事実として使ってよい)
- 検証録画: `data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT/`
  34セグメント/28,084行。manifestは各セグメント隣接の`<name>.manifest.json`。
- 先頭2セグメント: snapshot_u=`11165393552876`、bridge U=`11165393550921` /
  u=`11165393566438`、`U <= snapshot_u+1 <= u`成立、bridgeから135 depthのpuチェーン全PASS、
  pre-sync depth 1件(非適用)、snapshot 1000段×両面、価格は全て文字列。
- 34セグメント全量CLI: integrity PASS / SNAPSHOT_APPLIED 1 / DIFF_APPLIED 2938 /
  GAP 0 / RESYNC 0 / SYNC_FAILED 0 / trades_skipped 25144 / samples 300 /
  final_last_update_id `11165441170516` / elapsed 32191ms。
  **勘定: 1+2938+1+25144=28,084 で録画実測と完全一致(黙殺ゼロの証明)**。

### 実行経緯(Task 0〜5、全Task統括検証済み・承認済み)
- Task 0 証拠保全 → Task 1 N1/N2実装 → Task 2 fixture → Task 3 テスト(10 passed) →
  Task 4 CLI+全pytest(737/1/1)+34セグ実行 → Task 5 3点セット提出
  (CompletionLog.md追記は承認済み例外)。
- 完全ZIP: `HEATMAP/Phase_2-1_Reconstructor_complete_20260730.zip`
  (211,688 byte / 14エントリ / SHA-256 `74CBFB4B8B30700C766CCB54751717B7908FC4D212C860AEE60EAA341FAFD7D3`)。
  **統括による実物照合は未実施**。コミット済みのため必須ではなくなったが、
  お館様が照合を望む場合はZIPを受領して inventory 全件突き合わせを行うこと。
- 途中、報告書の行数計測不一致(495 vs 実物LF 573)を検出→byte/SHA正、LF基準で訂正済み。

## 5. コミットチェックポイント完了内容(v1.6追記用素材)

2段階承認制で実施・完了。
- Stage A: tracked 18件を[H]8/[X]6/[P]4に分類(分類不能0、迷えば[X]の保守則)。
  untrackedはH候補41/H明示除外57/X32。CompletionLog.mdは実物diff確認
  (Phase 2-1エントリ1件・59行のみ)を条件にH承認。
- Stage B: 49ファイルを個別パスaddで2コミット
  (`a47f21a`: 2789+/237- 、`f0390eb`: 10908+)。Hook `0709a09`上に積載。
  push/branch/rebase/amendなし。コミット後pytest 737/1/1維持、残存差分の勘定が閉じることを確認。

## 6. 未完了事項と次の一手(優先順)

1. **指示書v1.6の確定**(§2の条件で書き直し。お館様の承認を得て確定)
2. **Phase 2-2(描画器設計)指示書の作成**。着手前提:
   - 入力は§4の`sample_states`契約。records取得は`DepthHistoryReader(dir).iter_records()`
   - ダウンサンプリング(価格ビン集約・時間間引き)必須。描画テストは価格ビン50×時間100程度、
     フルサイズは成果物確認時のみ(統制ルール)
   - 既存の失敗を繰り返さない: x座標-185.25pxバグ(座標変換テスト化)、
     p95描画予算16ms超過(描画時間ログ必須化)
   - OrderBookSnapshotのbids/asks並び順は実物(orderbook.py)で確認してから仕様化すること
   - 保護対象4ファイル(特にindex.htmlの別系統Heatmap UI差分)に触れる必要が出たら停止・確認
3. Phase 2-1完全ZIPの実物照合(任意、お館様の指示があれば)
4. 未判断事項(継続): 常時記録の恒久有効化 / 残置fail `test_dom_tape_fusion_ui.py`(Phase 5側) /
  G07/G08分布調査等のHookライン事項は本ライン外

## 7. 本セッションでの失敗と教訓(次期統括は繰り返すな)

1. **お館様への責任転嫁と映る物言い**: 「どの進め方にしますか」「Codexへお伝えください」等、
   判断や伝達をお館様に投げる書き方で二度叱責を受けた。技術判断は統括が責任を持って下し、
   指示文案を用意して裁可を仰ぐ。選択肢の羅列で止まらない。
2. **統制文書の勝手な圧縮**: v1.6作成時にv1.5の完了記録を無断で要約・圧縮して却下された。
   統制文書の既存記載は不可侵。更新は追記のみ。
3. **消極的に見える留保**: ZIP照合の実益低下を先に述べて「省略も可」と提示し、
   やる気がないと受け取られた。やる価値の説明より先に手を動かす。
4. **ファイル納品の確実性**: 日本語ファイル名でダウンロードリンク不全が一度発生。
   納品はASCIIファイル名を併用し、SHA-256を添える。
5. **他ライン混在への警戒は正当だった**: 同一worktreeでHook較正が並走し、tracked差分数が
   16→17→18と変動した。差分数の変動を検出したら必ず出所を確定してから承認する。
   この慎重さは維持すること。

## 8. 参照物の所在

- 統制文書: `ArchitectureRepository/00_Master/HEATMAP_指示書_v1.5.md`(コミット済み)
- Phase 2-1指示書: `ArchitectureRepository/00_Master/Instruction_Phase2-1_Reconstructor_v1.md`
- 実装報告書: `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_板state再構築器実装報告.md`
  (Task 0〜5の全checkpoint、SHA-256 6BB4821C...)
- SHA-256 inventory: `HEATMAP/Phase_2-1_SHA256_INVENTORY_20260730.txt`(SHA-256 2A046971...)
- コミットチェックポイント指示書: 本チャット納品物
  `Instruction_Heatmap_Commit_Checkpoint_v1.md`(リポジトリ格納は未確認)
- CompletionLog: `ArchitectureRepository/00_Master/CompletionLog.md`(Phase 2-1エントリ追記済み)
- p21_evidence: `HEATMAP/p21_evidence/`(コミット外、実物検証の根拠一式)

以上。次期統括は本書と実物(v1.5、実装報告書、p21_evidence)を根拠とし、
本書の記憶的記述と実物が食い違う場合は実物を正とすること。
