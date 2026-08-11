# Phase 2-3 Stage 2 Task 1 最終設計材料（build_book_projection依存）

- 指示書: Phase 2-3 Stage 2 Task 1 最終設計材料（build_book_projection依存）Version 1.0
- 調査日: 2026-07-31
- 調査種別: 読み取り調査
- 調査時HEAD: `bf9512635d7a6f4d67a14d67d128fc528f6b6707`

## L1. `build_book_projection` 全文

出典: `Delta_Engine_Pro4web/webapp/book_projection.py:85-222`

```python
def build_book_projection(
    book_state: Any,
    *,
    depth_levels: int = 50,
    stale_after_ms: int = 2000,
    now_monotonic: float | None = None,
    projection_time: datetime | None = None,
) -> BookProjection:
    """Read the current state without mutating or queueing analysis updates."""
    if depth_levels < 1:
        raise ValueError("depth_levels must be >= 1")
    if stale_after_ms < 1:
        raise ValueError("stale_after_ms must be >= 1")
    projected_at = projection_time or _utc_now()
    if projected_at.tzinfo is None:
        raise ValueError("projection_time must be timezone-aware")
    projected_at = projected_at.astimezone(timezone.utc)

    if book_state is None:
        return _closed_projection(
            projection_time=projected_at,
            event_time=None,
            last_update_id=None,
            sync_state="NO_SNAPSHOT",
            depth_levels=depth_levels,
            age_ms=None,
        )

    snapshot = book_state.snapshot()
    event_time = getattr(book_state, "last_event_time", None)
    if isinstance(event_time, datetime) and event_time.tzinfo is not None:
        event_time = event_time.astimezone(timezone.utc)
    elif event_time is not None:
        event_time = None
    age_ms = book_state.age_ms(now_monotonic)

    if snapshot is None:
        state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=None,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if not getattr(book_state, "is_synchronized", False):
        state = "RESYNCING" if getattr(book_state, "gaps_detected", 0) else "NO_SNAPSHOT"
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if age_ms is None or age_ms > stale_after_ms:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="STALE",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    if event_time is None:
        return _closed_projection(
            projection_time=projected_at,
            event_time=None,
            last_update_id=snapshot.last_update_id,
            sync_state="INVALID",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    raw_bids = tuple(snapshot.bids.items())
    raw_asks = tuple(snapshot.asks.items())
    if any(
        not price.is_finite()
        or not quantity.is_finite()
        or price <= 0
        or quantity <= 0
        for price, quantity in raw_bids + raw_asks
    ):
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="INVALID",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )
    if not raw_bids or not raw_asks:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state="EMPTY",
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    bids = tuple(sorted(raw_bids, key=lambda level: level[0], reverse=True))
    asks = tuple(sorted(raw_asks, key=lambda level: level[0]))
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    if best_bid == best_ask:
        state = "LOCKED"
    elif best_bid > best_ask:
        state = "CROSSED"
    else:
        state = SYNCED
    if state != SYNCED:
        return _closed_projection(
            projection_time=projected_at,
            event_time=event_time,
            last_update_id=snapshot.last_update_id,
            sync_state=state,
            depth_levels=depth_levels,
            age_ms=age_ms,
        )

    return BookProjection(
        projection_time=projected_at,
        event_time=event_time,
        last_update_id=snapshot.last_update_id,
        sync_state=SYNCED,
        bids=bids[:depth_levels],
        asks=asks[:depth_levels],
        depth_levels=depth_levels,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=best_ask - best_bid,
        age_ms=age_ms,
    )
```

## L2. `book_state` に対する呼び出し・属性アクセス

関数開始時の `book_state is None` 分岐は `Delta_Engine_Pro4web/webapp/book_projection.py:103-111` にある。Noneでない場合に、第1引数へ行うメソッド呼出し・属性アクセスは次の出現順である。

