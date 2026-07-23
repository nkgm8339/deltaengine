この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。判断に迷う点があれば作業を中断して報告せよ。

# 指示書_OrderBook_Resync_v1

**対象**: `C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web`(現行ツリー、320 passed 時点)
**目的**: 板初期同期の「一発勝負」設計を廃し、Resync Supervisor による自動回復を実装する
**バージョン**: v3.6.6 / ADR-010

---

## 0. 背景(実行者向け)

現行の板同期には回復経路が存在しない。

1. 起動時 REST snapshot 取得は `pipeline.py` `run_async` 内の1回きり。失敗すると板は永久に空
2. gap 検出時に `OrderBookStateManager` は状態を破棄するが、誰も再snapshotを取得しない。以後の全diffは `rejected_before_snapshot` となり板は永久に空

本指示書は、同期アルゴリズム(ADR-007 の lenient 方式・pu-based gap検出)を**一切変更せず**、その外側に回復ループ(supervisor)を追加する。

**設計決定(逸脱禁止)**:
- lenient 同期・gap検出ロジックは無変更
- バックオフ定数は config でなくモジュール定数とする(較正対象でない運用値。config スキーマ・YAMLReference の改訂連鎖を避ける)
- supervisor は Live 専用。Replay 経路(`ReplayStats` 含む)は無変更
- `float()` は全域で使用禁止
- `docs/` / `ArchitectureRepository/` の既存ファイルは無変更(新規追加と CHANGELOG 追記のみ可、§6)

---

## 1. `src/orderflow/orderbook.py` — `is_initialized` プロパティ追加

`apply_initial_sync` メソッドの直後(`def snapshot` の直前)に以下を挿入する。他は一切変更しない。

```python
    @property
    def is_initialized(self) -> bool:
        """True when the book currently holds a valid synced state."""
        return self._initialized
```

---

## 2. `src/pipeline.py` — Resync Supervisor 本体

### 2-1. モジュールレベル定義の追加

`_imbalance_should_fire` 関数定義の直後(最初の `@dataclass` の前)に以下を挿入する。

```python
# --- Order Book resync supervisor (ADR-010) -----------------------------------

_BOOK_RESYNC_BACKOFF_SEC: tuple[int, ...] = (5, 10, 30)
_BOOK_HEALTH_POLL_SEC: int = 1


@dataclass
class BookResyncCounters:
    """Mutable counters owned by the live pipeline; single writer (supervisor)."""
    resyncs: int = 0
    fetch_failures: int = 0


async def _book_resync_supervisor(
    *,
    symbol: str,
    book_state: OrderBookStateManager,
    normalizer: Any,
    fetch_snapshot: Callable,
    counters: BookResyncCounters,
    sleep: Callable[[int], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Keep the order book initialized for the lifetime of the live pipeline.

    Whenever the book is not initialized (startup, or after a gap-detection
    reset in OrderBookStateManager), fetch a REST depth snapshot and re-enter
    the lenient initial-sync mode (ADR-007). Retries forever with bounded
    backoff; every failure is logged with the HTTP status / exception text
    (no silent loss). The sync algorithm itself is unchanged (ADR-010).
    """
    consecutive_failures = 0
    synced_once = False
    while True:
        if book_state.is_initialized:
            consecutive_failures = 0
            await sleep(_BOOK_HEALTH_POLL_SEC)
            continue
        try:
            raw_snap = await fetch_snapshot(symbol)
            depth_evt = rest_to_depth_event(raw_snap, symbol)
            update = normalizer.process_depth(depth_evt)
            if update is None:
                raise ValueError("depth snapshot normalization returned None")
            book_state.apply(update)
            book_state.apply_initial_sync(update.final_update_id)
            if synced_once:
                counters.resyncs += 1
                logger.info(
                    "order book resynced: snap_id=%s resyncs=%s",
                    update.final_update_id, counters.resyncs,
                )
            else:
                logger.info(
                    "initial snapshot applied: snap_id=%s (sync waiting for first diff with U<=%s)",
                    update.final_update_id, update.final_update_id + 1,
                )
            synced_once = True
            consecutive_failures = 0
            await sleep(_BOOK_HEALTH_POLL_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            counters.fetch_failures += 1
            delay = _BOOK_RESYNC_BACKOFF_SEC[
                min(consecutive_failures, len(_BOOK_RESYNC_BACKOFF_SEC) - 1)
            ]
            consecutive_failures += 1
            logger.warning(
                "depth snapshot fetch failed (attempt=%s, retry_in=%ss): %s",
                consecutive_failures, delay, exc,
            )
            await sleep(delay)
```

