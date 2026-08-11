# 第三コミット time_sales.js帰属確定 材料

- Version: 1.0
- 採取日: 2026-07-31
- 対象: DeltaEngine05M
- HEAD: `3be272cbce32464b45f1e952d692cc5ce61703c3`

## T1. test_absorption_realtime_display.py 全内容

```python
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.pipeline import _observe_absorption_state
from webapp.push_broker import PushBroker


ROOT = Path(__file__).parents[2]


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _result(
    classification: str = "BUY_ABSORPTION",
    *,
    strength: str = "0.82",
    price_low: str = "118245.1",
    price_high: str = "118245.1",
) -> SimpleNamespace:
    return SimpleNamespace(
        classification=classification,
        strength=Decimal(strength),
        price_low=Decimal(price_low),
        price_high=Decimal(price_high),
    )


def _websocket_collector() -> tuple[MagicMock, list[dict]]:
    websocket = MagicMock()
    sent: list[dict] = []

    async def send_text(text: str) -> None:
        sent.append(json.loads(text))

    websocket.send_text = AsyncMock(side_effect=send_text)
    return websocket, sent


def test_broker_broadcasts_active_and_clear_and_caches_latest_state() -> None:
    async def run() -> None:
        broker = PushBroker("BTCUSDT")
        first_ws, first_sent = _websocket_collector()
        await broker.register(first_ws)

        observed_at = _utc("2026-07-31T02:23:10.123000")
        await broker.on_absorption_state(
            observed_at,
            _result(),
            window_sec=10,
        )
        assert first_sent[-1]["type"] == "ABSORPTION_STATE"
        assert first_sent[-1]["payload"] == {
            "active": True,
            "classification": "BUY_ABSORPTION",
            "strength": "0.82",
            "price_low": "118245.1",
            "price_high": "118245.1",
            "observed_at": "2026-07-31T02:23:10.123000+00:00",
            "expires_at": "2026-07-31T02:23:20.123000+00:00",
            "window_sec": 10,
        }

        late_ws, late_sent = _websocket_collector()
        await broker.register(late_ws)
        assert late_sent == [first_sent[-1]]

        clear_time = _utc("2026-07-31T02:23:11")
        await broker.on_absorption_state(clear_time, None, window_sec=10)
        assert first_sent[-1]["payload"]["active"] is False
        assert first_sent[-1]["payload"]["classification"] is None
        assert first_sent[-1]["payload"]["expires_at"] is None
        assert late_sent[-1] == first_sent[-1]

        after_clear_ws, after_clear_sent = _websocket_collector()
        await broker.register(after_clear_ws)
        assert after_clear_sent == [first_sent[-1]]

    asyncio.run(run())


def test_tick_time_bridge_emits_detection_updates_and_one_clear_only() -> None:
    active = _result()

    class FakeDetector:
        def __init__(self) -> None:
            self.events_detected = 0
            self._current = None
            self._next = [
                (active, True),
                (active, True),
                (None, False),
                (None, False),
            ]

        def current(self):
            return self._current

        def observe_trade(self, _trade) -> None:
            self._current, detected = self._next.pop(0)
            if detected:
                self.events_detected += 1

    detector = FakeDetector()
    received = []
    trade = SimpleNamespace(event_time=_utc("2026-07-31T02:23:10"))

    for _ in range(4):
        _observe_absorption_state(
            detector,
            trade,
            lambda event_time, result: received.append((event_time, result)),
        )

    assert received == [
        (trade.event_time, active),
        (trade.event_time, active),
        (trade.event_time, None),
    ]


def test_webapp_wires_realtime_state_without_removing_analysis_fallback() -> None:
    main_source = (ROOT / "webapp" / "main.py").read_text(encoding="utf-8")
    html = (ROOT / "webapp" / "static" / "index.html").read_text(encoding="utf-8")

    assert "pipeline.on_absorption_state = on_absorption_state_cb" in main_source
    assert "broker.on_absorption_state(" in main_source
    assert 'case "ABSORPTION_STATE": onAbsorptionState(m,p); break;' in html
    assert "if(!ABS_REALTIME_SEEN){" in html
    assert "ABS=a.absorption||null;" in html
    assert "if(!on)resetAbsorptionRealtimeState();" in html
    assert "S.marketTime<ABS_EXPIRES_AT" in html
```

## T2. テストの依存対象

### import文・読み込み対象

```text
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:1:from __future__ import annotations
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:3:import asyncio
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:4:import json
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:5:from datetime import datetime, timezone
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:6:from decimal import Decimal
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:7:from pathlib import Path
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:8:from types import SimpleNamespace
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:9:from unittest.mock import AsyncMock, MagicMock
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:11:from src.pipeline import _observe_absorption_state
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:12:from webapp.push_broker import PushBroker
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:15:ROOT = Path(__file__).parents[2]
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:131:    main_source = (ROOT / "webapp" / "main.py").read_text(encoding="utf-8")
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py:132:    html = (ROOT / "webapp" / "static" / "index.html").read_text(encoding="utf-8")
```

