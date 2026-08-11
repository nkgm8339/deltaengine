# Stage2 Task2 Stage1 Investigation Report

発行日: 2026-08-01  
基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
参照指示書: `ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Implementation_v1.0.md`  
参照指示書SHA-256: `27A1E161BEADAA3ED3DEC233844D093A62FE2AA831D08757A0BBBC7611F7D`

本調査では編集、stash、checkout、rm、clean、add、commitを実行していない。

## Q1 env変数名

### v1.0 D2の実物

`ArchitectureRepository/00_Master/INSTR_Stage2_Task2_Implementation_v1.0.md:76-88` のD2は次の実物を指定している。

```text
    heatmap_replay_enabled = os.getenv("HEATMAP_REPLAY_ENABLED", "false").lower() == "true"
    heatmap_replay_dir = Path(os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw")) / f"symbol={config.market.symbol}"
    heatmap_replay_interval_ms = int(os.getenv("HEATMAP_REPLAY_INTERVAL_MS", "100"))
    heatmap_replay_sample_interval_ms = int(os.getenv("HEATMAP_REPLAY_SAMPLE_INTERVAL_MS", "1000"))
```

### 現行working treeの読取

`Delta_Engine_Pro4web/webapp/main.py:138-141`:

```text
138:    heatmap_replay_enabled = os.getenv("HEATMAP_REPLAY_ENABLED", "false").lower() == "true"
139:    heatmap_replay_dir = Path(os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw")) / f"symbol={config.market.symbol}"
140:    heatmap_replay_interval_ms = int(os.getenv("HEATMAP_REPLAY_INTERVAL_MS", "100"))
141:    heatmap_replay_sample_interval_ms = int(os.getenv("HEATMAP_REPLAY_SAMPLE_INTERVAL_MS", "1000"))
```

`Delta_Engine_Pro4web/webapp/main.py:131` には既存のrecording writer用の同名root読取もある。

```text
131:                os.getenv("DEPTH_HISTORY_ROOT", "data_05M/depth_history_raw"),
```

`HEATMAP_REPLAY_DIR` は現行main.pyの検索結果に存在しない。結論: replay rootのenv名は `DEPTH_HISTORY_ROOT`、既定値は `data_05M/depth_history_raw/symbol=<config.market.symbol>`。replay enableの既定値はfalse。interval既定値は100ms、sample interval既定値は1000ms。

## Q2 供給者ゼロ経路

### 現行main.pyの分岐

`Delta_Engine_Pro4web/webapp/main.py:376-391`:

```text
376:    if config.replay.enabled:
377:        market_push_task = None
378:        book_projection_task = None
379:        loop = asyncio.get_event_loop()
382:        pipeline_task = asyncio.ensure_future(
383:            loop.run_in_executor(None, pipeline.run, config.replay.data_path)
384:        )
385:    else:
386:        market_push_task = asyncio.create_task(market_push_pump.run())
387:        book_projection_task = (
388:            None
389:            if heatmap_replay_enabled
390:            else asyncio.create_task(book_projection_pump.run())
391:        )
```

`Delta_Engine_Pro4web/webapp/main.py:399-411`:

```text
399:    heatmap_replay_task = (
400:        asyncio.create_task(
401:            heatmap_replay_loop(
402:                broker.on_book_update,
403:                recording_dir=heatmap_replay_dir,
404:                interval_ms=heatmap_replay_interval_ms,
405:                sample_interval_ms=heatmap_replay_sample_interval_ms,
406:                depth_levels=config.webapp.live_dom_depth_levels,
407:                symbol=config.market.symbol,
408:            )
409:        )
410:        if heatmap_replay_enabled
411:        else None
```

### 実物根拠による全モード表

