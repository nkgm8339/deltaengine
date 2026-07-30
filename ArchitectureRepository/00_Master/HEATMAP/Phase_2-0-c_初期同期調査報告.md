# [完了] Phase 2-0-c 初期同期調査

- 調査日: 2026-07-29
- 調査方法: 現在の作業ツリーのコード読取のみ
- ライブ接続: なし
- テスト実行: なし
- 実装・本体変更: なし
- 記録データ変更: なし
- 本調査で作成したもの: 本報告書1ファイルのみ
- 報告書保存先:
  `ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-c_初期同期調査報告.md`

## 結論

現行コードは「REST snapshot取得後にWebSocket購読を開始する」という明示的な
直列順序ではない。`LivePipeline.run_async()`はconnector task、receiver task、
snapshot supervisor taskの順にtaskを生成するが、その間に購読完了を待つ
`await`や同期barrierはなく、3 taskは最初のyield後に同一asyncio loop上で競合して進む。

したがって現行の実態は次のraceである。

- WebSocket接続・購読・最初のdepthUpdate受信がREST snapshotより先になれば、
  そのdiffはraw recorderへ先に記録される。
- REST snapshot応答がWebSocket購読・最初のdepthUpdateより先になれば、
  snapshotが最初に記録され、そのsnapshotの`lastUpdateId`以後から
  最初に受信できたdiffの`U`までが記録不能になる。

Phase 2-0-bの両captureは後者だった。コードには「depth diffを1件以上受信し、
同期用bufferが動き始めたことを確認してからREST snapshotを取得する」barrierも、
buffer内から`U <= u_snapshot + 1 <= u`を探して検証するstate machineも存在しない。
`OrderBookStateManager.apply_initial_sync()`後のlenient受理がライブ表示を初期化するだけで、
記録の完全な再構築可能性は保証していない。

是正はLive取得層に、depth専用の初期同期state machineを追加する必要がある。
記録順制御とstrict接続検証は取得層、manifest同期情報は
`DepthHistoryRecorder`、録画時rotation閾値はWebApp起動配線に変更が必要である。
本報告では計画のみを提示し、実装していない。

## §3 タスクA: 現行初期同期手順の現物特定

### §3.1 INITIAL_BOOK_SYNC snapshotの生成箇所

#### REST取得

- ファイル:
  `Delta_Engine_Pro4web/src/acquisition/binance_rest.py`
- 関数:
  `async def fetch_depth_snapshot(symbol: str, limit: int = 1000, base_url: str = _DEFAULT_BASE_URL) -> dict`
- 定義: 49〜79行
- HTTP GET開始: 63〜64行
- JSON応答取得: 70行
- 生REST dict返却: 75行

```python
  49: async def fetch_depth_snapshot(
  50:     symbol: str,
  51:     limit: int = 1000,
  52:     base_url: str = _DEFAULT_BASE_URL,
  53: ) -> dict:
  59:     url = f"{base_url}{_DEPTH_PATH}"
  60:     params = {"symbol": symbol, "limit": limit}
  63:         async with aiohttp.ClientSession(timeout=timeout) as session:
  64:             async with session.get(url, params=params) as response:
  70:                 data = await response.json()
  75:                 return data
```

#### REST dictからdepthSnapshot行への変換

- ファイル:
  `Delta_Engine_Pro4web/src/acquisition/binance_rest.py`
- 関数:
  `def rest_to_depth_event(raw_rest: dict, symbol: str) -> dict`
- 定義: 124〜146行
- `e="depthSnapshot"`: 140行
- `u=lastUpdateId`: 143行
- bid/askはREST文字列を素通し: 144〜145行
- `E`はRESTに時刻がない場合、ローカル受信時刻: 135〜138行

```python
 124: def rest_to_depth_event(raw_rest: dict, symbol: str) -> dict:
 135:     # Binance Futures REST depth payloads provide lastUpdateId/bids/asks but
 136:     # no event timestamp. Supply the local receipt time for the normalizer's
 137:     # canonical event_time; it is metadata only and never drives book ordering.
 138:     event_time_ms = raw_rest.get("E", raw_rest.get("T", time.time_ns() // 1_000_000))
 139:     return {
 140:         "e": "depthSnapshot",
 141:         "s": symbol,
 142:         "E": event_time_ms,
 143:         "u": raw_rest["lastUpdateId"],
 144:         "b": raw_rest["bids"],
 145:         "a": raw_rest["asks"],
 146:     }
```

#### INITIAL_BOOK_SYNC理由の決定と記録

- ファイル: `Delta_Engine_Pro4web/src/pipeline.py`
- 関数:
  `async def _book_resync_supervisor(...) -> None`
- 定義: 191〜238行
- REST取得: 210行
- snapshot形式変換: 211行
- normalizer変換: 212行
- 初回理由`INITIAL_BOOK_SYNC`: 215〜218行
- snapshotの板state適用: 221行
- lenient初期同期mode開始: 222行
- 初回後に`synced_once=True`: 228行

```python
 204:     while True:
 205:         if book_state.is_initialized:
 206:             consecutive_failures = 0
 207:             await sleep(_BOOK_HEALTH_POLL_SEC)
 208:             continue
 209:         try:
 210:             raw_snap = await fetch_snapshot(symbol)
 211:             depth_evt = rest_to_depth_event(raw_snap, symbol)
 212:             update = normalizer.process_depth(depth_evt)
 213:             if update is None:
 214:                 raise ValueError("depth snapshot normalization returned None")
 215:             if recorder is not None:
 216:                 reason = "BOOK_RESYNC" if synced_once else "INITIAL_BOOK_SYNC"
 217:                 if hasattr(recorder, "write_snapshot"):
 218:                     recorder.write_snapshot(depth_evt, reason=reason)
 219:                 else:
 220:                     recorder.write(depth_evt)
 221:             book_state.apply(update)
 222:             book_state.apply_initial_sync(update.final_update_id)
 228:             synced_once = True
```

`_capture_reason`自体は同じファイルの`_RecorderFanout.write_snapshot()`が、
raw observation tap向けのcopyにだけ付加する。

- クラス: `_RecorderFanout`
- メソッド:
  `def write_snapshot(self, obj: dict[str, Any], *, reason: str) -> None`