### 2-2. 起動時ワンショット取得の置換

`run_async` 内の以下のブロック**全体**(コメント行から `logger.warning("initial depth snapshot fetch failed: %s", exc)` まで)を削除し、置換する。

削除対象(原文一致を確認せよ):

```python
        # Fetch REST snapshot after connector/receiver start so buffered depth diffs
        # can be aligned via apply_initial_sync (Binance initial sync spec).
        if fetch_snapshot is not None:
            try:
                raw_snap = await fetch_snapshot(self.symbol)
                depth_evt = rest_to_depth_event(raw_snap, self.symbol)
                update = normalizer.process_depth(depth_evt)
                if update is not None:
                    book_state.apply(update)
                    book_state.apply_initial_sync(update.final_update_id)
                    logger.info(
                        "initial snapshot applied: snap_id=%s (sync waiting for first diff with U<=%s)",
                        update.final_update_id, update.final_update_id + 1,
                    )
                    if book_state.snapshots_applied != 1:
                        logger.warning(
                            "book_state initial snapshot not applied cleanly: "
                            "snapshots_applied=%s", book_state.snapshots_applied
                        )
                else:
                    logger.warning("initial depth snapshot normalization failed")
            except Exception as exc:
                logger.warning("initial depth snapshot fetch failed: %s", exc)
```

置換後:

```python
        # Order book sync is owned by the resync supervisor (ADR-010): it performs
        # the initial REST snapshot with retry, and re-syncs automatically after
        # gap-detection resets. fetch_snapshot=None disables it (tests).
        self.book_resync_counters = BookResyncCounters()
        book_supervisor_task: Optional[asyncio.Task] = None
        if fetch_snapshot is not None:
            book_supervisor_task = asyncio.create_task(_book_resync_supervisor(
                symbol=self.symbol,
                book_state=book_state,
                normalizer=normalizer,
                fetch_snapshot=fetch_snapshot,
                counters=self.book_resync_counters,
            ))
```

**注記**: この置換により、snapshot 適用完了を待たずに消費ループが開始する。適用前に到着した diff は既存カウンタ `diffs_rejected_before_snapshot` で計上され(no silent loss)、snapshot 適用後の lenient 整列で収束する。仕様上問題ない。既存の live pipeline テストは全て `fetch_snapshot=None` のため無影響。

### 2-3. 終了処理

`run_async` の `finally:` ブロック内、`connector.stop()` の直後に以下を挿入する。

```python
            if book_supervisor_task is not None:
                book_supervisor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await book_supervisor_task
```

### 2-4. `LiveStats` へのカウンタ追加

`LiveStats` dataclass の `book_diffs_stale: int` の直後に追加する。

```python
    book_resyncs: int
    book_snapshot_fetch_failures: int
```

`LiveStats` 生成箇所の `book_diffs_stale=book_state.diffs_stale,` の直後に追加する。

```python
            book_resyncs=self.book_resync_counters.resyncs,
            book_snapshot_fetch_failures=self.book_resync_counters.fetch_failures,
```

`ReplayStats` は変更しない。

---

## 3. `webapp/main.py` — 可観測性の露出

### 3-1. `/api/stats`

`stats["book_gaps_detected"] = bm.gaps_detected` の直後に追加する。

```python
        stats["book_synced"] = bm.is_initialized
        rc = getattr(pipeline, "book_resync_counters", None)
        if rc is not None:
            stats["book_resyncs"] = rc.resyncs
            stats["book_snapshot_fetch_failures"] = rc.fetch_failures
```

(既存の `if bm is not None:` ブロック内に収める)

### 3-2. `_stats_loop`(STATS WebSocket 配信)

`stats: dict = {"ws_upstream": "OPEN", ...}` の行の直後に追加する。

```python
                bm = getattr(pipeline, "book_manager", None)
                stats["book"] = "SYNCED" if (bm is not None and bm.is_initialized) else "EMPTY"
                rc = getattr(pipeline, "book_resync_counters", None)
                if rc is not None:
                    stats["book_resyncs"] = str(rc.resyncs)
```

---

## 4. `webapp/static/index.html` — devオーバーレイに BOOK 行追加

`renderDev()` 内の rows 配列、`["WS",s.ws_upstream??"—",BUY],` の直後に以下2要素を追加する。他は一切変更しない。

