# DeltaEngine05M — LIVE DOM 完全修復方法調査報告

- 作成時刻: 2026-08-04 18:00 JST
- 対象repository: `C:\Users\user\Desktop\DeltaEngine05M`
- 判定: **調査完了 / 修復仕様確定 / 製品実装は未承認・未実施**
- 本作業の変更: 本報告書と調査checkpointだけ
- Git操作: `git add` / `git commit` / `git push` 0

## 0. 結論

LIVE DOM停止の完全修復には、次の3項目を一体で実施する必要がある。

1. `DepthSyncCoordinator`のmutable stateを`LivePipeline.run_async()`のmain consumerだけが更新する。
2. bridge後の`pu`不連続はsnapshot候補だけの失敗ではなくbuffer汚染として扱い、次attemptへ入る前にbufferを破棄する。
3. attempt上限の`SYNC_FAILED`後も板だけをfail-closedのまま保ち、次の有効depthから新epochを明示的に再armできるようにする。

restart、timeout緩和、Stage 2B-1 chunk化の撤去、snapshotだけの再取得では完全修復にならない。
前二者は原因を残し、chunk撤去はRealtime UI Freshnessの改善を戻す。timeout値は本件の順序逆転と無関係である。

## 1. 確認済みの故障経路

### 1.1 二重owner

現行`src/pipeline.py`では、同じcoordinatorを二つのcoroutine経路が直接変更する。

```text
DataReceiver.run()
  -> on_valid_message=notify_depth_sync
  -> depth_sync.observe_depth(message)

LivePipeline.run_async() main consumer
  -> process_live_depth(raw)
  -> depth_sync.observe_depth(raw) / start_resync(raw)
  -> observe_snapshot(...)
```

これはADR-003の「coroutine間でmutable stateを直接共有しない」という契約に反する。
板本体の`OrderBookStateManager`がmain consumer単一ownerでも、板へ入る前の同期bufferが二重ownerなら
strict順序は保証できない。

### 1.2 Stage 2B-1 yieldで顕在化する逆転

通常同期中にmain consumerがgap diffを処理してBOOK_RESYNCへ入る直前までに、後続の古いdiffが
`norm_q`へ積まれることがある。gap検出後の公平性yield中にreceiverはさらに新しいdiffを
coordinatorへ先行bufferできる。その後main consumerがqueue内の古い未mark diffをbuffer末尾へ追加し、
到着順が次のように逆転する。

```text
... u=107 -> u=109 -> （後から）pu=105 / u=107
```

Stage 2B-1は原因を新設したのではなく、元からあった二重owner競合を再現しやすくした。
したがってchunk化だけを戻しても潜在不具合は残る。

### 1.3 破損bufferの再利用とterminal固定

`DepthSyncCoordinator._verify_candidate()`は逆転を検出できており、誤った板を適用していない。
問題はその後である。`_reject_candidate()`は`_snapshot`だけを捨て、`_buffer`を保持する。
再取得したsnapshotも同じ破損位置で失敗し、3/3で`SYNC_FAILED`へ入る。

現行sourceを変更しない決定論的診断結果:

```text
before FETCHING_INITIAL_SNAPSHOT 1 5
after1 FETCHING_INITIAL_SNAPSHOT 2 5 2
after2 FETCHING_INITIAL_SNAPSHOT 3 5 3
after3 SYNC_FAILED 3 5 depth sync attempt limit reached (3/3):
  depth pu chain discontinuity after bridge
  (buffer_index=4, previous_u=109, current_pu=105)
post_depth SYNC_FAILED request=None buffered_count=5
```

terminal後の`observe_depth()`はfailure actionを返すだけで、新snapshot requestを発行しない。
このためtrade/Tapeは継続してもBook projectionとLIVE DOMは永久停止する。

## 2. 採用する恒久修復仕様

### 2.1 R1 — coordinatorの単一owner化（必須）

`LivePipeline.run_async()`のmain consumerをcoordinatorの唯一のmutable ownerとする。

- `DataReceiver`は従来どおり`validate -> raw recorder -> norm_q forward`を担当する。
- production配線では`on_valid_message=notify_depth_sync`を使用しない。
- `depth_sync_actions`、`prebuffered_depth_events`、object identityによる二重処理回避を撤去する。
- main consumerが`norm_q`のFIFO順で、次をすべて実行する。
  - `observe_depth()`
  - `observe_snapshot()` / `observe_fetch_failure()`
  - `start_resync()`
  - terminal後の明示的rearm