- 定義: 120〜132行
- `_capture_reason`付与: 125〜126行
- raw observation recorderへの書込: 128行

```python
 120:     def write_snapshot(self, obj: dict[str, Any], *, reason: str) -> None:
 121:         """Keep legacy bytes stable while adding acquisition reason to research raw."""
 122:         if self._legacy is not None:
 123:             self._legacy.write(obj)
 124:         if self._observation is not None:
 125:             observation_row = dict(obj)
 126:             observation_row["_capture_reason"] = reason
 127:             try:
 128:                 self._observation.write(observation_row)
```

呼出し順は次のとおり。

1. `_book_resync_supervisor()` 210行:
   `await fetch_depth_snapshot(symbol)`
2. `binance_rest.py` 63〜75行:
   REST GET、JSON decode、raw dict返却
3. `pipeline.py` 211行:
   `rest_to_depth_event(...)`
4. 212行: `normalizer.process_depth(...)`
5. 216行: 初回なら`reason="INITIAL_BOOK_SYNC"`
6. 218行: `_RecorderFanout.write_snapshot(...)`
7. `_RecorderFanout` 125〜128行:
   observation用copyへ`_capture_reason`を付けて
   `DepthHistoryRecorder.write()`へ渡す
8. supervisor 221〜222行:
   snapshotを板stateへ適用し、lenient初期同期modeへ入る

### §3.2 depth stream購読開始とraw_recorderへの流し込み

#### 購読streamの設定

- `Delta_Engine_Pro4web/config/config.yaml`: 22〜25行
- depth stream: 24行の`btcusdt@depth@100ms`

```yaml
  22:   subscribe_streams:
  23:     - "btcusdt@trade"
  24:     - "btcusdt@depth@100ms"
  25:     - "btcusdt@forceOrder"
```

#### ConnectorとReceiverの構築

- `Delta_Engine_Pro4web/src/pipeline.py`
- `LivePipeline.run_async()`: 1139行
- connector構築: 1166〜1177行
- legacy/raw recorder fanout構築: 1178〜1183行
- receiverへrecorderを配線: 1184〜1189行

```python
1166:         connector = ExchangeConnector(
1167:             url=self.ws_url,
1168:             subscribe_streams=self.subscribe_streams,
1169:             out_queue=out_q,
1170:             connect=connect,
1177:         )
1178:         legacy_recorder = JsonlRecorder(record_path) if record_path else None
1179:         recorder = (
1180:             _RecorderFanout(legacy_recorder, raw_recorder)
1181:             if legacy_recorder is not None or raw_recorder is not None
1182:             else None
1183:         )
1184:         receiver = DataReceiver(
1185:             out_q,
1186:             norm_q,
1187:             recorder=recorder,
1188:             validate=lambda m: default_validate(m) and event_filter(m),
1189:         )
```

#### WebSocket接続とSUBSCRIBE

- `Delta_Engine_Pro4web/src/acquisition/binance_ws.py`
- `make_binance_connect()`: 132〜167行
- socket接続: 151〜155行
- SUBSCRIBE frame作成・送信: 157〜160行
- stream返却: 165行

```python
 151:     async def connect(url: str, streams: list[str]) -> AsyncIterator[dict]:
 153:             ws = await connector(url, ping_interval=ping_interval, ping_timeout=ping_timeout)
 157:         subscribe = {"method": "SUBSCRIBE", "params": list(streams), "id": subscribe_id}
 159:             await ws.send(json.dumps(subscribe))
 164:         logger.info("binance subscribed streams=%s url=%s", streams, url)
 165:         return BinanceStream(ws)
```

#### 受信イベントのqueue投入

- `Delta_Engine_Pro4web/src/acquisition/connector.py`
- `ExchangeConnector.run()`: 133〜180行
- `_open()`完了後にSUBSCRIBEDへ遷移: 159〜162行
- transport受信: 165行
- `out_q`投入: 167行

```python
 159:             # connected + subscribed
 160:             self._set_state(ConnectionState.CONNECTED)
 161:             self._set_state(ConnectionState.SUBSCRIBED)
 165:                 async for message in transport:
 166:                     self.messages_out += 1
 167:                     await self._out.put(message)
```

#### raw_recorder書込

- `Delta_Engine_Pro4web/src/acquisition/receiver.py`
- `DataReceiver.run()`: 84〜102行
- `out_q`から取得: 87行
- validate: 90〜93行
- raw recorder書込: 99〜100行
- その後`norm_q`へ転送: 101行

```python
  84:     async def run(self) -> None:
  87:             message = await self._source.get()
  90:             if not self._validate(message):
  99:             if self._recorder is not None:
 100:                 self._recorder.write(message)
 101:             await self._destination.put(message)
 102:             self.forwarded += 1
```

raw observation recorderはWebApp lifespanで作られ、LivePipelineに渡される。

- `Delta_Engine_Pro4web/webapp/main.py`
- `DepthHistoryRecorder`生成: 124〜136行
- raw tap選択: 375〜376行
- LivePipelineへ渡す: 377〜379行

```python
 124:     persistent_enabled = os.getenv("PERSISTENT_DEPTH_HISTORY_ENABLED", "false").lower() == "true"
 126:     depth_history_enabled = os.getenv("DEPTH_HISTORY_ENABLED", "false").lower() == "true"
 127:     depth_history_recorder = (
 128:         SafeRecorder(
 129:             DepthHistoryRecorder(
 130:                 os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw"),
 131:                 config.market.symbol,
 132:             )
 133:         )
 134:         if depth_history_enabled
 135:         else None
 136:     )
 375:         _raw_taps = [t for t in (hook_capture, depth_history_recorder) if t is not None]
 376:         _raw_tap = _raw_taps[0] if len(_raw_taps) == 1 else (RecorderTee(_raw_taps) if _raw_taps else None)
 377:         pipeline_task = asyncio.create_task(
 378:             pipeline.run_async(raw_recorder=_raw_tap)
 379:         )
```

### §3.3 現行時系列と欠落区間

#### task生成順

`LivePipeline.run_async()`のtask生成は次の順である。

- `pipeline.py:1482`: connector task
- `pipeline.py:1483`: receiver task
- `pipeline.py:1491〜1498`: snapshot supervisor task
- `pipeline.py:1515`: main consumerが初めてqueue待ちでyield