```javascript
    ["BOOK",s.book??"—",s.book==="SYNCED"?BUY:SELL],["RESYNC",s.book_resyncs??"—",TXT],
```

---

## 5. テスト(新規7本、320 → 327)

### 5-1. `tests/orderflow/test_orderbook.py` 追記(1本)

```python
def test_is_initialized_property_lifecycle():
    """is_initialized: False -> True after snapshot -> False after gap reset."""
    mgr = OrderBookStateManager(symbol="BTCUSDT")
    assert mgr.is_initialized is False
    snap = OrderBookUpdate(
        symbol="BTCUSDT", update_type="SNAPSHOT",
        event_time=_ts(0), first_update_id=None, final_update_id=100,
        previous_final_update_id=None,
        bids=(BookLevel(price=Decimal("50000"), quantity=Decimal("1")),),
        asks=(BookLevel(price=Decimal("50001"), quantity=Decimal("1")),),
    )
    mgr.apply(snap)
    assert mgr.is_initialized is True
    gap_diff = OrderBookUpdate(
        symbol="BTCUSDT", update_type="DIFF",
        event_time=_ts(1), first_update_id=300, final_update_id=310,
        previous_final_update_id=250,  # != last_update_id(100) -> gap
        bids=(), asks=(),
    )
    result = mgr.apply(gap_diff)
    assert result.gap_detected is True
    assert mgr.is_initialized is False
```

既存の `OrderBookUpdate` コンストラクタ引数名・`_ts` 相当のヘルパは、同ファイル内の既存テストの流儀に**完全準拠**させる(上記は形の指定であり、引数名が既存実装と異なる場合は既存実装に合わせる。ロジックの弱体化は禁止)。

### 5-2. `tests/test_book_resync.py` 新規(5本)

以下の骨子で実装する。fake sleep は遅延値を記録して即 return し、実時間を消費しない。fake fetch は Binance REST 形の raw dict `{"lastUpdateId": <int>, "bids": [["50000.0", "1.0"]], "asks": [["50001.0", "1.0"]]}` を返す。normalizer は実物 `DataNormalizer`(binance プロファイル)を使い、conftest / 既存テストのプロファイル生成流儀に合わせる。実物構築が既存テストに前例なく重い場合のみ、`process_depth` が SNAPSHOT `OrderBookUpdate` を返す最小 fake を許可する(その場合は理由を CompletionLog に記載)。

```python
"""Tests for _book_resync_supervisor (ADR-010)."""
```

- **T1 `test_startup_retry_until_success`**: fetch が2回例外→3回目成功。supervisor 実行後(成功後の sleep 呼び出しで CancelledError を注入して停止)、`book_state.is_initialized is True`、`counters.fetch_failures == 2`、`counters.resyncs == 0`、記録された遅延列の先頭2件が `[5, 10]`
- **T2 `test_backoff_caps_at_30`**: fetch が4回連続例外。遅延列が `[5, 10, 30, 30]`
- **T3 `test_resync_after_gap`**: 初回成功→テスト側で gap diff を `book_state.apply` に流して未初期化化→supervisor が再fetch→`counters.resyncs == 1`、`book_state.is_initialized is True`
- **T4 `test_no_fetch_while_healthy`**: 初回成功後、healthy ポーリングを5サイクル回しても fetch 呼び出し回数が増えない(1回のまま)
- **T5 `test_cancel_terminates_cleanly`**: sleep 中に task.cancel()。`asyncio.CancelledError` で終了し、それ以外の例外を出さない

テスト内での supervisor 停止は「fake sleep が N 回目の呼び出しで `asyncio.CancelledError` を送出する」方式を標準とする(決定的・実時間ゼロ)。

### 5-3. `tests/webapp/test_api.py` 追記(1本)

`test_stats_includes_book_resync_counters`: fake pipeline に `book_manager`(is_initialized=True の実 `OrderBookStateManager` に SNAPSHOT 適用済み)と `book_resync_counters = BookResyncCounters(resyncs=2, fetch_failures=3)` を持たせ、`/api/stats` のレスポンスに `book_synced is True` / `book_resyncs == 2` / `book_snapshot_fetch_failures == 3` が含まれることを検証する。同ファイルの既存 fake pipeline 流儀に準拠する。

---

## 6. ドキュメント

### 6-1. `ArchitectureRepository/00_Master/ADR/ADR-010_OrderBook_Resync_v3.0.md` 新規作成(全文をそのまま使用)

