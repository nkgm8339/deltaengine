# Stage2 Task2 Stage1b Health Probe Investigation Report

発行日: 2026-08-01  
対象HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
調査範囲: 読み取りのみ。ソース編集、stash、checkout、rm、clean、add、commitは未実行。

## Q1 health状態の実体

### app.state.health_report

`Delta_Engine_Pro4web/webapp/main.py:520`:

```text
520:    app.state.health_report = None
```

固定型注釈は実物にない。初期値は`None`。

`Delta_Engine_Pro4web/webapp/main.py:566-588`:

```text
566:                report = monitor.evaluate(snap)
567:                health_payload = report.to_payload()
575:                health_payload["checks"]["tape"] = {
585:                if tape_problem and health_payload["state"] == "GREEN":
586:                    health_payload["state"] = "YELLOW"
587:                app.state.health_report = health_payload
588:                await broker.send_health(snap.sample_time, health_payload)
```

実体は`HealthReport.to_payload()`が返すdict。`Delta_Engine_Pro4web/src/monitor/health.py:120-135`でpayloadのキーは`state`、`sample_time`、`checks`、`anomalies_today`と定義される。

### stateの取り得る値

`Delta_Engine_Pro4web/src/monitor/health.py:12-13` は全体状態をGREEN/YELLOW/REDの3段階と記載し、`health.py:35-39`で値を定義する。

```text
35:GREEN = "GREEN"
36:YELLOW = "YELLOW"
37:RED = "RED"
39:_LEVEL_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}
```

`Delta_Engine_Pro4web/src/monitor/health.py:351-369`では全checksの最悪levelを`HealthReport(state=worst, ...)`として返す。

### health更新loop

`Delta_Engine_Pro4web/webapp/main.py:539-567`に`async def _health_loop()`があり、`HealthMonitor.evaluate()`からpayloadを作る。`main.py:592`で`health_task`として生成され、`main.py:605-607`で`app.state.tasks`へ登録される。

### 外部公開

`Delta_Engine_Pro4web/webapp/main.py:669-671`:

```text
669:@app.get("/health")
670:async def health():
671:    return {"status": "ok"}
```

`/health`は固定`{"status":"ok"}`で、`health_report`を参照しない。

`Delta_Engine_Pro4web/webapp/main.py:674-680`:

```text
674:@app.get("/api/health")
675:async def api_health(request: Request):
677:    report = getattr(request.app.state, "health_report", None)
678:    if report is None:
679:        return JSONResponse({"state": "UNKNOWN", "checks": {}, "anomalies_today": 0})
680:    return JSONResponse(report)
```

結論: D7が反映できる既存health状態は`app.state.health_report`のdict payload。異常値は既存state値では`RED`。公開先は`/api/health`であり、`/health`は常にok固定。

## Q2 task登録と例外監視

### task登録

`Delta_Engine_Pro4web/webapp/main.py:592-607`:

```text
592:    health_task = asyncio.create_task(_health_loop()) if m.enabled else None
593:    tasks = [pipeline_task, stats_task]
594:    if market_push_task is not None:
595:        tasks.append(market_push_task)
596:    if book_projection_task is not None:
597:        tasks.append(book_projection_task)
598:    if heatmap_replay_task is not None:
599:        tasks.append(heatmap_replay_task)
600:    tasks.append(tape_task)
601:    if oi_task is not None:
602:        tasks.append(oi_task)
603:    if hfm_task is not None:
604:        tasks.append(hfm_task)
605:    if health_task is not None:
606:        tasks.append(health_task)
607:    app.state.tasks = tasks
```

shutdown側は`main.py:611-616`で全taskをcancelし、例外をsuppressしてawaitする。

### done callbackの先例

先例は存在する。`Delta_Engine_Pro4web/webapp/main.py:261-271`:

```text
261:        def report_failure(completed) -> None:
262:            if completed.cancelled():
263:                return
264:            error = completed.exception()
265:            if error is not None:
266:                logger.error(
267:                    "replay broker callback failed",
268:                    exc_info=(type(error), error, error.__traceback__),
269:                )
271:        future.add_done_callback(report_failure)
```

結論: `add_done_callback`の既存作法はある。cancelled判定、`exception()`取得、logger.errorによるtraceback記録を踏襲できる。現在のreplay task自身にはdone callback登録はない。

## Q3 D7差し込み位置

### replay task生成の現行実物

`Delta_Engine_Pro4web/webapp/main.py:397-412`:

```text
397:    tape_task = asyncio.create_task(tape_batcher.run())
398:
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
412:    )
```

### 一意なbeforeアンカー候補

callbackをtask生成直後に登録する位置は、次のafter行の直後が候補。

```python
    )

    pending_oi_samples: list[dict] = []
```

基準HEADにおける`pending_oi_samples: list[dict] = []`の一意性は`Select-String`でCOUNT=1。したがってD7は、replay task式の終了`    )`と`pending_oi_samples`の間へ、`if heatmap_replay_task is not None: heatmap_replay_task.add_done_callback(...)`を挿入するアンカーとして確定候補にできる。

## D7設計確定に必要な注意

既存health payloadはhealth loopが周期更新するため、done callbackが`app.state.health_report`へREDを設定しても、次のhealth loopで通常payloadに上書きされる可能性がある。callbackで持続的に異常を反映するには、別の`app.state`フラグをhealth loopが参照する追加変更、またはhealth payloadを直接更新して以後のloopでもREDを維持する仕様が必要である。この持続性は実物上まだ確定していない。

また、`/health`は`main.py:669-671`で固定okを返すため、D7で`/health`の結果を異常化するには追加アンカーが必要になる。既存公開先だけを使うなら`/api/health`を対象にする。