- snapshot supervisorは現行どおりrequestを受けてREST候補を取得し、result queueへ返すだけとする。
- `OrderBookStateManager`のapplyも引き続きmain consumerだけが行う。

最初のdepthはreceiverでraw記録された後に`norm_q`へ入り、main consumerがbufferへ追加したactionから
snapshot requestを発行する。したがって「最初の有効depthより前にsnapshot fetchを始めない」barrierは維持される。

`DataReceiver.on_valid_message`という汎用API自体は削除不要である。production depth同期から外し、
別用途と既存単体testへの不要な波及を避ける。

### 2.2 R2 — `pu`不連続時だけbufferを破棄（必須）

reject理由を次の二種類へ分ける。

| reject種別 | buffer | 理由 |
|---|---|---|
| snapshot fetch失敗、target通過後bridgeなし | 保持 | より新しいsnapshot候補で既存の連続suffixを採用できる可能性がある |
| bridge後の`pu` chain不連続 | **全破棄** | snapshotを替えても、同じ破損順序を再利用してはならない |

`pu`不連続時の順序:

```text
候補reject
  -> _snapshot = None
  -> _buffer = []
  -> attemptを1増加
  -> 空bufferのまま次snapshot requestを発行
  -> 以後main consumerが受けた新しいdepthだけを到着順にbuffer
  -> 新snapshotとのstrict bridgeを再検証
```

coordinatorはsnapshotがbufferより先に返っても既に対応できる。
`VERIFYING_*_BRIDGE`で待ち、次のdepth受理時にstrict bridgeを検証するため、新state追加は不要である。

attempt上限に達した場合も、`_fail()`へ入る前または内部で`_snapshot`と`_buffer`を必ず破棄する。
terminal actionには従来どおり非空の`failure_reason`を残し、manifestの`sync_failures`へ記録する。

### 2.3 R3 — `SYNC_FAILED`後の明示rearm（必須）

`observe_depth()`の既存terminal契約は変えない。offline Heatmap reconstructorは
`SYNC_FAILED`後のdiffをdiscardする契約を持つため、自動rearmを同methodへ混ぜない。

代わりにcoordinatorへ、Live pipelineだけが明示的に呼ぶ
`rearm_after_failure(first_depth)`相当のAPIを追加する。

契約:

- 呼出可能stateは`SYNC_FAILED`だけ。
- 次の有効depthを新epochの最初のraw diffとして1件だけbufferする。
- `epoch += 1`、`attempt = 1`、`failure_reason = None`。
- recovery epochのreasonは`BOOK_RESYNC`とし、既存manifestの「epoch 1はINITIAL、2以降はBOOK_RESYNC」と整合させる。
- fresh snapshot requestを1件返す。
- strict verified batchが完成するまで板へsnapshot/diffを適用しない。
- terminal failure actionはrearm前に一度だけrecorder/logへ残す。

これにより、上流が一時的に破損してmax attemptへ達しても、次の有効depthから自律復旧できる。
同一epoch内の有限attempt契約は維持され、lenient適用やsilent infinite retryにはならない。

### 2.4 R4 — queue overflow時もfail closed

単一owner化後、raw recorderは引き続きreceiver到着時に全valid depthを記録する。
`norm_q`が`drop_oldest_log`で欠落した場合、coordinatorまたはbook managerはID/`pu`不連続を検出し、
汚染buffer破棄またはBOOK_RESYNCへ入る。欠落を連続扱いして穴を隠さない。

「runtime coordinator bufferに全rawを残す」ためにreceiverからmutable coordinatorを直接更新する方法は採用しない。
全量監査記録はraw recorder、runtimeの適用可否はmain consumerのstrict検証という責務分離にする。

### 2.5 R5 — Stage 2B-1と完成済み機能を維持

- 32 event / 50msのbacklog chunk化は維持する。
- `await asyncio.sleep(0)`はevent処理完了後・次queue取得前のまま維持する。
- timeout 1000/3000msは変更しない。
- Flow Price Response、3段チャート、8パターン、OI、Footprint、Heatmap、Tape、Hook、Strategy、executionを変更しない。
- `webapp/main.py`、`push_broker.py`、protected frontend 5件を変更しない。

## 3. 実装対象file（次の明示GO後）

必須変更:

1. `Delta_Engine_Pro4web/src/pipeline.py`
   - receiver側coordinator mutationとidentity guardを撤去
   - main consumer単一owner配線
   - terminal後の次valid depthで明示rearm
