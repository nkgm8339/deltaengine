# 指示書 Phase 2-0-d-1: depth 初期同期 state machine の実装

**Version: 1.0 / 作成日: 2026-07-29 / 宛先: Codex / 発行: Claude(統括)**

---

## 0. 背景と本指示書の範囲

Phase 2-0-c 報告(`ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-c_初期同期調査報告.md`)で、現行の初期同期は
connector/receiver/supervisor の並行 race であり、REST snapshot が先着すると
`u_snapshot + 1` から最初の受信 diff の `U` までが記録不能になることが現物で確定した。

統括承認済みの是正方針(ADR-011 厳守・pre-sync diff 全量記録方式):

- depth 受信・buffer を REST snapshot 取得より先に開始する。
- strict bridge 検証(`U <= u_snapshot + 1 <= u`)を通った snapshot だけを板 state へ適用する。
- pre-sync diff・reject した snapshot 候補も削除せず全量記録する(ADR-011)。
- 板 apply の所有者は単一コルーチンに集約する(ADR-003)。

**本指示書 (2-0-d-1) の範囲は state machine 本体と pipeline 配線、および strict 検証のテストまで。**
manifest V2、`DEPTH_HISTORY_MAX_BYTES` 配線、rotation 実データ検証は後続の 2-0-d-2 で扱う(本指示書では触らない)。

## 1. 報告書・成果物の出力先(厳守)

- 報告書: `ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-1_同期stateマシン実装報告.md`
- 新規実装: `Delta_Engine_Pro4web/src/acquisition/depth_sync.py`
- 変更: `Delta_Engine_Pro4web/src/pipeline.py`、`Delta_Engine_Pro4web/src/acquisition/receiver.py`
- 新規テスト: `Delta_Engine_Pro4web/tests/acquisition/test_depth_sync.py`
- 報告書には、変更した全ファイルのパスと、追加・変更したテスト名を列挙すること。

## 2. 統制(厳守)

- 実装前に、本指示書 §4 の設計で問題ないか計画を1度提示し、統括承認を待ってから着手する。
  (承認済みの方針から逸脱する点・判断を要する点がある場合のみ。なければその旨を述べて着手してよい。)
- テストにライブ接続禁止。全 fixture/mock 駆動。
- 同一テスト・同一コマンドの失敗が2回連続したら停止し、原因切り分けのみ報告して指示を待つ。
- 1タスク完了ごとに報告し、勝手に 2-0-d-2 へ進まない。
- manifest スキーマ、`max_bytes` 環境変数、`docker-compose.yml`、`webapp/main.py` は本指示書では変更しない。
- 既存未コミット差分(`webapp/main.py`、`docker-compose.yml`、`tests/webapp/test_book_update.py`)は保護する。触れる必要が生じたら停止して報告する。

## 3. sandbox 制約への対応

Phase 2-0-a で `pwsh.exe` 生成が Windows error 1312 で失敗した事象、および過去の
`windows unelevated restricted-token sandbox` による直接編集不可事象が記録されている。
既存追跡ファイルを `apply_patch` で直接編集できない場合は、変更を `.patch` として新規出力し
`git apply --recount` で適用する分岐を用いること。両対応で進め、いずれも失敗したら停止して報告する。

## 4. 実装設計

### 4.1 新規: depth_sync.py — 同期 coordinator

Phase 2-0-c §4.0 の state を実装する。板 state 自体は持たず、
「どの snapshot 候補と bridge diff を検証済みとして採用したか」を判定して返す純粋な調整器とする。

state:

```text
WAITING_FOR_FIRST_DEPTH → FETCHING_INITIAL_SNAPSHOT → VERIFYING_INITIAL_BRIDGE → SYNCED
  → (gap) RESYNC_BUFFERING → FETCHING_RESYNC_SNAPSHOT → VERIFYING_RESYNC_BRIDGE → SYNCED
上限到達: → SYNC_FAILED
```

要件:

1. 最初の有効 depthUpdate を受信するまで snapshot fetch を開始しない(barrier)。
   `ExchangeConnector.state == SUBSCRIBED` は開始条件にしない。最初の有効 depth 実データを条件にする。
2. 同期確立までの depthUpdate を full raw dict のまま単一ループ上の専用 buffer に保持する。
   この buffer は `BoundedEventQueue`(event_queue.py)とは別管理とする。上限は正整数設定。
3. snapshot 候補ごとに epoch(起動・各 gap 再同期を区別する正整数)と attempt(正整数)を付与する。
4. bridge 探索: buffer を到着順に走査し `U <= u_snapshot + 1 <= u` を満たす最初の diff を bridge とする。
   - buffer 最新 `u` が target 未満なら FAIL にせず次の diff を待つ。
   - buffer が target を通過したのに bridge がなければ、その snapshot 候補を reject して再取得。