| 順番 | 呼出し・アクセス | 引数／default | 戻り値の使われ方 | 根拠 |
|---:|---|---|---|---|
| 1 | `book_state.snapshot()` | 引数なし | `snapshot` へ格納。Noneならfail-closed分岐、非NoneならID・bids・asksを後続で使用 | `Delta_Engine_Pro4web/webapp/book_projection.py:113,121-141,143-220` |
| 2 | `getattr(book_state, "last_event_time", None)` | 属性なし時default `None` | `event_time` へ格納。timezone-aware datetimeだけUTC化し、それ以外の非None値はNoneへ変換 | `Delta_Engine_Pro4web/webapp/book_projection.py:114-118` |
| 3 | `book_state.age_ms(now_monotonic)` | `now_monotonic`（`float | None`） | `age_ms` へ格納。Noneまたは `stale_after_ms` 超過ならSTALE。projectionにも格納 | `Delta_Engine_Pro4web/webapp/book_projection.py:90,119,143-151,221` |
| 4 | `getattr(book_state, "gaps_detected", 0)` | 属性なし時default `0` | snapshotがNoneのとき、truthyならRESYNCING、falsyならNO_SNAPSHOT | `Delta_Engine_Pro4web/webapp/book_projection.py:121-130` |
| 5 | `getattr(book_state, "is_synchronized", False)` | 属性なし時default `False` | falsyならfail-closed分岐へ入る | `Delta_Engine_Pro4web/webapp/book_projection.py:132-141` |
| 6 | `getattr(book_state, "gaps_detected", 0)` | 属性なし時default `0` | 非同期状態でtruthyならRESYNCING、falsyならNO_SNAPSHOT | `Delta_Engine_Pro4web/webapp/book_projection.py:132-141` |

`snapshot` へ対する後続アクセスは `snapshot.last_update_id`（`Delta_Engine_Pro4web/webapp/book_projection.py:137,147,157,175,184,204,213`）、`snapshot.bids.items()`（同ファイル `:163`）、`snapshot.asks.items()`（同ファイル `:164`）である。

## L3. `sync_state` 分岐条件

`SYNCED` 定数とfail-closed state集合は `Delta_Engine_Pro4web/webapp/book_projection.py:15-24` に定義されている。fail-closed projectionはbids/asksを空、best bid/ask/spreadをNoneにする（同ファイル `:61-82`）。

### L3-1. 分岐の優先順

| 優先順 | 出力 `sync_state` | 条件 | 根拠 |
|---:|---|---|---|
| 1 | `NO_SNAPSHOT` | `book_state is None` | `Delta_Engine_Pro4web/webapp/book_projection.py:103-111` |
| 2 | `RESYNCING` | `snapshot is None` かつ `gaps_detected` がtruthy | `Delta_Engine_Pro4web/webapp/book_projection.py:121-130` |
| 2 | `NO_SNAPSHOT` | `snapshot is None` かつ `gaps_detected` がfalsy | `Delta_Engine_Pro4web/webapp/book_projection.py:121-130` |
| 3 | `RESYNCING` | snapshotは存在するが `is_synchronized` がfalsy、かつ `gaps_detected` がtruthy | `Delta_Engine_Pro4web/webapp/book_projection.py:132-141` |
| 3 | `NO_SNAPSHOT` | snapshotは存在するが `is_synchronized` がfalsy、かつ `gaps_detected` がfalsy | `Delta_Engine_Pro4web/webapp/book_projection.py:132-141` |
| 4 | `STALE` | `age_ms is None` または `age_ms > stale_after_ms` | `Delta_Engine_Pro4web/webapp/book_projection.py:143-151` |
| 5 | `INVALID` | `last_event_time` の正規化結果がNone。元値None、またはtimezone-awareでない非None値が該当 | `Delta_Engine_Pro4web/webapp/book_projection.py:114-118,153-161` |
| 6 | `INVALID` | bids/asks内のいずれかのpriceまたはquantityが非finite、0以下 | `Delta_Engine_Pro4web/webapp/book_projection.py:163-179` |
| 7 | `EMPTY` | bidsまたはasksの一方以上が空 | `Delta_Engine_Pro4web/webapp/book_projection.py:180-188` |
| 8 | `LOCKED` | sort後の `best_bid == best_ask` | `Delta_Engine_Pro4web/webapp/book_projection.py:190-195` |
| 9 | `CROSSED` | sort後の `best_bid > best_ask` | `Delta_Engine_Pro4web/webapp/book_projection.py:190-197` |
| 10 | `SYNCED` | sort後の `best_bid < best_ask`。先行する全fail-closed分岐を通過 | `Delta_Engine_Pro4web/webapp/book_projection.py:190-220` |