| アプリモード | `HEATMAP_REPLAY_ENABLED=false` | `HEATMAP_REPLAY_ENABLED=true` |
|---|---|---|
| live (`config.replay.enabled=false`) | live pump。`main.py:386-391`でbook projection taskを生成し、`main.py:410-411`でreplay taskはNone。 | replay task。`main.py:387-390`でlive taskはNone、`main.py:399-410`でreplay taskを生成。 |
| replay (`config.replay.enabled=true`) | なし。`main.py:376-384`でbook projection taskはNone、`main.py:410-411`でreplay taskもNone。 | replay task。`main.py:376-384`でlive taskはNone、`main.py:399-410`でreplay taskを生成。 |

結論: 供給者ゼロ経路は **yes**。`config.replay.enabled=true` かつ `HEATMAP_REPLAY_ENABLED=false` のセルで発生する。D3のlive分岐だけを排他化しても、このreplay分岐のゼロ状態は解消しない。

## Q3 UI guard testの第5対象

`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:9-14`:

```text
9:def test_heatmap_is_fail_closed_until_operational_activation():
10:    source = INDEX.read_text(encoding="utf-8")
11:    assert "const ORDER_BOOK_HEATMAP_ENABLED = false;" in source
12:    assert "if(!ORDER_BOOK_HEATMAP_ENABLED)" in source
13:    assert "heatmapButton.hidden=true" in source
14:    assert "window.HEATMAP_UI=api" in source
```

gateをfalseからtrueにすると、`test_orderbook_heatmap_ui.py:11` がfailする。結論: **yes**、第5対象として当該UIテストの期待値更新が必要。テスト名も現状の「fail closed」意味とgate trueの運用状態が一致しないため、更新時に確認が必要。

## Q4 空recording判定の実装可能位置

### 現行frame source

`Delta_Engine_Pro4web/webapp/heatmap_frame_source.py:43-66`:

```text
43:def iter_book_projections(
44:    recording_dir: Path,
45:    *,
46:    interval_ms: int,
47:    depth_levels: int = 50,
48:    symbol: str = "BTCUSDT",
49:) -> Iterator[BookProjection]:
52:    if not recording_dir.is_dir():
53:        raise FileNotFoundError(recording_dir)
55:    reader = DepthHistoryReader(recording_dir)
56:    reconstructor = DepthReconstructor(symbol=symbol, max_attempts=1)
57:    for event_time_ms, snapshot in reconstructor.sample_states(
58:        reader.iter_records(), interval_ms=interval_ms
59:    ):
60:        adapter = SnapshotBookStateAdapter(snapshot)
62:        yield build_book_projection(
```

root不存在は `iter_book_projections` の呼出し開始時に `FileNotFoundError` となる。空ディレクトリや、サンプルを生成できないrecordingについては、現行frame sourceに事前件数判定はない。

### reader/reconstructorの実物

`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:48-59`:

```text
48:class DepthHistoryReader:
51:    def __init__(self, directory: Path) -> None:
55:    def segments(self) -> list[SegmentInfo]:
58:        if not self.directory.exists():
59:            raise FileNotFoundError(self.directory)
```

`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:97-113` の `iter_records(self) -> Iterator[dict]` は、`segments()`が返す検証済みsegmentのJSON object recordsをyieldする。

`Delta_Engine_Pro4web/src/heatmap/reconstruct.py:208-225`:

```text
208:    def sample_states(
209:        self,
210:        records: Iterable[dict],
211:        *,
212:        interval_ms: int,
213:    ) -> Iterator[tuple[int, OrderBookSnapshot]]:
214:        """Yield synchronized state copies at a fixed event-time interval."""
220:        for event in self.run(records):
221:            if event.kind in {"GAP_DETECTED", "SYNC_FAILED"}:
224:            if event.kind != "DIFF_APPLIED":
```

サンプル件数の実物候補は二つある。

