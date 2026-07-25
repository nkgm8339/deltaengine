import json

import pytest

from src.orderflow.manual_execution_ledger import encode_record
from tests.orderflow.test_manual_execution_log import executed
from tools.append_manual_execution import append_json_text


def test_append_json_text_rejects_invalid_record():
    with pytest.raises(ValueError, match="invalid manual"):
        append_json_text(__import__("pathlib").Path("unused-ledger.jsonl"), "{}")


def test_record_payload_can_be_prepared_for_cli():
    payload = json.loads(encode_record(executed()))
    assert payload["record_id"] == "m-1"
    assert payload["status"] == "EXECUTED"