現行関数が返すstateは `SYNCED`, `NO_SNAPSHOT`, `RESYNCING`, `STALE`, `INVALID`, `EMPTY`, `LOCKED`, `CROSSED` であり、これ以外を代入する分岐は `Delta_Engine_Pro4web/webapp/book_projection.py:103-220` に該当なし。

### L3-2. `SYNCED` になるための入力上の必要条件

関数が例外ではなくprojectionを返すための引数条件として、`depth_levels >= 1`、`stale_after_ms >= 1`、`projection_time` を渡す場合はtimezone-awareであることが先に要求される（`Delta_Engine_Pro4web/webapp/book_projection.py:88-101`）。その上で `SYNCED` に到達する入力条件は次のすべてである。

1. `book_state` がNoneでない（`Delta_Engine_Pro4web/webapp/book_projection.py:103-113`）。
2. `book_state.snapshot()` がNoneでない（同ファイル `:113,121-130`）。
3. `getattr(book_state, "is_synchronized", False)` がtruthy（同ファイル `:132-141`）。
4. `book_state.age_ms(now_monotonic)` がNoneでなく、`stale_after_ms` 以下（同ファイル `:119,143-151`）。
5. `book_state.last_event_time` がtimezone-aware `datetime` であり、UTC化後もNoneでない（同ファイル `:114-118,153-161`）。
6. snapshotの全bid/ask levelについてpriceとquantityがfiniteかつ0より大きい（同ファイル `:163-179`）。
7. bidsとasksが両方とも1 level以上ある（同ファイル `:180-188`）。
8. bidsを価格降順、asksを価格昇順にした先頭価格について `best_bid < best_ask`（同ファイル `:190-200`）。

これらを通過した場合、bids/asksはそれぞれ `depth_levels` 件まで切られ、spreadは `best_ask - best_bid` となる（`Delta_Engine_Pro4web/webapp/book_projection.py:210-222`）。

## L4. `OrderBookStateManager` 公開インターフェース

`OrderBookStateManager` は `Delta_Engine_Pro4web/src/orderflow/orderbook.py:97-192` に定義され、`public interface` の区切りは同ファイル `:127` にある。

### L4-1. constructorと公開属性

| 種別 | シグネチャ／属性 | 型・初期値 | 根拠 |
|---|---|---|---|
| constructor | `OrderBookStateManager(symbol: str, *, clock: Callable[[], float] = time.monotonic) -> None` | `symbol` とmonotonic clockを受ける | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:105-110` |
| 属性 | `symbol` | `str`、constructor引数 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:107,111` |
| counter | `snapshots_applied` | `int = 0` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:120-121` |
| counter | `diffs_applied` | `int = 0` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:120-122` |
| counter | `diffs_rejected_before_snapshot` | `int = 0` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:120-123` |
| counter | `diffs_stale` | `int = 0` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:120-124` |
| counter | `gaps_detected` | `int = 0` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:120-125` |

### L4-2. 公開メソッド・propertyの全列挙

| 種別 | シグネチャ | 戻り値と実体 | 根拠 |
|---|---|---|---|
| method | `apply(update: OrderBookUpdate) -> ApplyResult` | SNAPSHOT/DIFFへ分岐し、`ApplyResult` を返す | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:129-140` |
| method | `apply_initial_sync(snapshot_update_id: int) -> None` | `_sync_id` にsnapshot IDを設定 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:142-151` |
| property | `is_initialized -> bool` | `_initialized` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:154-157` |
| property | `is_synchronized -> bool` | `_initialized and _sync_id is None` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:159-162` |
| property | `last_event_time -> Optional[datetime]` | `_last_event_time` | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:164-167` |
| method | `age_ms(now_monotonic: Optional[float] = None) -> Optional[int]` | 未適用ならNone。それ以外は現在monotonicとの差を非負msへ変換 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:169-174` |
| method | `snapshot() -> Optional[OrderBookSnapshot]` | 未初期化ならNone。それ以外はsymbol/ID/bids copy/asks copy/event timeを持つsnapshot | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:176-186` |
| method | `bid_quantity_at(price: Decimal) -> Decimal` | priceをDecimal化してbid数量、欠落時0 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:188-189` |
| method | `ask_quantity_at(price: Decimal) -> Decimal` | priceをDecimal化してask数量、欠落時0 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py:191-192` |