5. bridge 以後の buffered diff について `pu(後) == u(前)` を検証する。不連続なら verified にしない。
6. attempt 上限(正整数設定)到達で `SYNC_FAILED`。silent infinite retry や lenient 適用はしない。
7. すべての ID・epoch・attempt・max は整数として検証する。`float()` 禁止。価格・数量は文字列のまま扱う。

coordinator は板 state を書き換えず、「検証済み snapshot」「検証済み bridge 以降の diff 列(到着順)」
「同期結果(SYNCED / SYNC_FAILED と失敗理由)」を呼び出し側へ返すインターフェースとする。

### 4.2 変更: receiver.py — 最初の depth 通知

`DataReceiver` に、最初の有効 depth を coordinator へ通知する callback / tap を追加する。
raw recorder への書込 → `norm_q` への forward の到着順契約(receiver.py:99-101)は維持する。
raw 記録は buffer とは独立に、到着時にこれまで通り継続する(pre-sync diff も全量記録)。

### 4.3 変更: pipeline.py — 配線と板 apply の集約

- 現行 `_book_resync_supervisor()` の「REST snapshot 即適用」(pipeline.py:210-222)を、
  coordinator 経由の「strict 検証後にだけ適用」へ置き換える。
- 板 state の apply は Live main consumer 側の単一コルーチンに集約する。
  snapshot fetch task と main consumer が同じ mutable state を別々に更新しない(ADR-003)。
- strict 検証 PASS 後に snapshot を `book_state.apply()` し、`apply_initial_sync(snapshot_u)` を呼び、
  外部検証済み bridge を最初の diff として渡す。orderbook.py のlenient branch を「未検証 diff の穴隠し」に使わない。
- 初期同期と BOOK_RESYNC で同じ coordinator/state machine を通す。
- strict 同期待機中は板投影のみ fail-closed とし、trade / CVD / Flow Price Response 等の独立経路は止めない。

### 4.4 触らないもの(本指示書の範囲外)

- `orderbook.py`: 原則変更不要(Phase 2-0-c §4.8)。coordinator 外部で strict 検証する。
  lenient API を未検証で呼べない契約は doc/test で固定するに留める。verified bridge 専用 API 新設は本指示書では行わない。
- `binance_ws.py` / `connector.py`: 最初の depth 実データを barrier にする案では変更不要。
- manifest / `depth_history_recorder.py` / `max_bytes` / compose / `webapp/main.py`: 2-0-d-2 で扱う。

## 5. テスト(test_depth_sync.py、全 fixture 駆動)

最低限、以下を fixture で検証する。ライブ接続禁止。

1. depth を先に受信し buffer 開始後にだけ snapshot fetch が始まる。
2. buffer 内の `U <= u_snapshot + 1 <= u` bridge で SYNCED になる。
3. buffer が target を通過して bridge なしなら snapshot を再取得する。
4. attempt 上限到達で SYNC_FAILED、板は fail-closed、明示 error。
5. bridge 以後の `pu` 不連続を verified にしない。
6. pre-sync diff が到着順・全量で raw 記録経路に残る(buffer に入れても記録は捨てない)。
7. BOOK_RESYNC でも同じ strict 手順を通る。
8. 追加した metadata・経路に float 型が混入しない。

既存テストで本変更の影響を受けるもの(Phase 2-0-c §4.10 記載: `test_book_resync.py`、
`test_live_pipeline.py`、`test_binance_rest.py` の初期同期関連)は、strict 同期後の意味に合わせて更新する。
更新したテストは報告書に「旧期待 → 新期待」で列挙する。lenient 前提のまま残さない。

## 6. 報告フォーマット

- `[完了/失敗/停止] Phase 2-0-d-1 同期stateマシン実装`
- 変更・新規ファイルのパス一覧
- depth_sync.py の state 実装の要点(どの関数がどの state 遷移を担うか、ファイル:行番号)
- 追加テスト名と、各テストが §5 のどの項目を検証するか
- 更新した既存テストの「旧期待 → 新期待」
- テスト実行結果(`python -m pytest -q -p no:cacheprovider` の該当範囲。全体回帰は完了時に1度)
- float 混入チェック結果
- 既存未コミット差分を触っていないことの確認
- 実行した全コマンドと結果(失敗コマンドも隠さず記載)

---

以上。完了報告受領後、統括が検証し Phase 2-0-d-2(manifest V2・max_bytes 配線・rotation 実データ検証)指示書を発行する。
