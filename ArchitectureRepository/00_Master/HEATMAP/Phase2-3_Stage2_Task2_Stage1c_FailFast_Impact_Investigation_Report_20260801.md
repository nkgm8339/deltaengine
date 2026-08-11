# Stage2 Task2 Stage1c FailFast Impact Investigation Report

実施日: 2026-08-01  
基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
調査範囲: 読み取りのみ。v3.2 working tree、stash、`C:\tmp\task2_predrop_untracked_20260801`は変更していない。

## Q1 既存fail 3件の実体

### 1. `test_replay_does_not_start_live_oi_poller`

`Delta_Engine_Pro4web/tests/webapp/test_api.py:305-324`:

```text
305:def test_replay_does_not_start_live_oi_poller():
306:    mock_pipeline = _make_mock_pipeline()
307:    mock_pipeline.run = MagicMock(return_value=None)
308:    mock_config = _make_mock_config()
309:    mock_config.replay.enabled = True
310:    mock_config.replay.data_path = "recording.jsonl"
311:    oi_poller = AsyncMock()
313:    with patch("webapp.main.load_config", return_value=mock_config), \
315:         patch("webapp.main.ReplayPipeline") as MockPipeline, \
316:         patch("webapp.main.oi_polling_loop", new=oi_poller):
319:        with TestClient(app) as client:
320:            response = client.get("/api/history/open-interest")
322:    assert response.status_code == 200
323:    assert response.json() == {"samples": []}
324:    oi_poller.assert_not_called()
```

`_make_mock_config()`の初期値は`test_api.py:12-50`で`cfg.replay.enabled = False`、このテストだけ`test_api.py:309`でTrueに変更する。`HEATMAP_REPLAY_ENABLED`を設定する実物はこのテストにない。検証対象はreplay時のOI APIとOI poller非起動で、Heatmap replayをassertしていない。Heatmapとは別系統。

### 2. `test_replay_does_not_start_live_book_projection`

`Delta_Engine_Pro4web/tests/webapp/test_api.py:327-347`:

```text
327:def test_replay_does_not_start_live_book_projection():
328:    mock_pipeline = _make_mock_pipeline()
329:    mock_pipeline.run = MagicMock(return_value=None)
330:    mock_config = _make_mock_config()
331:    mock_config.replay.enabled = True
332:    mock_config.replay.data_path = "recording.jsonl"
333:    book_run = AsyncMock()
335:    with patch("webapp.main.load_config", return_value=mock_config), \
337:         patch("webapp.main.ReplayPipeline") as MockPipeline, \
338:         patch("webapp.main.LatestBookProjectionPump.run", new=book_run), \
339:         patch("webapp.main.oi_polling_loop", new=AsyncMock()):
342:        with TestClient(app) as client:
343:            response = client.get("/api/stats")
345:    assert response.status_code == 200
346:    assert response.json()["book_projection_state"] == "DISABLED_REPLAY"
347:    book_run.assert_not_awaited()
```

`HEATMAP_REPLAY_ENABLED`設定は実物にない。assertは既存live book projection pumpがreplayモードで起動しないこととstatsの`DISABLED_REPLAY`であり、recording-driven heatmap replay taskやCanvasを検証していない。Heatmap replayとは別系統の既存book projection回帰テスト。

### 3. `test_replay_worker_callbacks_reach_websocket_with_market_time`

`Delta_Engine_Pro4web/tests/webapp/test_api.py:465-529` の実物では、`config.replay.enabled=True`（`test_api.py:472-475`）、`ReplayPipeline`をpatch（`test_api.py:503-506`）、WebSocketへ接続（`test_api.py:509-511`）し、replay workerからTrade/Candleを送る（`test_api.py:478-499`）。assertは`TAPE_UPDATE`と`CANDLE`の時刻・sequence・trade内容（`test_api.py:522-529`）である。BOOK_UPDATE、`HEATMAP_UI`、Canvas、`HEATMAP_REPLAY_ENABLED`の実物はない。結論: **Heatmapとは無関係**で、market/tape/candle replayのWebSocket回帰テスト。

## Q2 起動fixture共有範囲

3件とも`from webapp.main import app`後に`with TestClient(app) as client:`を通り、FastAPI lifespanを起動する（`test_api.py:318-320`, `341-343`, `508-510`）。`main.py:120-146`のlifespanがconfigを読み、v3.2のfail-fastは`main.py:142-146`でこのfixtureの起動時に通過する。

`test_api.py`内の`TestClient(`出現数は16件。従って同じアプリlifespan fixtureの影響範囲は3件だけではない。代表例は`test_api.py:86-88`（`/health`）、`105-107`（`/api/stats`）、`128-130`（`/api/config`）、`416-418`（`/api/health`）で、これらは通常`_make_mock_config()`の`replay.enabled=False`を使う。replay=Trueに変更する上記3件が、v3.2 fail-fastの新規fail対象である。

## Q3 UI gateとconfig.replayの連携

### gateは静的

`Delta_Engine_Pro4web/webapp/static/index.html:968-969`:

```text
968:// GO-H3 presentation gate. Keep false until GO-H6 operational activation.
969:const ORDER_BOOK_HEATMAP_ENABLED = true;
```

gateは静的JavaScript定数。`main.py:661-669`のルートは`FileResponse(str(_STATIC_DIR / "index.html"))`で静的ファイルを返すだけで、config値をテンプレート注入しない。

### HELLO/WebSocketにもreplay状態はない

`main.py:677-680`のHELLO payloadはversion、time、symbol等を送り、`config.replay.enabled`を含めない。index側のHELLO処理は`index.html:1043-1045`でversionとsymbolを扱うだけ。`config.replay`をgateへ渡す実物経路はない。

### gate抑制フック

gate=false時の既存抑制は`index.html:2375-2379`の`if(!ORDER_BOOK_HEATMAP_ENABLED)`で、heatmapButton、canvas、controls等をhiddenにしてreturnする静的分岐。BOOK_UPDATE受信は`index.html:1066`の`onBookUpdate(p)`、Canvasへの投入は`index.html:1085-1088`の`HEATMAP_UI.ingestBook`である。

アプリreplay時だけこのgateを動的に抑制するための既存サーバ→フロント受け渡し、config注入、HELLO flagは実物にない。結論: **実物にない（既存の動的抑制フックなし）**。案Aを採る場合、main.pyのHELLO payload等とindex.htmlの初期化経路を追加変更する必要があり、v3.2の5ファイル・既存D1-D7アンカーだけでは表現できない。

## Stage1c結論

1. failした3件はHeatmap replayではなく、既存のOI/book projection/tape/candle replay回帰テスト。
2. 3件とも同じTestClient/lifespanを通過し、v3.2のfail-fastを踏む。
3. live通常（`config.replay.enabled=false`）は既存live pumpが供給するが、アプリreplay時にgateだけ抑制する既存フックは存在しない。
4. 「replay時だけgate抑制」を採るには、config.replayのフロント伝達とindex側動的gateを追加設計する必要がある。これは実装前に新しいアンカー・対象範囲の承認が必要。

