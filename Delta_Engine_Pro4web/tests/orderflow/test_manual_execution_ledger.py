import pytest

from src.orderflow.manual_execution_ledger import decode_record, encode_record, load_records
from tests.orderflow.test_manual_execution_log import executed


def test_json_round_trip_preserves_record_and_delay():
    record = executed()
    decoded = decode_record(encode_record(record))
    assert decoded == record
    assert decoded.execution_delay_ms == 4_000


def test_missing_path_is_empty():
    assert load_records(__import__("pathlib").Path("path-that-does-not-exist.jsonl")) == ()


def test_invalid_line_and_unknown_status_are_rejected():
    with pytest.raises(ValueError, match="invalid manual"):
        decode_record("{not-json}")
    line = encode_record(executed()).replace("EXECUTED", "UNKNOWN")
    with pytest.raises(ValueError, match="invalid manual"):
        decode_record(line)
