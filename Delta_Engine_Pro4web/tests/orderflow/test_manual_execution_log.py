from datetime import datetime, timedelta, timezone

import pytest

from src.orderflow.manual_execution_log import ManualExecutionRecord, ManualExecutionStatus

UTC = timezone.utc


def executed():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    return ManualExecutionRecord(
        record_id="m-1", episode_id="e-1", symbol="#BTCUSDr", window_sec=300,
        checkpoint_time=start, checkpoint_stage="SUSTAINED_CONFLICT", pressure_side="BUY",
        signal_displayed_time=start + timedelta(seconds=1),
        decision_time=start + timedelta(seconds=3), order_time=start + timedelta(seconds=4),
        fill_time=start + timedelta(seconds=5), status=ManualExecutionStatus.EXECUTED,
        entry_side="LONG", entry_price=100.5, entry_bid=100.0, entry_ask=100.4,
        exit_time=start + timedelta(minutes=5), exit_price=105.0,
    )


def test_executed_record_preserves_delay_and_bid_ask():
    record = executed()
    assert record.execution_delay_ms == 4_000
    row = record.to_row()
    assert row["status"] == "EXECUTED"
    assert row["entry_ask"] == 100.4
    assert row["execution_delay_ms"] == 4_000


def test_skipped_record_requires_reason_but_no_fill():
    start = datetime(2026, 7, 25, tzinfo=UTC)
    record = ManualExecutionRecord(
        record_id="m-2", episode_id="e-2", symbol="#BTCUSDr", window_sec=600,
        checkpoint_time=start, checkpoint_stage="NON_RESPONSE", pressure_side="SELL",
        signal_displayed_time=start, decision_time=start + timedelta(seconds=2),
        order_time=None, fill_time=None, status=ManualExecutionStatus.SKIPPED,
        entry_side=None, entry_price=None, entry_bid=100.0, entry_ask=120.0,
        exit_time=None, exit_price=None, skip_reason="SPREAD_TOO_WIDE",
    )
    assert record.execution_delay_ms is None
    assert record.to_row()["skip_reason"] == "SPREAD_TOO_WIDE"


def test_invalid_order_is_rejected():
    record = executed()
    with pytest.raises(ValueError, match="chronological"):
        ManualExecutionRecord(
            **{**record.__dict__, "order_time": record.signal_displayed_time - timedelta(seconds=1)}
        )
    with pytest.raises(ValueError, match="skip_reason"):
        ManualExecutionRecord(
            **{**record.__dict__, "status": ManualExecutionStatus.SKIPPED, "entry_side": None,
               "entry_price": None, "fill_time": None, "exit_time": None, "exit_price": None,
               "skip_reason": None}
        )