1. `DepthHistoryReader.segments()`の戻り値 `list[SegmentInfo]` の件数。manifestの`record_count`は`reconstruct.py:117-120`で取得され、実ファイルの行数と`reconstruct.py:128-143`で照合される。ただしsegment件数やraw record件数は、同期済み`sample_states`が1件yieldされることを保証しない。
2. `DepthReconstructor.sample_states()`の戻り値iteratorから得られる`tuple[int, OrderBookSnapshot]`の件数。これはframe sourceが実際にprojection化するサンプルの定義に最も直接的に対応するが、iteratorを消費して確認する位置と再生時の二重走査を決める必要がある。

現段階の事実: root存在確認は`iter_book_projections`冒頭で可能。サンプル1件の候補は`sample_states`のyieldである。起動時raiseをmain.pyへ差し込む具体的アンカーは、replay task生成の`main.py:399-411`周辺が候補だが、空判定の二重走査や新規helperの要否は未確定であり、設計承認前に実装しない。

### recording実体

読み取り結果、`Delta_Engine_Pro4web/data_05M/depth_history_raw/symbol=BTCUSDT/` は実在し、`.jsonl` と対応`.manifest.json`が存在する。`.jsonl.part`も存在するため、未完segmentをサンプル判定に含めない必要がある。`data_05M/depth_history_raw`（リポジトリ直下）は存在せず、実体は`Delta_Engine_Pro4web/data_05M/...`配下にある。

## Q5 D1-D6実物と一意性

参照指示書のアンカーは以下。

- D1: `INSTR...:65-74` import追加。before `from webapp.hfm_quote_tailer import hfm_quote_tail_loop` / after replay import追加。
- D2: `INSTR...:76-88` env解決。`DEPTH_HISTORY_ROOT`、enabled、interval、sample interval。
- D3: `INSTR...:90-104` live分岐でbook pump排他。
- D4: `INSTR...:106-129` tape task直後のreplay task生成。
- D5: `INSTR...:131-145` tasks登録。
- D6: `INSTR...:147-157` `ORDER_BOOK_HEATMAP_ENABLED` false→true。

基準HEADに対するアンカー一意性の読み取り結果:

```text
HEAD main.py:55  from webapp.hfm_quote_tailer import hfm_quote_tail_loop  COUNT=1
HEAD main.py:137 broker = _build_broker(config, persistent_writer)  COUNT=1
HEAD main.py:381 market_push_task = asyncio.create_task(market_push_pump.run())  COUNT=1
HEAD main.py:388 tape_task = asyncio.create_task(tape_batcher.run())  COUNT=1
HEAD main.py:572 if book_projection_task is not None:  COUNT=1
HEAD index.html:969 const ORDER_BOOK_HEATMAP_ENABLED = false;  COUNT=1
```

結論: D1-D6のbeforeアンカーは基準HEADで一意。ただしQ2のreplay-mode供給者ゼロと、Q4の空recording起動時判定はD1-D6だけでは未解決。

## §2 現在の作業ツリー

読み取りコマンド出力:

```text
git rev-parse HEAD
2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4

git status --porcelain -- Delta_Engine_Pro4web/
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py

git diff --name-only -- Delta_Engine_Pro4web/
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/static/index.html

git diff --cached --name-only
(空)
```

Task 2のdirtyは4パス相当（tracked変更2、untracked新規2）。ただし指定範囲全体のstatusには`phase0c_storage_sizing_20260728/`も表示されるため、status全体を「4パスのみ」と解釈してはいけない。新規2ファイルのstatus記号は`??`で、untrackedである。書き込み操作は未実行。

## Stage 1の事実結論

1. env名は`DEPTH_HISTORY_ROOT`で確定。`HEATMAP_REPLAY_DIR`は実物にない。
2. 供給者ゼロ経路は実在する（アプリreplay × flag false）。
3. gate true化により既存UI guard testはfailするため第5対象が必要。
4. 空recordingのroot判定は既存frame sourceにあるが、同期済みsample 1件の起動時判定は未実装。`sample_states`のyieldを基準候補として追加設計が必要。
5. D1-D6 beforeアンカーは基準HEADで一意だが、Q2/Q4を解決する追加アンカーの要否は統括承認前に確定しない。

