from __future__ import annotations

from decimal import Decimal

import pytest

from src.orderflow.big_trades.candle_observer import CandleBoundaryMismatch, ZoneCandleObserver
from src.orderflow.big_trades.constants import CandleResultLabel, PriceRelation
from src.orderflow.big_trades.models import ClosedCandle
from src.orderflow.big_trades.time_buckets import candle_id
from tests.orderflow._big_trades_helpers import BASE, event_zone


def _candle(*, open_price: str, high: str, low: str, close: str, identifier: int | None = None):
    return ClosedCandle(
        candle_id=candle_id(BASE) if identifier is None else identifier,
        open_time=BASE,
        symbol="BTCUSDT",
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def test_upper_wick_return_and_close_above_are_distinct_facts() -> None:
    _, zone, _ = event_zone()
    observer = ZoneCandleObserver(tick_size=Decimal("1"))
    returned = observer.observe(
        zone, _candle(open_price="101", high="105", low="100", close="101")
    )
    assert returned.returned_inside_after_upper_excursion is True
    assert returned.closed_above_zone is False
    assert returned.labels == (
        CandleResultLabel.CLOSED_INSIDE,
        CandleResultLabel.UPPER_WICK_RETURN,
    )
    assert returned.candle_high_above_ticks == Decimal("3")

    above = observer.observe(
        zone, _candle(open_price="101", high="105", low="100", close="104")
    )
    assert above.closed_above_zone is True
    assert above.returned_inside_after_upper_excursion is False
    assert above.candle_close_relation is PriceRelation.ABOVE
    assert above.labels == (CandleResultLabel.CLOSE_ABOVE,)


def test_lower_wick_return_and_exact_boundary_close() -> None:
    _, zone, _ = event_zone()
    result = ZoneCandleObserver(tick_size=Decimal("1")).observe(
        zone, _candle(open_price="101", high="102", low="97", close="100")
    )
    assert result.candle_close_relation is PriceRelation.INSIDE
    assert result.returned_inside_after_lower_excursion is True
    assert result.candle_low_below_ticks == Decimal("3")
    assert result.labels == (
        CandleResultLabel.CLOSED_INSIDE,
        CandleResultLabel.LOWER_WICK_RETURN,
    )


def test_candle_boundary_mismatch_is_explicit() -> None:
    _, zone, _ = event_zone()
    bad = _candle(open_price="100", high="102", low="99", close="101", identifier=1)
    with pytest.raises(CandleBoundaryMismatch, match="CANDLE_BOUNDARY_MISMATCH"):
        ZoneCandleObserver(tick_size=Decimal("1")).observe(zone, bad)


def test_invalid_candle_high_below_low_is_rejected() -> None:
    with pytest.raises(ValueError, match="high must be"):
        _candle(open_price="100", high="99", low="101", close="100")
