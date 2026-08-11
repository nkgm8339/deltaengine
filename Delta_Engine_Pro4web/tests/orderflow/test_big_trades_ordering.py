from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from tests.orderflow._big_trades_helpers import fill
from src.orderflow.big_trades.ordering import SameMillisecondTradeOrderBuffer


def test_same_millisecond_bucket_releases_by_integer_trade_id() -> None:
    buffer = SameMillisecondTradeOrderBuffer()
    assert buffer.push(fill(0, trade_id=30)) == ()
    assert buffer.push(fill(0, trade_id=10)) == ()
    assert buffer.push(fill(0, trade_id=20)) == ()
    released = buffer.push(fill(1, trade_id=40))
    assert [trade.trade_id for trade in released] == [10, 20, 30]
    assert [trade.trade_id for trade in buffer.flush()] == [40]


def test_late_trade_after_release_is_rejected() -> None:
    buffer = SameMillisecondTradeOrderBuffer()
    buffer.push(fill(1, trade_id=1))
    buffer.push(fill(2, trade_id=2))
    assert buffer.push(fill(1, trade_id=3)) == ()
    assert buffer.rejections[-1].reason == "LATE_AFTER_RELEASE"


def test_older_than_current_open_bucket_is_rejected() -> None:
    buffer = SameMillisecondTradeOrderBuffer()
    buffer.push(fill(2, trade_id=2))
    assert buffer.push(fill(1, trade_id=1)) == ()
    assert buffer.rejected_count == 1


def test_empty_flush_is_idempotent() -> None:
    buffer = SameMillisecondTradeOrderBuffer()
    assert buffer.flush() == ()
    assert buffer.flush() == ()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("price", "0"),
        ("price", "-1"),
        ("price", "NaN"),
        ("price", "Infinity"),
        ("quantity", "0"),
        ("quantity", "-1"),
        ("quantity", "NaN"),
        ("quantity", "Infinity"),
    ),
)
def test_invalid_decimal_trade_values_are_rejected(field: str, value: str) -> None:
    values = {"price": "100", "quantity": "1"}
    values[field] = value
    with pytest.raises(ValueError):
        fill(0, values["price"], values["quantity"])


def test_decimal_trade_values_are_preserved_exactly() -> None:
    trade = fill(0, "100.123456789", "0.00123456789")
    assert trade.price == Decimal("100.123456789")
    assert trade.quantity == Decimal("0.00123456789")


def test_unknown_side_and_timezone_naive_are_rejected() -> None:
    with pytest.raises(ValueError, match="BUY or SELL"):
        fill(0, side="UNKNOWN")
    with pytest.raises(ValueError, match="timezone-aware"):
        fill(0, base=datetime(2026, 1, 1))
