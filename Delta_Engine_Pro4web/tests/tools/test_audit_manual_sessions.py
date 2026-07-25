from datetime import datetime, timezone
import json

from src.orderflow.manual_execution_ledger import append_record
from src.orderflow.manual_execution_log import ManualExecutionRecord, ManualExecutionStatus
from tools.audit_manual_sessions import audit


def make_record(tmp_id: str, hour: int, status: ManualExecutionStatus) -> ManualExecutionRecord:
    base = datetime(2026, 7, 25, hour, 0, tzinfo=timezone.utc)
    return ManualExecutionRecord(
        record_id=tmp_id, episode_id=f"ep-{tmp_id}", symbol="BTCUSD",
        window_sec=300, checkpoint_time=base, checkpoint_stage="STALLED",
        pressure_side="BUY", signal_displayed_time=base, decision_time=None,
        order_time=None, fill_time=None, status=status, entry_side=None,
        entry_price=None, entry_bid=None, entry_ask=None, exit_time=None,
        exit_price=None, skip_reason="test" if status is not ManualExecutionStatus.EXECUTED else None,
    )


def test_audit_groups_by_fixed_utc_session(tmp_path):
    path = tmp_path / "manual.jsonl"
    append_record(path, make_record("a", 7, ManualExecutionStatus.SKIPPED))
    append_record(path, make_record("b", 13, ManualExecutionStatus.REJECTED))
    result = audit(path)
    assert result["record_count"] == 2
    assert result["by_session"] == {
        "ASIA": {"SKIPPED": 1},
        "EUROPE_NY_OVERLAP": {"REJECTED": 1},
    }