```python
1481:         loop = asyncio.get_event_loop()
1482:         connector_task = asyncio.create_task(connector.run())
1483:         receiver_task = asyncio.create_task(receiver.run())
1485:         # Order book sync is owned by the resync supervisor (ADR-010)
1489:         book_supervisor_task: Optional[asyncio.Task] = None
1490:         if fetch_snapshot is not None:
1491:             book_supervisor_task = asyncio.create_task(_book_resync_supervisor(
1492:                 symbol=self.symbol,
1493:                 book_state=book_state,
1494:                 normalizer=normalizer,
1495:                 fetch_snapshot=fetch_snapshot,
1496:                 counters=self.book_resync_counters,
1497:                 recorder=recorder,
1498:             ))
1515:                     raw = await asyncio.wait_for(norm_q.get(), timeout=timeout)
```

`create_task()`の順はtask生成順にすぎず、connectorのWebSocket handshakeと
SUBSCRIBE完了を待ってからsupervisorを開始するbarrierではない。
connectorはsocket接続を`await`し、supervisorはREST GETを`await`するため、
ネットワーク応答順で先着経路が変わる。

#### 実行経路

```text
webapp lifespan
  └─ LivePipeline.run_async(raw_recorder=...)
       ├─ recorder / out_q / norm_q / connector / receiver を構築
       ├─ task 1: ExchangeConnector.run()
       │    └─ WebSocket接続 → SUBSCRIBE送信 → depthUpdate受信
       │         └─ out_q.put()
       ├─ task 2: DataReceiver.run()
       │    └─ out_q.get() → validate → recorder.write(depthUpdate)
       │         └─ norm_q.put()
       ├─ task 3: _book_resync_supervisor()
       │    └─ REST snapshot取得 → recorder.write_snapshot(INITIAL_BOOK_SYNC)
       │         └─ book_state.apply() → apply_initial_sync()
       └─ main consumer
            └─ norm_q.get() → process_depth() → book_state.apply(diff)
```

#### 欠落が発生する区間

Phase 2-0-bの現物ではsnapshot行が各segmentの1行目、最初のdepthUpdateが2行目だった。
これはtask 3のsnapshot記録がtask 1→2の最初のdiff記録より先着したことを示す。

欠落区間は、取引所がREST snapshotの`lastUpdateId`を確定した時点の直後から、
WebSocket購読が実際に配信を開始し、最初のdepthUpdateが
`DataReceiver` 99〜100行で記録される直前までである。

現行コードはこの区間の前にstream購読完了・diff受信開始を保証していないため、
その間の取引所diffを後から取得できない。Phase 2-0-bで測定された
227ms／約10,175 update IDと193ms／約14,300 update IDは、このraceで
REST snapshotが先着した側の欠落である。

注意: `rest_to_depth_event()`がsnapshotの`E`へ入れる値は
`binance_rest.py:135〜138`のローカル受信時刻であり、snapshotの取引所確定時刻ではない。
したがってコードだけから227msを再算出することはできない。時間・ID差の量は
Phase 2-0-b現物測定、欠落区間の発生機序は上記コードで確定する。

### §3.4 snapshot前diffを保持するbufferの有無

**同期検証用bufferは存在しない。**

存在するqueueは次の2個である。

- `pipeline.py:1163`:
  `out_q = BoundedEventQueue(..., name="ws_out")`
- `pipeline.py:1164`:
  `norm_q = BoundedEventQueue(..., name="receiver_out")`

`BoundedEventQueue`は
`Delta_Engine_Pro4web/src/acquisition/event_queue.py:24〜57`の一般的なstage間queueで、
snapshot IDとの対応を追跡しない。既定policyは`drop_oldest_log`である。

```python
  24: class BoundedEventQueue:
  27:     def __init__(
  29:         maxsize: int,
  30:         overflow_policy: str = DROP_OLDEST_LOG,
  37:         self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
  42:     async def put(self, item: Any) -> None:
  47:         if self._queue.full():
  49:                 self._queue.get_nowait()
  52:             self.overflow_count += 1
  57:         self._queue.put_nowait(item)
```

これらは短時間イベントを保持し得るが、次の機能がないため初期同期bufferとは扱えない。

- WebSocket depthを1件受信するまでREST snapshot取得を待つbarrier
- depthUpdateだけを同期epoch単位で保持するbuffer
- bufferから`U <= snapshot_u + 1 <= u`を探索する処理
- snapshotが古すぎる場合の再取得判定
- bridge diff以後の`pu`チェーン検証
- buffer overflow時にsync不成立とするfail-closed処理
- accepted snapshotとbridge diffをmanifestへ結び付ける処理

また`DataReceiver`はraw recorderへ書いた後に`norm_q`へ渡す
（`receiver.py:99〜101`）。したがって`norm_q`は「記録前diffのbuffer」でもない。

`OrderBookStateManager`にもraw diff列のbufferはない。
`orderbook.py:233〜242`は`apply_initial_sync()`後、最初のnon-stale diffを
bridge条件の再検査なしで受理するだけである。

```python
 233:         # Initial sync mode: accept first non-stale diff (lenient — Binance Futures
 234:         # batches can start at first_update_id > snap_id+1 due to connection timing).
 235:         if self._sync_id is not None:
 236:             self._sync_id = None
 237:             self._apply_levels(self._bids, update.bids)
 238:             self._apply_levels(self._asks, update.asks)
 239:             self._last_update_id = update.final_update_id
 242:             return ApplyResult(applied=True, reinitialized=False, gap_detected=False)
```

### §3.5 gap後のsnapshot再取得経路

**経路は存在する。**

1. Live main consumerがdepthUpdateを
   `pipeline.py:1535〜1545`でnormalizeし、
   `book_state.apply(update)`へ渡す。
2. `OrderBookStateManager._apply_diff()`は
   `orderbook.py:244〜252`で`pu`優先のgap判定を行う。
3. gap時は`orderbook.py:253〜268`でbid/ask、last ID、sync IDを消去し、
   `_initialized=False`へ戻して`gap_detected=True`を返す。
4. supervisorは`pipeline.py:205`の
   `book_state.is_initialized`を1秒周期で監視している。
