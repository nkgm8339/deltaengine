# 指示書: Phase 2-1 板state再構築器 実装
**Version: 1.0 / 作成日: 2026-07-30 / 発行: 統括(Claude web) / 実行: Claude Code(Codex)**

---

## 0. 本書の位置づけ

- Bookmap系ヒートマップ開発 指示書 v1.5 §5 #12「Phase 2-1 再構築器設計」の実装指示。
- 根拠は `p21_evidence.zip`(2026-07-30受領)の実物のみ。統括が独立検証済み:
  - 検証セグメント2本のSHA-256/byte/行数がmanifest V2と完全一致
  - manifest `sync_events` のbridge(snapshot_u=11165393552876, bridge_U=11165393550921,
    bridge_u=11165393566438)が実データで `U <= snapshot_u+1 <= u` 成立
  - bridgeからセグメント2末尾までpuチェーン **depth 135件 全PASS**
  - float混入0、価格は全て文字列
- CLAUDE.md「ヒートマップ開発 統制ルール」に全面準拠(ライブ接続禁止・停止条件・報告フォーマット)。

## 1. 目的と範囲

**目的**: JSONL記録(manifest V2)から板stateの時系列を決定論的に再構築する
オフライン再構築器を実装する。Phase 2-2(静的描画)への入力契約を確定する。

**範囲外(本タスクで実装しない)**:
- 描画・ダウンサンプリング(Phase 2-2)
- ライブパイプラインへの組込み(Phase 3)
- 約定バブル(Phase 4。tradeは読み飛ばすが、hook拡張余地はAPI上残す)
- 常時記録の恒久有効化(指示書v1.5 §6 未判断事項)

## 2. Step 0: 証拠保全(実装前必須)

HEADは `e358a0f`(Phase 1最終)であり、Phase 2-0-d系の実装全体
(pipeline.py、depth_sync.py、depth_history_recorder.py 等)が未コミット差分のまま。
実装着手前に以下を実行する。

```powershell
# HEATMAP配下に未コミット差分の全量パッチを保全(tracked差分)
git diff > ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_YYYYMMDD.patch
# untrackedファイル一覧も保全
git status --porcelain > ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_YYYYMMDD.txt
```

パッチのSHA-256を報告書に記載する。**git add / commit / stash / checkout は行わない**
(コミットチェックポイントは別タスクとして統括が発行する)。

## 3. 実装物

新規ファイルのみ。**既存ファイルの変更は一切禁止**(orderbook.py / depth_sync.py /
depth_history_recorder.py / 保護対象4ファイルを含む全既存ファイル)。

| # | パス | 内容 |
|---|---|---|
| N1 | `Delta_Engine_Pro4web/src/heatmap/__init__.py` | 空パッケージ |
| N2 | `Delta_Engine_Pro4web/src/heatmap/reconstruct.py` | 再構築器本体 |
| N3 | `Delta_Engine_Pro4web/tests/heatmap/__init__.py` | 空 |
| N4 | `Delta_Engine_Pro4web/tests/heatmap/test_reconstruct.py` | ユニット+実データfixtureテスト |
| N5 | `Delta_Engine_Pro4web/tests/heatmap/fixtures/`(後述) | 合成fixture + 実データ縮約fixture |
| N6 | `ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py` | 手動確認用CLI |
| N7 | `Delta_Engine_Pro4web/tests/heatmap/fixtures/make_real_fixture.py` | 実データからのfixture生成スクリプト(出所記録付き) |

### 3.1 N2: 再構築器の設計(確定仕様)

既存クラスを**そのまま流用**する(改造禁止):

- 同期検証: `src.acquisition.depth_sync.DepthSyncCoordinator`(p21_evidence実物383行)。
  純粋state machineでI/O・asyncio非依存のため、オフラインでそのまま使える。
- 板state: `src.orderflow.orderbook.OrderBookStateManager`(実物orderbook.py:97)。

**lenient受理の扱い(2-0-cで確立した契約の遵守方法)**:
`OrderBookStateManager._apply_diff` の `_sync_id is not None` 分岐(orderbook.py:236-243)は
「最初の非staleなdiffを無検証で受理」するlenientパスである。本再構築器は
**Coordinatorが `SYNCED`(verified)を返した snapshot+diffs だけ**を book に適用する。
つまり lenient 分岐に入るのは Coordinator 検証済みの bridge diff のみであり、
未検証diffの穴隠しには使わない。適用手順は固定:

1. `apply(SNAPSHOT)` — verified snapshotから `OrderBookUpdate(update_type="SNAPSHOT", final_update_id=snap["u"], ...)` を構築して適用
2. `apply_initial_sync(snap["u"])`
3. verified diffs を到着順に `apply(DIFF)` — 先頭(bridge)はlenient分岐で受理され、以降はpu基準gap検出(orderbook.py:245-268)が働く

**主要クラス(この署名を実装する)**:

```python
"""Offline depth-history reconstructor (Phase 2-1).

Input: JSONL segments + manifest V2 written by DepthHistoryRecorder.
Output: deterministic book-state timeline for Phase 2-2 rendering.
Decimal only — no float(). asyncio 不使用(純オフライン、ADR-003に抵触しない)。
"""

@dataclass(frozen=True)
class SegmentInfo:
    path: Path
    manifest: dict          # load_depth_history_manifest() の戻り値
    started_at: str         # manifest["started_at"]

class DepthHistoryReader:
    """Enumerate and validate segments in one recording directory.

    - manifestのないセグメント(.part含む)は列挙対象外とし、skipped_segmentsに記録
      (recorder docstring 12行目の読み出し契約に従う)
    - 各セグメントは使用前に byte_size / record_count / sha256 をmanifestと突き合わせ、
      不一致は SegmentIntegrityError(検証続行しない)
    - manifest V1(schema_version=1)も列挙は可(load_depth_history_manifestがV1受理)。
      sync_events を持たないため、再構築はデータ内のdepthSnapshotに依存する
    - ソートキーは manifest["started_at"]
    """
    def __init__(self, directory: Path) -> None: ...
    def segments(self) -> list[SegmentInfo]: ...
    def iter_records(self) -> Iterator[dict]:
        """全セグメントを順に読み、JSON行をdictでyield。tradeもそのまま流す。"""

@dataclass(frozen=True)
class ReconstructionEvent:
    """Phase 2-2への出力契約(1適用=1イベント)。"""
    kind: str               # "SNAPSHOT_APPLIED" | "DIFF_APPLIED" | "SYNC_STARTED"
                            # | "RESYNC_STARTED" | "SYNC_FAILED" | "GAP_DETECTED"
    event_time_ms: int      # レコードの E(int ms)。snapshotはE、diffはE
    last_update_id: int | None
    epoch: int

class DepthReconstructor:
    """Consume records; drive DepthSyncCoordinator + OrderBookStateManager."""
    def __init__(self, *, symbol: str = "BTCUSDT",
                 max_buffered_diffs: int = 10_000,
                 max_attempts: int = 1) -> None: ...
        # max_attempts=1: 録画内に同一epochのsnapshot候補は1つしかないため

    def run(self, records: Iterable[dict]) -> Iterator[ReconstructionEvent]:
        """決定論的イベント列をyield。処理規則:
        - e=="trade": 読み飛ばし(カウントのみ)。将来hookのため on_trade は設けない(範囲外)
        - e=="depthUpdate": coordinator未SYNCEDなら observe_depth / SYNCEDなら book.apply(DIFF)
          - book が gap_detected を返したら GAP_DETECTED をyieldし
            coordinator.start_resync(該当diff) → RESYNC_STARTED
        - e=="depthSnapshot": coordinator.observe_snapshot(現在のrequest, レコード)
          - requestは notify_first_depth/observe_depth/start_resync が返した最新のものを保持
          - actionが is_verified なら上記3.1の固定手順で適用し SNAPSHOT_APPLIED +
            verified diffsぶんの DIFF_APPLIED をyield
          - SYNC_FAILED なら SYNC_FAILED をyieldして以降のdepthは discard カウント
        - 不正レコード(DepthSyncInputError)は即例外で停止(黙殺しない)
        """

    def snapshot(self) -> OrderBookSnapshot | None:
        """現時点の板state(orderbook.snapshot()の委譲)。"""

    def sample_states(self, records: Iterable[dict], *,
                      interval_ms: int) -> Iterator[tuple[int, OrderBookSnapshot]]:
        """(sample_time_ms, snapshot) を interval_ms 刻みでyield。
        Phase 2-2の主入力。per-diffの全コピーを避けるため、サンプル時刻を跨いだ
        適用直後にのみ snapshot() を取る。"""

    @property
    def counters(self) -> dict[str, int]:
        """trades_skipped / diffs_applied / diffs_discarded_after_fail /
        gaps_detected / snapshots_applied / sync_failures を返す(黙殺ゼロ原則)。"""
```

**Decimal規律**: レコードの文字列価格は `Decimal(str値)` でのみ変換。`float()` 使用禁止。
テストに `float` 型混入検査を含める。

### 3.2 N5/N7: fixture

**合成fixture(N4内でinline生成可)**: 最低限、以下のケースを揃える。