```markdown
# ADR-010 — Order Book Resync Supervisor

**Status**: Accepted
**Version**: v3.0

---

# Context

Order book initial sync (ADR-007 lenient mode) had no recovery path: the REST
depth snapshot was fetched exactly once at startup, and a gap-detection reset
left the book permanently uninitialized. Either failure mode resulted in a
permanently empty order book while the trade-side pipeline kept running.

---

# Decision

A resync supervisor coroutine owns order book synchronization for the lifetime
of the live pipeline:

- Whenever the book is uninitialized (startup, or after a gap reset), it
  fetches a REST depth snapshot and re-enters lenient initial-sync mode.
- Failures retry forever with bounded backoff (5s / 10s / 30s cap); every
  failure is logged with the HTTP status or exception text (no silent loss).
- Counters `resyncs` and `fetch_failures` are exposed via LiveStats,
  `/api/stats`, and the STATS WebSocket message.
- The sync algorithm itself (ADR-007 lenient alignment, pu-based gap
  detection) is unchanged. Backoff timings are module constants, not
  configuration, as they are operational values and not calibration targets.
- Replay mode is unaffected.

---

# Consequences

Positive

- Transient REST failures and sequence gaps self-heal without restart.
- A permanently failing REST endpoint (e.g., HTTP 451 regional block) is now
  diagnosable from the logged status; a WS partial-book fallback is designed
  only if such a block is confirmed.

Trade-offs

- Diffs arriving before the first snapshot application are rejected and
  counted (diffs_rejected_before_snapshot) instead of being buffered; the
  lenient first-diff acceptance converges the state immediately after.

---

# Related Documents

- ADR-007_OrderBook_Initial_Sync
- ErrorCodes
```

### 6-2. `ArchitectureRepository/00_Master/CHANGELOG.md` 追記

先頭の `---`(ヘッダ直後)と `# v3.6.5` の間に以下を挿入する。既存エントリは一切変更しない。

```markdown
# v3.6.6 — 2026-07-19

## Added

- ADR-010_OrderBook_Resync_v3.0.md: 板同期の Resync Supervisor を決定。起動時 REST snapshot の無限リトライ(バックオフ 5/10/30s)と、gap 検出後の自動再同期を実装。lenient 同期アルゴリズム(ADR-007)は無変更。
- LiveStats / `/api/stats` / STATS 配信に `book_synced` / `book_resyncs` / `book_snapshot_fetch_failures` を追加。dev オーバーレイに BOOK / RESYNC 行を追加。

## Tests

- Resync Supervisor(起動リトライ・バックオフ上限・gap 後再同期・healthy 時非取得・キャンセル終了)、`is_initialized` プロパティ、stats 露出を追加。320 → 327。

---
```

---

## 7. 検証と完了条件

1. `pytest` 全実行: **327 passed**(既存320 + 新規7)。既存テストの修正は不要のはず。必要になった場合は理由を CompletionLog に記載せよ
2. `grep -rn "float(" src/ webapp/ tests/test_book_resync.py` — 新規・変更コードに `float(` 0件
3. `ArchitectureRepository/` の差分が ADR-010 新規 + CHANGELOG 追記の2点のみであること
4. アプリ起動時のバージョン表示が v3.6.6 になること(CHANGELOG 先頭エントリ由来。コード変更不要)

## 8. 完了報告(3点セット)

1. `CompletionLog.md` に完了報告を追記(テスト数推移・設計決定遵守表・逸脱の有無)
2. 全体を `DeltaEngine_OBRESYNC_完了.zip` として提出
3. チャット報告と ZIP の両方を提出

## 9. 禁止事項

- `git clean -fd` / `git checkout .` / `git reset --hard` / `git stash -u` / DeltaEngine 配下への削除系コマンド
- lenient 同期条件・gap 検出条件の変更
- config スキーマの変更
- 本指示書に書かれていない仕様変更

## 10. ライブ起動前チェック(実装完了後、ライブ確認を行う場合)

1. `tasklist | findstr /i python` で DeltaEngine 配下を実行中の残存 python プロセス(前回検出 PID 15160 相当)がないことを確認。あれば終了させる
2. 起動後、dev オーバーレイの BOOK が SYNCED(緑)であること
3. `/api/stats` で `book_synced: true`・`book_snapshot_fetch_failures` の値を記録。0でない場合はログの `depth snapshot fetch failed` 行(HTTPステータス含む)を報告に添付する(451 恒久遮断の判別材料となる)