5. Falseを検出すると`pipeline.py:210`でREST snapshotを再取得する。
6. 初回完了後は`synced_once=True`なので、
   `pipeline.py:216`で理由を`BOOK_RESYNC`にする。
7. `_RecorderFanout.write_snapshot()`が
   `_capture_reason: "BOOK_RESYNC"`をraw recorderへ記録する。
8. snapshot適用後、再び`apply_initial_sync()`のlenient modeへ入る。

gap処理の現物:

```python
 244:         # Gap: sequence discontinuity.
 247:         gap = False
 248:         if update.previous_final_update_id is not None:
 249:             gap = update.previous_final_update_id != self._last_update_id
 250:         elif update.first_update_id is not None:
 251:             expected = self._last_update_id + 1
 252:             gap = update.first_update_id != expected
 253:         if gap:
 255:             self._bids = {}
 256:             self._asks = {}
 257:             self._last_update_id = None
 258:             self._sync_id = None
 261:             self._initialized = False
 262:             self.gaps_detected += 1
 268:             return ApplyResult(applied=False, reinitialized=False, gap_detected=True)
```

Phase 2-0-bの2 captureに`INITIAL_BOOK_SYNC`以外がなかったことは、
このコード経路が存在しないことを意味しない。capture中に
`OrderBookStateManager`がgapを検出して再取得へ進む事象がなかったことを意味する。

ただしgap再同期にも初期同期と同じstrict bridge検証・同期bufferがなく、
再取得中も同じraceとlenient受理が発生する。

### §3.6 DepthHistoryRecorder側の受け口

- ファイル:
  `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py`
- クラス:
  `DepthHistoryRecorder`（38行）
- constructor:
  `__init__(root, symbol, max_bytes=..., flush_interval_sec=..., clock=...)`
  （41〜48行）
- snapshot/diff共通受け口:
  `def write(self, obj: dict) -> None`（77行）
- close:
  `def close(self) -> None`（95行）
- segment/manifest確定:
  `_close_segment(reason)`（98〜121行）

```python
  38: class DepthHistoryRecorder:
  41:     def __init__(
  43:         root: str | Path,
  44:         symbol: str,
  45:         max_bytes: int = _DEFAULT_MAX_BYTES,
  46:         flush_interval_sec: float = _FLUSH_INTERVAL_SEC,
  77:     def write(self, obj: dict) -> None:
  78:         line = (
  79:             json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  80:             + "\n"
  81:         ).encode("utf-8")
  82:         if self._handle is None:
  83:             self._open()
  84:         self._handle.write(line)
  85:         self._hasher.update(line)
  86:         self._count += 1
  87:         self._bytes += len(line)
  92:         if self._bytes >= self.max_bytes:
  93:             self._close_segment("rotate")
```

`DepthHistoryRecorder`は`e`を判別せず、snapshotもdiffも同じ`write(dict)`で
JSONL化する。`_capture_reason`付与はrecorder外の`_RecorderFanout`が行う。
価格・数量変換も行わない。

wrapperの受け口:

- `SafeRecorder.write(obj)`:
  `depth_history_recorder.py:136〜148`
- `RecorderTee.write(obj)`:
  `depth_history_recorder.py:170〜172`
- `RecorderTee.close()`はno-op:
  174〜175行

判断:

- stream先行、diff buffer、bridge探索、snapshot再取得上限は取得層の責務であり、
  JSONL serializer本体へ持ち込むべきではない。
- pre-sync diffに再構築用metadataを付けるだけなら、
  recorderへ渡す前にdictをcopy/decorateできるため、serializerの`write()`変更は不要。
- しかし§4要件のmanifest同期結果追加には、
  現行manifestが固定7項目
  （`depth_history_recorder.py:106〜118`）で外部metadata受け口もないため、
  recorder側の変更が必要。
- `SafeRecorder`と`RecorderTee`にも同期metadata更新を安全にforwardする契約が必要。

現行manifest:

```python
 106:         manifest = {
 107:             "schema_revision": _SCHEMA_REVISION,
 108:             "symbol": self.symbol,
 109:             "record_count": self._count,
 110:             "byte_size": self._bytes,
 111:             "sha256": self._hasher.hexdigest(),
 112:             "closed_reason": reason,
 113:             "started_at": self._started_at,
 114:             "closed_at": _utc_stamp(),
 115:         }
```

## §4 タスクB: 是正計画

### §4.0 是正方針

Live取得層へ、REST supervisor単体ではなく
「depth受信開始 → buffer → snapshot候補取得 → bridge検証 → 適用」の
state machineを置く。板stateを書き換える所有者はLive main consumerに集約し、
REST fetch taskはsnapshot候補をqueue経由で返すだけにする。

推奨state:

```text
WAITING_FOR_FIRST_DEPTH
  → FETCHING_INITIAL_SNAPSHOT
  → VERIFYING_INITIAL_BRIDGE
  → SYNCED
  → (gap) RESYNC_BUFFERING
  → FETCHING_RESYNC_SNAPSHOT
  → VERIFYING_RESYNC_BRIDGE
  → SYNCED

上限到達:
  → SYNC_FAILED（板はfail-closed、記録manifestはfalse、明示error）
```

### §4.1 depth受信・bufferをRESTより先に開始

計画:

1. connector、receiver、raw recorderを現行どおり先に起動する。
2. depth専用同期coordinatorをreceiver/main consumer経路へ接続する。
3. 最初の有効`depthUpdate`を受けるまでREST snapshot taskを開始しない。
4. 最初のdepthUpdateを含め、同期確立までのdepthUpdateを
   full raw dictのまま、単一loop上の専用bufferへ保持する。
5. raw recorderへの書込はbufferとは独立して到着時に継続する。
6. trade、forceOrder、Flow Price Response等の既存経路は待たせない。

最初のdepthUpdate受信をbarrierにすれば、
「購読frameを送っただけで配信開始前」というraceを避けられる。
`ExchangeConnector.state == SUBSCRIBED`だけではdepth配信開始の証明にならないため、
最初の有効depth実データを開始条件にする。

同期bufferは一般`out_q`/`norm_q`と分離する。buffer上限超過、queue overflow、
JSON/ID欠損が起きた場合はそのsnapshot候補を検証済みにせず、
理由付きでattempt失敗とする。