`OrderBookSnapshot` の戻り値型は `symbol: str`, `last_update_id: int`, `bids: dict[Decimal, Decimal]`, `asks: dict[Decimal, Decimal]`, `event_time: Optional[datetime]` である（`Delta_Engine_Pro4web/src/orderflow/orderbook.py:69-77`）。`ApplyResult` は `applied`, `reinitialized`, `gap_detected` の各boolを持つ（同ファイル `:86-90`）。

### L4-3. `build_book_projection` 依存との対応

| `build_book_projection` 側 | Manager側実体 | 根拠 |
|---|---|---|
| `book_state.snapshot()` | `snapshot() -> Optional[OrderBookSnapshot]` | `Delta_Engine_Pro4web/webapp/book_projection.py:113`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:176-186` |
| `book_state.last_event_time` | property `last_event_time -> Optional[datetime]` | `Delta_Engine_Pro4web/webapp/book_projection.py:114`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:164-167` |
| `book_state.age_ms(now_monotonic)` | `age_ms(Optional[float]) -> Optional[int]` | `Delta_Engine_Pro4web/webapp/book_projection.py:119`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:169-174` |
| `book_state.gaps_detected` | 公開counter `int`。gap検出時にincrement | `Delta_Engine_Pro4web/webapp/book_projection.py:122,133`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:125,253-268` |
| `book_state.is_synchronized` | property `bool` | `Delta_Engine_Pro4web/webapp/book_projection.py:132`; `Delta_Engine_Pro4web/src/orderflow/orderbook.py:159-162` |

## L5. envelope と `d2s` のpayload出力仕様

### L5-1. envelope

`envelope(msg_type: str, time_: datetime, symbol: str, payload: dict) -> dict` は次の4キーを返す（`Delta_Engine_Pro4web/webapp/push_broker.py:38-45`）。

| キー | JSON型 | 値 | 根拠 |
|---|---|---|---|
| `v` | number | `PAYLOAD_VERSION`。現値1 | `Delta_Engine_Pro4web/webapp/push_broker.py:18,38-40` |
| `type` | string | `msg_type`。book送信では `BOOK_UPDATE` | `Delta_Engine_Pro4web/webapp/push_broker.py:41,264-266` |
| `time` | string | `time_` をUTC ISO文字列化。book送信では `projection.projection_time` | `Delta_Engine_Pro4web/webapp/push_broker.py:42,264-267` |
| `symbol` | string | brokerの `self.symbol` | `Delta_Engine_Pro4web/webapp/push_broker.py:43,151,264-267` |
| `payload` | object | 下表のbook payload | `Delta_Engine_Pro4web/webapp/push_broker.py:44,268-293` |

message dictは `_broadcast` で `json.dumps` され、`ws.send_text` へ渡る（`Delta_Engine_Pro4web/webapp/push_broker.py:188-195`）。

### L5-2. `d2s`

`d2s(v: Optional[Decimal]) -> Optional[str]` はNoneをNoneのまま返し、Decimalまたはintだけを `str(v)` へ変換する。それ以外はTypeErrorである（`Delta_Engine_Pro4web/webapp/push_broker.py:21-27`）。適用箇所はbid/askのpriceとqty（同ファイル `:280-286`）、SYNCED時のbest bid/ask/spread（同ファイル `:289-291`）である。

### L5-3. book payloadの最終キーと型

