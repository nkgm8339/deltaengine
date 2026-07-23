"""CvdCalculator.current_bar_snapshot — 進行中バーの非破壊スナップショット."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.orderflow.cvd import CvdCalculator, Trade

T0 = datetime(2026, 7, 18, 12, 0, 5, tzinfo=timezone.utc)


def _trade(i, price, qty, side, t=T0):
    return Trade(
        trade_id=i, event_time=t, symbol="BTCUSDT",
        price=Decimal(price), quantity=Decimal(qty), side=side,
    )


def test_snapshot_none_before_first_trade():
    calc = CvdCalculator("BTCUSDT", "1m")
    assert calc.current_bar_snapshot() is None


def test_snapshot_reflects_running_bar_values():
    calc = CvdCalculator("BTCUSDT", "1m")
    calc.process(_trade(1, "100", "2", "BUY"))
    calc.process(_trade(2, "101", "1", "SELL"))
    snap = calc.current_bar_snapshot()
    assert snap is not None
    assert snap.open == Decimal("100")
    assert snap.high == Decimal("101")
    assert snap.close == Decimal("101")
    assert snap.volume == Decimal("3")
    assert snap.delta == Decimal("1")   # +2 -1
    assert snap.cvd == Decimal("1")
    assert snap.bar_time == datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def test_snapshot_is_non_destructive():
    calc = CvdCalculator("BTCUSDT", "1m")
    calc.process(_trade(1, "100", "2", "BUY"))
    before = calc.current_bar_snapshot()
    again = calc.current_bar_snapshot()
    assert before == again                      # 何度呼んでも同じ
    calc.process(_trade(2, "100", "1", "BUY"))  # 状態は生きている
    after = calc.current_bar_snapshot()
    assert after.volume == Decimal("3")
    # スナップショット後もバーは閉じておらず finalize で確定できる
    final = calc.finalize()
    assert final is not None and final.volume == Decimal("3")