### §4.2 strict bridge検証・snapshot再取得・上限

各同期epochで次を行う。

1. depth buffer開始済みを確認する。
2. REST snapshot候補を取得し、候補ごとにattempt番号を付けて記録する。
3. `target = snapshot_u + 1`を整数演算で作る。
4. buffer内を到着順に走査し、
   `U <= target <= u`を満たす最初のdiffをbridgeとする。
5. bufferの最新`u`がtarget未満なら、直ちにFAILにせず次のdiffを待つ。
6. bufferがtargetを通過したのにbridgeがなければsnapshot候補をrejectし、
   REST snapshotを再取得する。
7. bridge以後のbuffered diffについて`pu(後) == u(前)`を検証する。
8. strict検証PASS後にだけsnapshotを板stateへ適用し、
   `apply_initial_sync(snapshot_u)`を呼んで、外部検証済みbridgeを最初のdiffとして渡す。
   これによりmanagerのlenient branchを「未検証diffの穴隠し」には使わない。
9. bridge以後を到着順に適用し、producerへ同じ順で1回だけ通知する。
10. 初期同期とBOOK_RESYNCの双方で同じstate machineを使う。

attempt上限は明示的な正整数設定とする。上限到達時:

- `sync_verified=false`
- failure reason、attempt数、最後のsnapshot_u、buffer範囲をmanifestへ残す
- Health/Statsへ同期失敗を明示
- 板stateは未初期化のfail-closedを維持
- raw recording segmentを`sync_failed`理由で確定する
- market trade/CVD等の独立経路は継続するが、その録画sessionを
  「再構築可能」と扱わない
- silent infinite retryまたはlenient適用はしない

HTTP fetch errorの既存backoff（5、10、30秒）とbridge不成立attemptを区別して計数する。
上限と失敗条件はfixtureで固定可能にする。

### §4.3 到着順・全量記録とpre-sync diffの識別

pre-sync diffを捨てない。DataReceiverが受けた時点でこれまでどおりraw recorderへ書く。
同期bufferは適用待ち用のmemory copyであり、raw記録の代替ではない。

再構築側の識別方式として、observation用copyだけへ次を追加する案を推奨する。

- `_capture_phase`:
  `PRE_SYNC` / `SYNCED` / `RESYNC_BUFFERING`
- `_sync_epoch`:
  起動・各gap再同期を区別する正整数
- snapshot候補:
  既存`_capture_reason`に加え`_sync_attempt`

bridge diffはすでにraw到着時に記録済みになり得るため、過去行を上書きしない。
accepted snapshotとbridgeの対応はmanifestへ
`snapshot_u`、bridge `U/u/pu`、epoch、attemptを記録し、
Phase 2-1再構築器が同epochのpre-sync行からbridgeを特定する。

候補snapshotをrejectした場合も削除せず記録する。
manifestのattempt結果でaccepted/rejectedを区別する。
これによりADR-011の全量性と、append-only契約を両立する。

既存WS dictそのものは変更せずcopyをdecorateする。
価格・数量は文字列のまま、ID・attempt・epochは整数、
`float()`は使用しない。

### §4.4 manifest同期情報

`RAW_DEPTH_HISTORY_V1`の固定manifestを拡張し、schema revisionを更新する。
少なくとも次を保持する。

- `sync_verified: true/false`
- `sync_state_at_close`
- `sync_epoch`
- `sync_attempt_count`
- accepted `sync_snapshot_u`
- accepted bridge
  `sync_first_diff_U` / `sync_first_diff_u` / `sync_first_diff_pu`
- `pre_sync_record_count`
- `sync_failure_reason`（成功時null）
- 複数snapshot候補・BOOK_RESYNCを保持する`sync_checks`配列
  - reason
  - epoch
  - attempt
  - snapshot_u
  - bridge U/u/pu
  - result
  - failure reason

1 segment中に初期同期と複数BOOK_RESYNCがあり得るため、
単一scalarだけでは履歴を表現できない。top-levelの最終状態と、
boundedな`sync_checks`配列の両方を持つ。

rotationがsync確立前に発生したsegmentは`sync_verified=false`、
次segmentで確立した場合はそのsegmentのmanifestにPASS情報を持たせる。
どのsegmentも後から書き換えない。

### §4.5 ADR-003・float禁止・既存機能無劣化

- threadは追加しない。
- REST fetchは既存aiohttp coroutineを使用する。
- coordinator、buffer、snapshot結果通知は単一asyncio loopと
  `asyncio.Queue`/taskで構成する。
- 板stateのapplyは1 coroutineへ集約し、snapshot taskとmain consumerが
  同じmutable stateを別々に更新しない。
- recorderの同期write、1秒周期flush、segment close時fsyncは維持する。
- 価格・数量は文字列を維持し、`Decimal`経由の再文字列化も不要。
- `float()`を新規使用しない。
- retry、max_bytes、epoch、IDはstrictな整数として検証する。
- CVD、Footprint、Imbalance、Absorption、Flow Price Response、
  OI、3段チャート、8パターンの計算・payloadは変更しない。
- strict sync待機中は板投影のみfail-closedとし、trade系処理を止めない。

### §4.6 Replay/Live二重構造への影響

#### Live

変更対象。現在の
`_book_resync_supervisor()`によるsnapshot即適用を、
buffer/strict検証coordinator経由へ置き換える。
初期同期完了までの板表示開始が数百ms程度遅れる可能性があるが、
誤った板を表示するよりfail-closedを優先する。

#### Replay

`ReplayPipeline.run()`は
`pipeline.py:468〜469`でファイルを全読込し、
646〜665行で記録順にsnapshot/diffを直接`book_state.apply()`する。
REST fetch、WebSocket、resync supervisorを持たない。

```python
 468:     def run(self, data_path: str | Path) -> ReplayStats:
 469:         raws = ReplaySource(data_path).read_all()
 646:         for raw in raws:
 650:             kind = normalizer.classify_raw(raw)
 651:             if kind == "depth":
 652:                 update = normalizer.process_depth(raw)
 654:                     apply_result = book_state.apply(update)
```

したがってLive取得是正をReplayへそのまま入れない。