2. `Delta_Engine_Pro4web/src/acquisition/depth_sync.py`
   - `pu`不連続時のbuffer破棄
   - `_fail()`時のbuffer破棄
   - `rearm_after_failure()`相当の明示API
3. `Delta_Engine_Pro4web/tests/acquisition/test_depth_sync.py`
4. `Delta_Engine_Pro4web/tests/test_live_pipeline.py`

原則変更不要:

- `src/acquisition/receiver.py`
- `src/acquisition/depth_history_recorder.py`
- `src/heatmap/reconstruct.py`
- `src/orderflow/orderbook.py`
- WebSocket schema、frontend、config、compose

原則変更不要fileへ変更が必要になった場合は、その時点で境界拡張として停止・報告する。

## 4. 必須test matrix

### 4.1 coordinator単体

1. 5件bufferの`previous_u=109 / current_pu=105`を再現し、attempt 2へ入る前に`buffered_count == 0`。
2. attempt 2のfresh depthとfresh snapshotだけでSYNCEDへ復帰し、旧diffがverified batchへ混入しない。
3. `pu`不連続が最終attemptならSYNC_FAILED、snapshot/bufferとも空。
4. snapshot fetch failureは従来どおり有限attemptを使い、連続bufferを保持する。
5. bridgeなしsnapshot rejectは従来どおり、より新しいsnapshotで既存連続suffixを採用できる。
6. terminal後の`rearm_after_failure()`でepoch増加、attempt 1、reason BOOK_RESYNC、fresh first diffだけを保持。
7. rearm後の古いepoch/attempt snapshot resultは`DepthSyncInputError`で拒否。
8. offline reconstructorは明示rearmを呼ばず、SYNC_FAILED後discard契約を維持。
9. float禁止、非整数ID拒否、buffer上限、max attemptsの既存testを維持。

### 4.2 Live pipeline統合

1. coordinatorの全mutable methodをspyし、実行task identityがmain consumer 1個だけである。
2. Stage 2B-1 `pipeline_chunk_max_events=1`で強制yieldしても、depth IDのbuffer順が逆転しない。
3. 初期syncはraw record -> norm_q -> main buffer -> requestの順で、snapshot/diffを各1回だけapply。
4. gap直前にqueueへ積まれたunmarked old diffと、yield中のnew diffを決定論的に与え、旧再現がSYNC_FAILED固定にならない。
5. terminal failureを一度記録後、次valid depthから新epochを作り、fresh snapshotでLIVE DOMがSYNCEDへ戻る。
6. 同期待機・failure中もtrade/Tape/CVD/Flowの独立経路が継続する。
7. queue overflowで欠落を隠さずfail closed/resyncし、誤ったSYNCED bookを送らない。
8. `backlog_chunk_yields`、32/50 config、event順序のStage 2B-1既存testをそのまま通す。

### 4.3 回帰

- depth sync / book resync / binance REST / history recorder / Heatmap reconstruct
- Live pipeline / snapshot wiring / Footprint / DOM / Tape / WebApp
- repository全体
- 既知baseline failureは別topicのlayout selector 1件。削除・緩和せず、新規failure 0を条件にする。
- protected/consumer fileは開始終了SHA一致を条件にする。

## 5. runtime検証と合格条件

runtime操作、image build、deploymentは別の明示GO後に行う。

### 5.1 build前gate

- 実装baselineのsource/config/protected SHAを再照合。
- `git diff --check` PASS。
- 対象test、波及test、repository全体で新規failure 0。
- `src/pipeline.py`の既存CRLF/LF比率を開始実物基準で保護し、一括normalizeしない。

### 5.2 candidate image gate

- canonical Stage 2B-1 imageを親・比較基準にし、変更manifestを許可fileだけへ限定。
- image内source SHAとhost SHA一致。
- temporary/isolated環境で決定論的gap、破損buffer、terminal rearmを通す。
- source本体へtemporary計装を混ぜない。必要なら親image ID pinのoverlay方式。

### 5.3 live gate

最低600秒のcanonical soakと、終了後120秒の直接WebSocket連続観測を行う。
600秒中に自然gapが起きない場合でも、4章の決定論的fault testを省略しない。

PASS条件:

- startup initial syncがstrict verifiedで完了。
- gap/RESYNCING/STALEが起きた場合、古い板をSYNCEDとして延長せず、同じruntime内でfresh epochへ復帰。
- 同じ`buffer_index / previous_u / current_pu`を別attemptで反復しない。
- terminal SYNC_FAILEDへ達した場合も、次valid depthから新epoch requestが発行され、永久固定しない。
- 最終`book_synced=true / book_projection_state=SYNCED`。
- 回復後120秒のBOOK_UPDATE sequence error 0、全件SYNCED。
- `book_projection_send_failures=0`。
- Tape dropped 0 / send failure 0 / accounting balanced。
- pipeline exception 0、container restart 0、OOM false。
- Stage 2B-1効果を維持し、heartbeat server/browser interval 3,000ms未満。
- protected/consumer SHAは開始終了一致。

上流DNS/接続断中は即時SYNCEDを要求しない。上流復旧後も自動再armせず固定する場合をFAILとする。

## 6. baseline imageの選定

### 6.1 実装・buildの正本

次修復の正本は、Stage 2B-1成果を保持したhost sourceとpin済みcanonical imageである。

```text
canonical Stage 2B-1 image
sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c

src/pipeline.py
7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae

src/acquisition/depth_sync.py
131b0b773712e983179789316e8562dddc41b7330d8df23330ff5b871debb576
```

理由:

- 32/50 chunk化を含み、600秒再soakで遅延効果gateをPASSしている。
- 現行host sourceと`pipeline.py` SHAが一致する。
- pin tagが保持され、candidateとのmanifest/SHA比較ができる。
- Stage 2Aへ戻すと、今回の二重owner bugを残したままUI freshness改善を失う。

### 6.2 現runtimeとrollbackの注意

18:00 JST時点のread-only確認:

```text
container ccbb420a6ecbb739d9977e3545849e3778eb9c99a3a28fcbac64a5b09807b65a
image     sha256:2b598c055e26401511bc448b1abe14e3c503760cc946f550f6bacf54a954394d
restart   0 / OOM false
stats     book_synced=true / resyncs=1 / gaps=1
health    RED（event lag 41,418ms。直近logに上流DNS/timeoutあり）
```

現runtimeは現在Book SYNCEDへ戻っているが、既知のterminal固定経路をsourceに残すため
「完全正常baseline」とは認定しない。電源復帰後の一時sampleであり、恒久修復の証明でもない。

また、保存済み旧imageに「現行機能を全保持し、今回の二重owner bugも持たない」ものはない。

- Stage 2A `sha256:508bb...`は同じreceiver prebuffer配線を持つ。
- absorption image `sha256:8ce357...`もstrict depth sync導入後で同じ潜在bugを持つ。
- `rollback-pre-footprint-20260728`はFootprint/Tape/Book projectionを欠く。

したがって、`a9c39...`はcandidate失敗時に現状態へ戻すためのexact technical rollbackには使えるが、
rollback成功をLIVE DOM完全修復と呼んではならない。完全に健全なrollback imageは現時点で存在せず、
新candidateが全gateを通って初めて新しい正常baselineとなる。

## 7. 実装時の停止条件

次のいずれかで実装・配備を停止する。

- baseline SHAまたはimage ID不一致。
- coordinator単一ownerにできず、receiver callbackからmutable stateを触る必要が生じる。
- raw全量記録のためにstrict順序またはADR-003を破る必要が生じる。
- offline reconstructorのSYNC_FAILED後discard契約が意図せず変わる。
- protected、timeout、Flow Price Response、3段チャート等への変更が必要になる。
- test期待を削除・緩和しないと通らない。
- candidateで同じ破損tupleのretry反復、terminal固定、誤SYNCED applyが一件でも出る。

## 8. 次の再開位置

ユーザー/統括が本仕様を確認し、製品source・test変更の明示GOを出す地点。
GO後は、上記4fileだけを開始対象としてSHA/EOL checkpointを先に作り、
coordinator単体testを先行してからpipeline単一owner化へ進む。

## 9. GO後の実装・runtime反映結果（2026-08-04）

ユーザーGO後、上記4fileに対して実装と回帰検証を行った。

- `depth_sync.py`: pu chain破損時のbuffer破棄、terminal failure後のfresh depth rearmを実装。
- `pipeline.py`: receiver callbackによるcoordinator直接更新をproduction配線から除去し、main consumerを唯一のmutable-state ownerに統一。
- テスト: 対象回帰 `74 passed`、追加回帰 `65 passed`、`py_compile`、`git diff --check` 成功。
- runtime: 修正版イメージをbuildし、`deltaengine_clone`をforce-recreate。
- 反映後確認: `/api/health=GREEN`、`book_synced=true`、`book_projection_state=SYNCED`、book gaps=0、同期失敗ログなし。

全体pytestは実行ハーネスの125秒制限で完走していないため、全体スイートの完走結果のみ未確定である。
