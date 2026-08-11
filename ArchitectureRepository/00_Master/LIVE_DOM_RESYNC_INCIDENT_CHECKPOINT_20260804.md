# DeltaEngine05M — LIVE DOM RESYNCING incident checkpoint

作成日: 2026-08-04 10:35 JST  
対象repository: `C:\Users\user\Desktop\DeltaEngine05M`

## 復旧操作前

- ユーザー申告: `live domが一切反応しない！！！！`
- 現container: `ccbb420a6ecbb739d9977e3545849e3778eb9c99a3a28fcbac64a5b09807b65a`
- 現image: `sha256:2b598c055e26401511bc448b1abe14e3c503760cc946f550f6bacf54a954394d`
- container作成: 2026-08-04 09:51:12 JST。base composeだけから再作成されており、09:44時点のStage 2B-1 exact restore containerとは別物。
- source/config/protected 10件SHAはStage 2B-1正本値と一致。
- API全体healthはGREENだが、`/api/stats`は`book_synced=false`、`book_projection_state=RESYNCING`、book gap 1。
- 15秒WebSocket直接観測: Tape 82 update、BOOK_UPDATE 1件だけ、状態`RESYNCING`。browser固有でなくbackend板供給停止。
- container logの反復エラー:
  - `depth synchronization failed closed`
  - `depth sync attempt limit reached (3/3)`
  - `depth pu chain discontinuity after bridge (buffer_index=479, previous_u=11205439006325, current_pu=11205408863033)`
- 原因判定: depth snapshot＋buffered diffの同期が不連続でfail closedし、同期済み板投影を送れないためLIVE DOMが停止。
- 承認範囲: 現image/source/configを変更せず、現containerをrestartして新しいsnapshot＋diffから再同期するoperational recovery。
- 変更file: 本checkpointのみ。source本体、protected、timeout、UI freshnessは未変更。
- 未完了: container restart、readiness、30秒BOOK連続更新・全SYNCED、最終health確認。
- blockerの限定範囲: LIVE DOM板供給だけ。Tape、trade、pipelineは稼働中。
- 次の再開位置: current containerをrestartし、book_syncedとWebSocket BOOK_UPDATEを直接測定する。

## restart結果と再発

- current imageを変更せずcontainer restartを実施した。
- restart直後readiness PASS。
- 続く30秒直接測定:
  - BOOK_UPDATE 190件
  - sequence 78→267
  - 非SYNCED 0
  - gap 0
  - max受信間隔1,055.364ms
  - `book_synced=true / book_projection_state=SYNCED`
  - Tape dropped 0 / send failure 0 / balanced true
- しかし約1分後に再発:
  - `book_synced=false`
  - `book_projection_state=RESYNCING`
  - gap 1
  - fail-closed BOOK_UPDATE 3件
  - API health RED（event lag 27,569ms）
- 結論: restartは一時復旧だけで恒久解決ではない。

## source根本原因

- `src/acquisition/depth_sync.py::_verify_candidate()`はbridge後の`pu`不連続を検出すると`_reject_candidate()`へ入る。
- `_reject_candidate()`は`_snapshot`だけを捨て、破損した`_buffer`を保持したままattemptを増やす。
- そのため再取得したsnapshot候補も同じ不連続bufferの同じindexで失敗する。
- attempt 3/3後は`SYNC_FAILED`へ入る。
- `observe_depth()`は`SYNC_FAILED`中に新規depthを受けてもfailure actionを返すだけで、新snapshot requestを発行しない。
- pipelineは同じfailureをlogし続けるが、同期を再armしない。したがってBook projectionとLIVE DOMが永久に止まる。

## 恒久修正候補（未承認・未実装）

1. `pu` chain discontinuityを検出したcandidateのbufferをbookへ一切適用せず破棄する。
2. 次attemptを空のbufferからfresh depthで再armし、新snapshotとのstrict bridgeを作り直す。
3. 古い破損bufferが次attemptへ再利用されないこと、新しい連続diffだけでSYNCEDへ復帰することを専用testで固定する。
4. 既存のsnapshot-too-old／fetch failure retry契約は変えず、`pu`不連続だけを限定修正する。
5. source/test/image/runtimeを明示承認後に変更し、実WebSocketで継続SYNCEDを検証する。

- 未完了: 恒久source修正、test、image build、deployment、runtime継続検証。
- blockerの限定範囲: 元指示の「source本体を変更しない」境界。解除の明示指示が必要。
- 現runtime: LIVE DOMは再度RESYNCINGで停止中。Tape等のtrade経路は継続。
- Git操作: `git add` / `commit` / `push` 0。