- 既存ReplayPipelineにライブREST取得やWebSocket待機を追加しない。
- 追加するunderscore metadataはnormalizerが無視できる互換形にする。
- pre-sync diffがsnapshotより前に記録されるため、既存ReplayPipelineだけでは
  bridgeへ巻き戻して完全再構築できない。
- Phase 2-1の専用再構築器がmanifestのaccepted snapshot/bridgeを読み、
  同epochのpre-sync diffを参照してsnapshotから再適用する。
- 既存Replayのtrade/CVD等の挙動は維持する。
- `test_live_recording_replays_identically`は、新manifest/metadataと
  strict同期後の意味を明示して更新する必要がある。

### §4.7 rotation用max_bytes設定経路

#### 現状

- default:
  `depth_history_recorder.py:30`
  `_DEFAULT_MAX_BYTES = 64 * 1024 * 1024`
- constructor引数:
  41〜46行
- rotation判定:
  92〜93行
- WebApp生成:
  `webapp/main.py:129〜132`は`max_bytes`を渡さずdefault固定
- compose:
  `docker-compose.yml:29〜30`はenabled/rootのみ
- `config/config.yaml`:
  depth history/max_bytes項目なし
- programmatic path:
  `tests/acquisition/test_depth_history_recorder.py:75`の
  `DepthHistoryRecorder(..., max_bytes=200)`だけ

現時点では、通常のWebApp録画でconfig/環境変数から`max_bytes`を小さくする経路はない。
変更なしで可能なのは、コードからconstructorを直接呼ぶ場合だけである。

現行compose:

```yaml
  28:       # ADR-011 raw depth history(取得層タップ)。有効化はP1-2で判断。
  29:       - DEPTH_HISTORY_ENABLED=false
  30:       - DEPTH_HISTORY_ROOT=/app/data_05M/depth_history_raw
```

#### 是正計画

既存のenabled/rootが環境変数なので、最小変更として
`DEPTH_HISTORY_MAX_BYTES`を追加する。

- default: `67108864`
- `webapp/main.py`でstrictな正整数として1回だけparse
- invalid、0、負数は起動時に明示error
- `float()`は使用しない
- `DepthHistoryRecorder(..., max_bytes=parsed_value)`へ渡す
- `docker-compose.yml`へdefault値を明記
- 起動logへeffective max_bytesを出す

次回検証録画では小さい値を明示し、少なくとも1回
`closed_reason="rotate"`の実境界を作る。
本調査では環境変数追加も録画も行っていない。

### §4.8 変更対象ファイル

| 変更対象 | 計画内容 | 必須度 |
|---|---|---|
| `Delta_Engine_Pro4web/src/pipeline.py` | 現行supervisor即適用を廃止し、Live depth同期state machineを配線。strict bridge確認後だけsnapshot/diffを適用。初期・gap再同期を共通化 | 必須 |
| `Delta_Engine_Pro4web/src/acquisition/depth_sync.py`（新規候補） | depth buffer、epoch、attempt上限、bridge探索、pu検証、fail-closed結果を分離実装 | 推奨 |
| `Delta_Engine_Pro4web/src/acquisition/receiver.py` | 最初の有効depth受信をcoordinatorへ通知できる同期callback/tapを追加。raw record→forwardの到着順契約は維持 | 必須候補 |
| `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py` | sync metadata受け口、manifest V2、複数sync_checks、SafeRecorder/RecorderTee forwarding、rotation時状態確定 | 必須 |
| `Delta_Engine_Pro4web/webapp/main.py` | `DEPTH_HISTORY_MAX_BYTES`のstrict整数読込とrecorderへの引渡し | 必須 |
| `Delta_Engine_Pro4web/docker-compose.yml` | `DEPTH_HISTORY_MAX_BYTES` default/録画時override経路を追加 | 必須 |
| manifest/schema仕様書（Phase 2-0-dで統括指定） | V2 fields、pre-sync metadata、epoch/attempt/accepted bridgeの意味を固定 | 必須 |
| `src/orderflow/orderbook.py` | coordinator外部でstrict検証する案では基本変更不要。lenient APIを直接未検証で呼べない契約をdoc/testで固定。必要ならverified bridge専用APIを別承認 | 原則不要 |
| `src/acquisition/binance_ws.py` / `connector.py` | 最初のdepth実データをbarrierにする案では変更不要。SUBSCRIBED eventだけを使う案は不十分 | 原則不要 |

### §4.9 想定リスクと対策

| リスク | 内容 | 計画上の対策 |
|---|---|---|
| buffer memory増加 | REST遅延・失敗中にdiffが蓄積 | depthのみ、正整数上限、overflow時はattempt失敗。raw disk記録は継続 |
| 一般queue overflow | 現行`drop_oldest_log`はsync bridgeを失い得る | sync bufferは別管理。overflowしたepochをverifiedにしない |
| snapshot候補とdiffのrace | 同一loopでもtask完了順は変動 | monotonicなcapture順・epoch・attemptを付与し、main ownerで判定 |
| 重複適用 | bufferしたdiffを到着時とsync後の両方で適用する危険 | unsynced中は板へ適用せず、verified後にcoordinatorから1回だけemit |
| producer副作用順 | 遅延適用時にobserve_book_updateが重複/逆順になる危険 | bridge以後を元のdepth到着順で1回だけ通知するfixture |
| manifest rotation | sync確立前にsegmentがrotate | segment close時stateを固定し、後から上書きしない。次segmentにPASSを記録 |
| 複数resync | scalar manifestでは履歴消失 | bounded `sync_checks`配列とepochを採用 |
| candidate snapshot全量性 | rejectしたsnapshotを捨てると監査不能 | 全candidateを理由・attempt付きで記録 |
| Live表示遅延 | strict PASSまで板が表示されない | fail-closedを維持。trade/CVD等は継続 |
| Replay互換 | pre-sync行がsnapshot前にある | metadataを追加し、Phase 2-1専用reconstructorでaccepted bridgeから再構築 |
| schema互換 | manifest V1 readerが未知field/revisionを拒否 | V2明示、reader互換test、V1 fixture維持 |
| float混入 | metadata生成時の誤変換 | ID/attempt/epochはint、価格数量はstr、再帰型test |
| recorder障害 | SafeRecorderがdisableされmanifestを残せない | health/logへerrorを露出し、sync_verified扱いにしない |
| 既存未コミット変更 | `webapp/main.py`と`docker-compose.yml`は調査時点で変更済み | Phase 2-0-d着手時に既存差分を保護し、重複箇所を再監査 |

