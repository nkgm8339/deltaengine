from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.execution.flow_hfm_executor import (
    FlowExecutionController,
    FlowTransitionDetector,
    JsonlAuditLog,
    Mt5MarketOrderGateway,
)
from tools.run_flow_hfm_autotrader import build_parser


class MemoryAudit:
    def __init__(self) -> None:
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    def inspect(self):
        return {"stage": "MT5_INSPECT", "status": "READY"}

    def execute(self, side, *, mode, context):
        self.calls.append((side, mode, dict(context)))
        return {
            "stage": "MT5_ORDER_SEND" if mode == "live" else "MT5_ORDER_CHECK",
            "status": "FILLED" if mode == "live" else "CHECK_OK",
            "side": side,
            "order_ticket": 123 if mode == "live" else None,
            "deal_ticket": 456 if mode == "live" else None,
            "fill_price": "64000.0" if mode == "live" else None,
        }


def envelope(state: str, *, window_sec: int = 30, time: str = "2026-07-25T15:00:00+00:00"):
    return {
        "type": "FLOW_RESPONSE",
        "time": time,
        "symbol": "BTCUSDT",
        "payload": {
            "windows": [
                {
                    "window_sec": window_sec,
                    "state": state,
                    "last_price": "64000.0",
                    "pressure_side": "BUY",
                }
            ]
        },
    }


def test_transition_detector_maps_the_four_entry_states():
    cases = [
        ("BUY_EFFECTIVE", "BUY"),
        ("SELL_EFFECTIVE", "SELL"),
        ("BUY_TRAPPED", "SELL"),
        ("SELL_TRAPPED", "BUY"),
    ]
    for state, side in cases:
        detector = FlowTransitionDetector(30)
        assert detector.observe("UNCLEAR").kind == "BASELINE"
        transition = detector.observe(state)
        assert transition.kind == "ENTRY"
        assert transition.side == side


def test_startup_state_is_baseline_and_same_state_does_not_duplicate():
    gateway = FakeGateway()
    audit = MemoryAudit()
    controller = FlowExecutionController(
        window_sec=30,
        mode="check",
        gateway=gateway,
        audit=audit,
    )

    baseline = controller.handle_envelope(envelope("BUY_TRAPPED"))
    unchanged = controller.handle_envelope(envelope("BUY_TRAPPED", time="2026-07-25T15:00:01+00:00"))

    assert [r["stage"] for r in baseline] == ["FLOW_BASELINE"]
    assert unchanged == []
    assert gateway.calls == []


def test_transition_creates_one_intent_and_one_order_result():
    gateway = FakeGateway()
    audit = MemoryAudit()
    controller = FlowExecutionController(
        window_sec=30,
        mode="check",
        gateway=gateway,
        audit=audit,
    )
    controller.handle_envelope(envelope("UNCLEAR"))

    records = controller.handle_envelope(
        envelope("SELL_TRAPPED", time="2026-07-25T15:00:01+00:00")
    )

    assert [r["stage"] for r in records] == [
        "FLOW_TRANSITION",
        "ORDER_INTENT",
        "MT5_ORDER_CHECK",
    ]
    assert gateway.calls[0][0:2] == ("BUY", "check")
    assert records[-1]["status"] == "CHECK_OK"
    assert records[-1]["order_ticket"] is None


def test_flow_only_controller_rejects_live_mode():
    with pytest.raises(ValueError, match="Flow-only LIVE execution is prohibited"):
        FlowExecutionController(
            window_sec=30,
            mode="live",
            gateway=FakeGateway(),
            audit=MemoryAudit(),
        )


def test_flow_only_cli_rejects_live_mode():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--mode", "live"])


def test_a_later_different_state_can_create_a_new_entry():
    gateway = FakeGateway()
    controller = FlowExecutionController(
        window_sec=30,
        mode="check",
        gateway=gateway,
        audit=MemoryAudit(),
    )
    controller.handle_envelope(envelope("UNCLEAR"))
    controller.handle_envelope(envelope("BUY_EFFECTIVE", time="2026-07-25T15:00:01+00:00"))
    controller.handle_envelope(envelope("BUY_EFFECTIVE", time="2026-07-25T15:00:02+00:00"))
    controller.handle_envelope(envelope("BUY_TRAPPED", time="2026-07-25T15:00:03+00:00"))

    assert [(call[0], call[1]) for call in gateway.calls] == [
        ("BUY", "check"),
        ("SELL", "check"),
    ]


def test_other_window_is_ignored():
    gateway = FakeGateway()
    controller = FlowExecutionController(
        window_sec=30,
        mode="observe",
        gateway=gateway,
        audit=MemoryAudit(),
    )
    assert controller.handle_envelope(envelope("BUY_EFFECTIVE", window_sec=60)) == []
    assert controller.snapshot()["latest_flow"] is None


def test_jsonl_audit_is_immediately_readable(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    audit = JsonlAuditLog(path)
    audit.append({"stage": "ORDER_INTENT", "value": "日本語"})
    assert path.read_text(encoding="utf-8").strip() == (
        '{"stage":"ORDER_INTENT","value":"日本語"}'
    )


@dataclass
class Info:
    visible: bool = True
    volume_min: float = 0.01
    volume_max: float = 50.0
    volume_step: float = 0.01
    filling_mode: int = 1
    trade_allowed: bool = True
    tradeapi_disabled: bool = False
    trade_expert: bool = True


@dataclass
class Tick:
    bid: float = 63990.0
    ask: float = 64010.0


@dataclass
class Result:
    retcode: int
    comment: str = "Done"
    order: int = 0
    deal: int = 0
    price: float = 0.0


class FakeMt5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self, *, check_retcode=0, send_retcode=10009):
        self.check_retcode = check_retcode
        self.send_retcode = send_retcode
        self.sent = []

    def initialize(self, **_kwargs):
        return True

    def last_error(self):
        return (1, "Success")

    def terminal_info(self):
        return Info()

    def account_info(self):
        return Info()

    def symbol_info(self, _symbol):
        return Info()

    def symbol_info_tick(self, _symbol):
        return Tick()

    def symbol_select(self, _symbol, _visible):
        return True

    def positions_get(self, **_kwargs):
        return ()

    def orders_get(self, **_kwargs):
        return ()

    def order_check(self, _request):
        return Result(self.check_retcode)

    def order_send(self, request):
        self.sent.append(request)
        return Result(self.send_retcode, order=123, deal=456, price=request["price"])


def test_gateway_check_mode_never_sends_order():
    mt5 = FakeMt5()
    gateway = Mt5MarketOrderGateway(
        terminal_path="terminal64.exe",
        symbol="#BTCUSDr",
        mt5_module=mt5,
    )
    result = gateway.execute("BUY", mode="check", context={"window_sec": 30})
    assert result["status"] == "CHECK_OK"
    assert mt5.sent == []


def test_gateway_live_returns_ticket_and_fill():
    mt5 = FakeMt5()
    gateway = Mt5MarketOrderGateway(
        terminal_path="terminal64.exe",
        symbol="#BTCUSDr",
        mt5_module=mt5,
    )
    result = gateway.execute("SELL", mode="live", context={"window_sec": 30})
    assert result["status"] == "FILLED"
    assert result["order_ticket"] == 123
    assert result["deal_ticket"] == 456
    assert result["fill_price"] == "63990.0"