1. bridge成立(U <= snap_u+1 <= u)→ SYNCED → diff数件適用
2. bridge不成立(latest_u が target を超えているのに橋なし)→ SYNC_FAILED(max_attempts=1)
3. puチェーン断絶 → GAP_DETECTED → 録画内に後続 BOOK_RESYNC snapshotあり → 再SYNC成功
4. puチェーン断絶 → 後続snapshotなし → 末尾まで discard、counters整合
5. stale diff(u <= last_id)→ diffs_stale としてbookが拒否、再構築は継続
6. manifest sha256不一致 → SegmentIntegrityError
7. manifest欠如セグメント → skip記録
8. float混入レコード → 例外(受理しない)

**実データ縮約fixture(N7で生成)**: `p21_evidence` と同一の検証録画
`data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT/`
の先頭2セグメントから、**depthSnapshot全行 + depthUpdate全行(136行)+ trade先頭5行**を
抽出した2ファイル + 対応manifest(record_count/byte_size/sha256は縮約後の実値で再計算し、
`"_fixture_provenance"` キーに元ファイル名・元SHA-256を記録)を
`tests/heatmap/fixtures/real_validation/` に生成する。生成スクリプトN7は再実行可能にする。

### 3.3 N4: テストの合格基準

合成fixture 8ケースに加え、実データ縮約fixtureで以下を assert する
(統括が実物検算済みの期待値):

- SNAPSHOT_APPLIED 1件、snapshot_u = 11165393552876
- bridge diff: U=11165393550921, u=11165393566438
- pre-sync depth(bridge前)1件は適用されない(録画には存在するが book には入らない)
- DIFF_APPLIED = **135件**(bridge含む、2セグメント通算)、GAP_DETECTED = 0、SYNC_FAILED = 0
- 最終 last_update_id = 2セグメント目最終depthの u と一致
- 全価格・数量が Decimal であり float が状態内に存在しない
- `sample_states(interval_ms=1000)` が単調増加の時刻でsnapshotを返す

### 3.4 N6: 手動確認CLI

```
python ArchitectureRepository/00_Master/HEATMAP/tools_p21/reconstruct_check.py <recording_dir> [--interval-ms 1000]
```

出力: セグメント数 / skip数 / integrity結果 / イベント種別カウント / counters /
最終last_update_id / 所要時間。**本CLIのフルデータ実行は手動確認タスク**であり、
テストからは呼ばない(統制ルール: フルサイズ処理は成果物確認時のみ)。

## 4. 実行手順(統制ルール準拠)

1. **計画提示**: 変更ファイル一覧(§3のN1〜N7のみのはず)・想定リスクを提示し、承認後に着手
2. Step 0 証拠保全
3. N1〜N7 実装
4. `python -m pytest -q -p no:cacheprovider`(Delta_Engine_Pro4web/ から実行)
   - ベースライン: 収集時 `1 failed, 727 passed, 1 skipped`。
     許容される失敗は既知の `test_dom_tape_fusion_ui.py` 1件のみ。新規failはゼロであること
5. 手動確認: N6 CLIを検証録画dir全34セグメントに対して実行し、出力を報告書に転記
   (期待: integrity全PASS、SYNC_FAILED=0、GAP_DETECTED=0)
6. 報告書 + 完全ZIP + CompletionLog.mdエントリの3点セット

## 5. 停止条件(再掲+固有)

- 同一テスト失敗2回連続で停止・切り分け報告
- 既存ファイルへの変更が必要と判明した場合は**実装せず停止**し、対象ファイル・理由・
  最小変更案を報告(統括が判断する)
- 検証録画dirの実物が §3.2 記載パスに存在しない場合は停止・実パス報告
- ライブ接続は一切禁止

## 6. 統括側で確定済みの設計判断(Codexは再検討不要)

| 判断 | 根拠 |
|---|---|
| DepthSyncCoordinatorをオフライン流用 | 実物383行がI/O非依存の純粋state machineであることを確認済み |
| lenient分岐はverified bridge適用専用 | orderbook.py:236-243の実物と2-0-c契約の両立手段として統括が決定 |
| max_attempts=1 | 録画内に同一epochの候補snapshotは1つのみ(録画の性質) |
| tradeは読み飛ばし | Phase 4素材だが本Phaseの範囲外(指示書v1.5 §3) |
| 出力はsample_states主契約 | per-diff全コピー(1000段×2面×135回)の無駄を避ける |
| 新規namespace `src/heatmap/` | `src/acquisition/replay.py`(既存・別物)との混同回避 |

---

## 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-07-30 | 初版。p21_evidence実物検証に基づく再構築器実装指示 |