### §4.10 影響するテスト

既存testの更新・回帰対象:

- `Delta_Engine_Pro4web/tests/test_book_resync.py`
  - `test_startup_retry_until_success`（40行）
  - `test_successful_snapshot_is_recorded_for_exact_depth_replay`（67行）
  - `test_backoff_caps_at_30`（97行）
  - `test_resync_after_gap`（117行）
  - `test_no_fetch_while_healthy`（147行）
- `Delta_Engine_Pro4web/tests/test_live_pipeline.py`
  - `test_live_recording_replays_identically`（164行）
  - `test_optional_raw_observation_tap_is_isolated_from_legacy_stats`（194行）
  - `test_snapshot_reason_is_added_only_to_observation_tap`（225行）
  - observation failure隔離test（239行）
- `Delta_Engine_Pro4web/tests/acquisition/test_depth_history_recorder.py`
  - 文字列素通し、manifest、rotation、flush、SafeRecorder、RecorderTee全件
- `Delta_Engine_Pro4web/tests/acquisition/test_binance_rest.py`
  - REST変換（52行）
  - snapshot/diff順（103行）
  - 現在のlenient初期同期test（145行）
- `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`
  - fail-closed/gap/resync lifecycle（66行）
  - 調査時点の未コミット追加testも保護
- `Delta_Engine_Pro4web/tests/test_pipeline_snapshot_wiring.py`
  - Replay/Live両pipelineのsnapshot wiring
- `Delta_Engine_Pro4web/tests/test_config.py`
  - config方式を採る場合のみ
- compose/envのdeployment test

新規fixture test:

1. depthを先に受信しbuffer開始後にだけREST fetchが始まる。
2. buffer内の`U <= snapshot_u + 1 <= u` bridgeでPASSする。
3. bufferがtargetを通過してbridgeなしならsnapshotを再取得する。
4. attempt上限到達でmanifest false、明示error、板fail-closed。
5. bridge以後の`pu`不連続をverifiedにしない。
6. pre-sync diff、candidate snapshot、post-sync diffがraw到着順・全量で残る。
7. accepted bridgeをmanifestから一意に特定できる。
8. BOOK_RESYNCでも同じstrict手順を通る。
9. sync中rotationの前後manifestが正しい。
10. `DEPTH_HISTORY_MAX_BYTES`の小さい値で実fixture rotationが起きる。
11. invalid max_bytesが起動時に明示失敗する。
12. 追加metadataを含め全JSONLにfloat型が混入しない。
13. Replayはネット接続せず、既存trade/CVD経路が不変。
14. recorder/coordinator失敗がFlow Price Response等の独立経路を停止しない。

本指示書ではtest収集・実行とも行っていない。

## §5 実行した全コマンドと結果

すべて読取専用。失敗コマンドは0件。同一コマンド再試行はない。

### 1. 出力先重複確認と横断検索

```powershell
[System.IO.File]::Exists(
  '...\ArchitectureRepository\00_Master\HEATMAP\Phase_2-0-c_初期同期調査報告.md'
)
rg -n --no-heading "INITIAL_BOOK_SYNC|_capture_reason|fetch_depth_snapshot|DepthHistoryRecorder|RecorderTee|raw_recorder|@depth|depthUpdate|apply_initial_sync|resync" Delta_Engine_Pro4web/src Delta_Engine_Pro4web/tests Delta_Engine_Pro4web/config Delta_Engine_Pro4web/docker-compose.yml
```

結果: exit 0。報告書は作成前False。関連定義・test・configを特定。

### 2. pipeline supervisor・recorder配線・task起動箇所の行番号付き読取

```powershell
[System.IO.File]::ReadAllLines('Delta_Engine_Pro4web/src/pipeline.py', UTF8)
# 95〜232、1135〜1205、1455〜1525行を出力
```

結果: exit 0。`_RecorderFanout`、`_book_resync_supervisor`、
`run_async`配線、task生成順を確認。

### 3. depth apply/gap経路検索とpipeline追加範囲読取

```powershell
rg -n "process_depth|book_state\.apply|gap_detected|producer\.observe_book|classify_raw" Delta_Engine_Pro4web/src/pipeline.py
# pipeline.py 204〜250、1515〜1575、1650〜1705行を出力
```

結果: exit 0。Live main consumerのdepth適用とsupervisor終了処理を確認。

### 4. connector/receiver/subscription候補検索

```powershell
rg -n "class ExchangeConnector|def run|subscribe|class DataReceiver|recorder\.write|out_queue|norm_q" Delta_Engine_Pro4web/src/acquisition Delta_Engine_Pro4web/src/pipeline.py
```

結果: exit 0。connector、receiver、binance_wsの定義箇所を特定。

### 5. connector/receiver/binance_ws現物読取

```powershell
# connector.py 45〜180
# receiver.py 61〜111
# binance_ws.py 128〜180
[System.IO.File]::ReadAllLines(<各ファイル>, UTF8)
```

結果: exit 0。WebSocket接続、SUBSCRIBE、out_q、raw record、norm_qの順を確認。

### 6. REST snapshot fetcher読取

```powershell
[System.IO.File]::ReadAllLines(
  'Delta_Engine_Pro4web/src/acquisition/binance_rest.py', UTF8
)
# 1〜100行
```

結果: exit 0。aiohttp GET、文字列保持、timeout/error処理を確認。

### 7. REST snapshot変換関数検索・読取

```powershell
rg -n "def rest_to_depth_event|lastUpdateId|depthSnapshot" Delta_Engine_Pro4web/src/acquisition/binance_rest.py
# 130〜175行を行番号付き出力
```

結果: exit 0。関数定義124行、`u=lastUpdateId` 143行、
ローカル受信時刻metadataを確認。

### 8. DepthHistoryRecorder全文範囲読取

```powershell
[System.IO.File]::ReadAllLines(
  'Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py', UTF8
)
# 1〜210行
```

結果: exit 0。受け口、rotation、manifest、SafeRecorder、RecorderTeeを確認。

### 9. max_bytes・環境変数・生成箇所検索