読み込み対象は `Delta_Engine_Pro4web/webapp/main.py`（テスト:131）と `Delta_Engine_Pro4web/webapp/static/index.html`（テスト:132）。

### 文字列走査

```text
PATTERN=onAcceptedTrades HIT_COUNT=0
PATTERN=time_sales HIT_COUNT=0
PATTERN=ABSORPTION_STATE HIT_COUNT=2
60:        assert first_sent[-1]["type"] == "ABSORPTION_STATE"
136:    assert 'case "ABSORPTION_STATE": onAbsorptionState(m,p); break;' in html
PATTERN=onAbsorptionState HIT_COUNT=1
136:    assert 'case "ABSORPTION_STATE": onAbsorptionState(m,p); break;' in html
```

| 文字列 | 出現 | 行 |
|---|:---:|---|
| `onAcceptedTrades` | × | — |
| `time_sales` | × | — |
| `ABSORPTION_STATE` | ○ | `test_absorption_realtime_display.py:60,136` |
| `onAbsorptionState` | ○ | `test_absorption_realtime_display.py:136` |

## T3. onAcceptedTrades の消費先

全ソースgrep生出力:

```text
Delta_Engine_Pro4web/webapp/static/time_sales.js:221:      this.onAcceptedTrades = config.onAcceptedTrades || function () {};
Delta_Engine_Pro4web/webapp/static/time_sales.js:304:      if (accepted.length) { try { this.onAcceptedTrades(accepted, result); } catch (_) {} }
Delta_Engine_Pro4web/webapp/static/index.html:2431:    capacity:500,poolSize:32,rowHeight:28,onSelect:trade=>{selectTapeTrade(trade);if(window.HEATMAP_UI)window.HEATMAP_UI.focusTrade(trade);},onStreamRestart:()=>loadTimeSalesHistory(),onAcceptedTrades:onAcceptedTapeTrades,
Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:58:    assert "this.onAcceptedTrades(accepted, result)" in tape
Delta_Engine_Pro4web/tests/webapp/test_dom_trade_pulse_ui.py:47:    assert "onAcceptedTrades:onAcceptedTapeTrades" in html
```

config受渡し箇所:

```text
Delta_Engine_Pro4web/webapp/static/index.html:2431:    capacity:500,poolSize:32,rowHeight:28,onSelect:trade=>{selectTapeTrade(trade);if(window.HEATMAP_UI)window.HEATMAP_UI.focusTrade(trade);},onStreamRestart:()=>loadTimeSalesHistory(),onAcceptedTrades:onAcceptedTapeTrades,
```

渡される関数の定義・本体:

```text
Delta_Engine_Pro4web/webapp/static/index.html:1095:function onAcceptedTapeTrades(trades,result){
Delta_Engine_Pro4web/webapp/static/index.html:1096:  const streamId=TAPE_UI&&TAPE_UI.store?TAPE_UI.store.streamId:null;
Delta_Engine_Pro4web/webapp/static/index.html:1097:  if(FP.chart&&result&&result.restart)FP.chart.clearDomTradePulses("TAPE_STREAM_RESTART");
Delta_Engine_Pro4web/webapp/static/index.html:1098:  if(DOM_TRADE_PULSE_ENABLED&&FP.chart){
Delta_Engine_Pro4web/webapp/static/index.html:1099:    try{
Delta_Engine_Pro4web/webapp/static/index.html:1100:      FP.chart.ingestDomTradePulses(trades,{
Delta_Engine_Pro4web/webapp/static/index.html:1101:        symbol:trades&&trades[0]&&trades[0].symbol||S.symbol,
Delta_Engine_Pro4web/webapp/static/index.html:1102:        streamId,
Delta_Engine_Pro4web/webapp/static/index.html:1103:      });
Delta_Engine_Pro4web/webapp/static/index.html:1104:    }catch(_){/* DOM pulse is optional presentation; Tape acceptance remains authoritative. */}
Delta_Engine_Pro4web/webapp/static/index.html:1105:  }
```

## T4. pipeline `on_accepted_trade` 呼出実体

### 作業ツリーgrep

```text
Delta_Engine_Pro4web/src/pipeline.py:424:        self.on_accepted_trade: Optional[Callable] = None
Delta_Engine_Pro4web/src/pipeline.py:595:            if self.on_accepted_trade is not None:
Delta_Engine_Pro4web/src/pipeline.py:597:                    self.on_accepted_trade(normalized)
Delta_Engine_Pro4web/src/pipeline.py:999:        on_accepted_trade: Optional[Callable] = None,
Delta_Engine_Pro4web/src/pipeline.py:1080:        self.on_accepted_trade = on_accepted_trade
Delta_Engine_Pro4web/src/pipeline.py:1582:            if self.on_accepted_trade is not None:
Delta_Engine_Pro4web/src/pipeline.py:1584:                    self.on_accepted_trade(normalized)
```

作業ツリーの発火行は `Delta_Engine_Pro4web/src/pipeline.py:597,1584`。

### HEAD grep