| キー | JSON型 | 値・null条件 | 根拠 |
|---|---|---|---|
| `book_stream_id` | string | broker生成UUID文字列 | `Delta_Engine_Pro4web/webapp/push_broker.py:160,269` |
| `book_sequence` | number（int） | `book_updates_broadcast + 1` | `Delta_Engine_Pro4web/webapp/push_broker.py:161,261,270,296` |
| `event_time` | string または null | 非NoneならUTC ISO文字列 | `Delta_Engine_Pro4web/webapp/push_broker.py:271-274` |
| `projection_time` | string | UTC ISO文字列 | `Delta_Engine_Pro4web/webapp/push_broker.py:275-277` |
| `last_update_id` | number（int）または null | `projection.last_update_id` | `Delta_Engine_Pro4web/webapp/book_projection.py:37`; `Delta_Engine_Pro4web/webapp/push_broker.py:278` |
| `sync_state` | string | `projection.sync_state` | `Delta_Engine_Pro4web/webapp/book_projection.py:38`; `Delta_Engine_Pro4web/webapp/push_broker.py:279` |
| `bids` | array | SYNCED時 `{price: string, qty: string}` の配列。非SYNCED時空配列 | `Delta_Engine_Pro4web/webapp/push_broker.py:254,262,280-283` |
| `asks` | array | SYNCED時 `{price: string, qty: string}` の配列。非SYNCED時空配列 | `Delta_Engine_Pro4web/webapp/push_broker.py:254,263-286` |
| `depth_levels` | number（int） | `projection.depth_levels` | `Delta_Engine_Pro4web/webapp/book_projection.py:41`; `Delta_Engine_Pro4web/webapp/push_broker.py:288` |
| `best_bid` | string または null | SYNCED時Decimalを`d2s`、非SYNCED時null | `Delta_Engine_Pro4web/webapp/push_broker.py:254,289` |
| `best_ask` | string または null | SYNCED時Decimalを`d2s`、非SYNCED時null | `Delta_Engine_Pro4web/webapp/push_broker.py:254,290` |
| `spread` | string または null | SYNCED時Decimalを`d2s`、非SYNCED時null | `Delta_Engine_Pro4web/webapp/push_broker.py:254,291` |
| `age_ms` | number（int）または null | `projection.age_ms` | `Delta_Engine_Pro4web/webapp/book_projection.py:45`; `Delta_Engine_Pro4web/webapp/push_broker.py:292` |

指定列挙の12キーに加えて、現行payloadは `age_ms` も出力する（`Delta_Engine_Pro4web/webapp/push_broker.py:268-293`）。SYNCED projectionではbest bid/ask/spreadがすべて非Noneであることを送信前に要求する（同ファイル `:250-260`）。

## 参照ファイル識別値

下表は調査時のファイルbytesに対するSHA-256である。3つの実装ファイルは調査時HEADとの差分がない。

| ファイル | SHA-256 | byte | LF | CR |
|---|---:|---:|---:|---:|
| `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` | `F14AA1002269E0AF1F43B28AF5E7356C118E19BFF5DF6C45B081530153DDA032` | 81936 | 1274 | 1190 |
| `Delta_Engine_Pro4web/webapp/book_projection.py` | `591BBB8A43946FCDE43CD04B42026BD03DA1BE55135CA08491D295DB8E755D99` | 9154 | 299 | 0 |
| `Delta_Engine_Pro4web/src/orderflow/orderbook.py` | `291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05` | 11295 | 290 | 0 |
| `Delta_Engine_Pro4web/webapp/push_broker.py` | `D74F0F13B092055E7FA93D604A09E27278401B87D84444D1CB83B4C03AAF19BD` | 25453 | 593 | 6 |

## Git証跡

### `git rev-parse HEAD`

```text
bf9512635d7a6f4d67a14d67d128fc528f6b6707
```

### `git status --porcelain -- Delta_Engine_Pro4web/`

```text
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
```

上記は調査開始時から存在するuntracked directoryであり、tracked `M` は出力されていない。

### `git diff --cached --name-only`

```text
（出力なし）
```

`CACHED_PATH_COUNT=0`