```powershell
rg -n "DepthHistoryRecorder\(|depth_history|DEPTH_HISTORY|max_bytes|RAW_DEPTH_HISTORY" Delta_Engine_Pro4web --glob '!data_05M/**' --glob '!*.jsonl' --glob '!*.duckdb'
```

結果: exit 0。WebApp/composeにはenabled/rootだけで、max_bytes経路なし。

### 10. WebApp lifespan配線読取

```powershell
[System.IO.File]::ReadAllLines('Delta_Engine_Pro4web/webapp/main.py', UTF8)
# 105〜145、350〜395、545〜600行
```

結果: exit 0。Liveだけraw recorderを渡し、Replayでは渡さない構造を確認。

### 11. Replay/Live構造読取

```powershell
[System.IO.File]::ReadAllLines('Delta_Engine_Pro4web/src/pipeline.py', UTF8)
# 430〜490、625〜670、890〜995行
```

結果: exit 0。Replayはファイル順直接適用、Liveはasyncio task構造。

### 12. BoundedEventQueue検索

```powershell
rg -n "class BoundedEventQueue|async def put|drop_oldest|overflow" Delta_Engine_Pro4web/src/acquisition
```

結果: exit 0。実ファイルは`event_queue.py`。一般queueであり同期bufferではない。

### 13. event_queue.py読取

```powershell
[System.IO.File]::ReadAllLines(
  'Delta_Engine_Pro4web/src/acquisition/event_queue.py', UTF8
)
# 1〜75行
```

結果: exit 0。既定`drop_oldest_log`とoverflow counterを確認。

### 14. 関連test検索

```powershell
rg -n "^def test_|^async def test_|INITIAL_BOOK_SYNC|BOOK_RESYNC|max_bytes|write_snapshot|raw_recorder|snapshot.*diff|buffer" <関連test 7ファイル>
```

結果: exit 0。§4.10の既存testを特定。

### 15. resync supervisor test読取

```powershell
[System.IO.File]::ReadAllLines(
  'Delta_Engine_Pro4web/tests/test_book_resync.py', UTF8
)
# 1〜170行
```

結果: exit 0。起動retry、snapshot記録、gap再取得、healthy時非取得の現行期待を確認。

### 16. ADR-003/011・rotation関連文書検索

```powershell
rg -n "ADR-003|ADR-011|単一ループ|arrival|到着順|全量|max_bytes|rotation" ArchitectureRepository Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py | Select-Object -First 120
```

結果: exit 0。ADR-003、ADR-011、Phase 1設計制約と現行recorder説明を確認。

### 17. Replay/Liveのbook_state生成位置読取

```powershell
rg -n "book_state =|OrderBookStateManager\(" Delta_Engine_Pro4web/src/pipeline.py
# pipeline.py 500〜535、1230〜1265行
```

結果: exit 0。ReplayとLiveが別々のmanagerを所有する二重構造を確認。

### 18. 将来変更候補のworktree状態確認

```powershell
git status --short -- <pipeline/acquisition/webapp/compose/関連test>
```

結果: exit 0。次の2ファイルが調査開始前から変更済み。

```text
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/webapp/main.py
```

本調査では変更していない。

### 19. compose/config現物読取

```powershell
# docker-compose.yml 20〜34行
# config/config.yaml 18〜30行
[System.IO.File]::ReadAllLines(<各ファイル>, UTF8)
```

結果: exit 0。depth stream購読と、max_bytes設定不在を確認。

### 20. 報告書の必須項目・保存先・変更範囲確認

```powershell
[System.IO.File]::ReadAllText(<Phase_2-0-c report>, UTF8)
[System.IO.File]::ReadAllLines(<Phase_2-0-c report>, UTF8)
git status --short -- ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-c_初期同期調査報告.md Delta_Engine_Pro4web/src Delta_Engine_Pro4web/webapp/main.py Delta_Engine_Pro4web/docker-compose.yml Delta_Engine_Pro4web/config Delta_Engine_Pro4web/tests
```

結果: exit 0。確認時46,841 byte／1,090行、必須marker 21件中欠落0、
絶対保存先記載あり。新規物は本報告書だけ。
既存変更として`docker-compose.yml`、`webapp/main.py`、
`tests/webapp/test_book_update.py`が表示されたが、本調査では変更していない。

## §6 発見した想定外事項

1. 背景の原因候補は「REST後にstream記録開始」だったが、コードは明示的な直列ではなく
   connector/receiver/supervisorの並行raceだった。結果としてRESTが先着すれば
   同じ欠落が発生し、今回の現物はその順序だった。
2. connector taskはsupervisor taskより先に生成されるが、購読完了barrierではない。
   task生成順だけでは要件1を満たさない。
3. 一般`BoundedEventQueue`は存在するが、bridge探索・epoch・overflow fail-closedを持たず、
   初期同期bufferとして使用できない。
4. gap後の`BOOK_RESYNC` snapshot挿入経路は既に存在する。
   Phase 2-0-bで出現しなかったのは経路不在ではなく、capture中にgap resyncが起きなかったため。
5. gap再同期経路もstrict接続検証を持たず、初期同期と同じ穴がある。
6. REST snapshotの`E`は取引所snapshot時刻ではなくローカル受信時刻。
   欠落msの厳密評価ではこの値を取引所生成時刻として扱えない。
7. `max_bytes`は通常WebApp録画から設定不能。64MiB default固定で、
   次回rotation検証には環境変数/config配線の実装が必要。
8. 将来変更候補の`webapp/main.py`、`docker-compose.yml`、
   `tests/webapp/test_book_update.py`は既にユーザー変更済み。
   Phase 2-0-dでは上書きせず、差分を保護して実装する必要がある。
9. 現行Replayはraw行順に直接適用し、Liveのlenient初期同期を使わない。
   したがって同じ記録でもLive表示とReplay再構築結果が一致しない可能性がある。

## §7 停止位置

是正案の実装、設定追加、test変更、test実行、録画、ライブ接続は行っていない。
本報告をもって計画提示で停止し、Phase 2-0-dの統括承認を待つ。

## §8 報告書保存先

`C:\Users\user\Desktop\DeltaEngine05M\ArchitectureRepository\00_Master\HEATMAP\Phase_2-0-c_初期同期調査報告.md`