```text
HEAD:Delta_Engine_Pro4web/src/pipeline.py:424:        self.on_accepted_trade: Optional[Callable] = None
HEAD:Delta_Engine_Pro4web/src/pipeline.py:594:            if self.on_accepted_trade is not None:
HEAD:Delta_Engine_Pro4web/src/pipeline.py:596:                    self.on_accepted_trade(normalized)
HEAD:Delta_Engine_Pro4web/src/pipeline.py:977:        on_accepted_trade: Optional[Callable] = None,
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1057:        self.on_accepted_trade = on_accepted_trade
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1558:            if self.on_accepted_trade is not None:
HEAD:Delta_Engine_Pro4web/src/pipeline.py:1560:                    self.on_accepted_trade(normalized)
```

HEADの発火行は `HEAD:Delta_Engine_Pro4web/src/pipeline.py:596,1560`。

## 末尾git生出力

### `git rev-parse HEAD`

```text
3be272cbce32464b45f1e952d692cc5ce61703c3
```

### `git status --porcelain`

```text
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md
 M ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H0_CHECKPOINT_20260729.md
 M ArchitectureRepository/00_Master/PROJECT_MEMORY.md
 M ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md
 M Delta_Engine_Pro4web/docker-compose.yml
 M Delta_Engine_Pro4web/src/pipeline.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
 M Delta_Engine_Pro4web/webapp/static/time_sales.js
?? ArchitectureRepository/00_Master/ABSORPTION_REALTIME_DISPLAY_FIX_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/AI\343\202\263\343\203\241\343\203\263\343\203\210/"
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task1_Go_Task2.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task2_Go_Task3.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_Go_Task4.md
?? ArchitectureRepository/00_Master/HEATMAP/Approval_P22_Task3_PreReport_Reply_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task1_ReSubmit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task2_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task3_Submit_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Instruction_P22_Task4_Fix_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit1_HeatmapCore_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_BookIdentity_Completion_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_Preflight_PushBroker_Diff_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit2_Stopped_FloatScan_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Commit3_Preflight_Pipeline_TimeSales_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage1_Investigation_Report_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Preflight_Repository_Hygiene_Materials_20260731.md
?? ArchitectureRepository/00_Master/HEATMAP/Roadmap_Heatmap_Render_to_Dynamic_v1.md
?? ArchitectureRepository/00_Master/HEATMAP/p21_evidence/
?? ArchitectureRepository/00_Master/HEATMAP/tools_p22/
?? ArchitectureRepository/00_Master/HEATMAP/worktree_backup_pre_p21_20260730.patch
?? ArchitectureRepository/00_Master/HEATMAP/worktree_status_pre_p21_20260730.txt
?? ArchitectureRepository/00_Master/HEATMAP_Instruction_v1.5.md
?? ArchitectureRepository/00_Master/HOOK_STAGE2C4_CHECKPOINT_20260731.md
?? "ArchitectureRepository/00_Master/Heatmap_Handover_20260730 (1).md"
?? ArchitectureRepository/00_Master/Heatmap_Handover_20260730.md
?? ArchitectureRepository/00_Master/INSTR_Commit1_HeatmapCore_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_Preflight_PushBroker_v1.0.md
?? "ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0 (1).md"
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit2_PushBroker_BookIdentity_v1.1.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_AbsorptionTest_Wiring_v1.0.md
?? ArchitectureRepository/00_Master/INSTR_Commit3_Preflight_Pipeline_TimeSales_v1.0.md
?? ArchitectureRepository/00_Master/Instruction_Phase2-2_Renderer_v1.md
?? ArchitectureRepository/00_Master/SCHEDULED_TASK_RESUME_FIX_CHECKPOINT_20260731.md
?? ArchitectureRepository/00_Master/VWAP_CHART_RELATED_MODULE_INVENTORY_20260729.md
?? ArchitectureRepository/00_Master/VWAP_INVESTIGATION_20260729/
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/DeltaEngine_\347\265\214\347\267\257\345\240\261\345\221\212_\347\254\2541\346\234\237-\347\254\2544\346\234\237_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_LEGACY_STRATEGY_INVENTORY_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_AND_STRATEGY_CONTENT_GUIDE_20260727.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_CONTAINER_RESTART_20260730.md"
?? "ArchitectureRepository/00_Master/\343\203\210\343\203\252\343\202\254\343\203\274\344\275\234\346\210\220\346\214\207\347\244\272\346\233\270\347\276\244/HOOK_STAGE2C1_GATE_DATA_20260729.md"
?? "ArchitectureRepository/00_Master/\345\256\237\351\201\213\347\224\250/"
?? "ArchitectureRepository/00_Master/\346\214\207\347\244\272\346\233\270_STAGE2C2_Hook\350\274\203\346\255\243_\345\210\206\345\270\203\351\233\206\350\250\210_v1.md"
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
?? pytest-vwap-ui-elevated/
?? vwap-audit.duckdb
?? vwap_first100.jsonl
?? vwap_restore_ws_capture.jsonl
?? vwap_ws_capture.jsonl
```

### `git diff --cached --name-only`

```text
```
