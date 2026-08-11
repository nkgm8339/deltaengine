from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.orderflow.big_trades.aggregation import create_big_trade_event
from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    ClusterCloseReason,
    FilterMode,
    MarkerPriceMode,
    SideFilter,
)
from src.orderflow.big_trades.filtering import ManualSizeFilter
from src.orderflow.big_trades.models import (
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ExecutionCluster,
)
from src.orderflow.big_trades.reaction_zones import create_reaction_zone


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def fill(
    ms: int,
    price: str = "100",
    quantity: str = "1",
    side: str = "BUY",
    *,
    trade_id: int | None = None,
    symbol: str = "BTCUSDT",
    venue: str = "BINANCE",
    base: datetime = BASE,
) -> BigTradeFill:
    timestamp = base + timedelta(milliseconds=ms)
    return BigTradeFill(
        event_time=timestamp,
        trade_time=timestamp,
        trade_id=ms if trade_id is None else trade_id,
        symbol=symbol,
        venue=venue,
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
    )


def settings(
    *,
    settings_id: str = "settings-1",
    filter_mode: FilterMode = FilterMode.MANUAL,
    minimum: str = "0",
    maximum: str = "0",
    intensity: AutomaticIntensity = AutomaticIntensity.MEDIUM,
    calibration_id: str | None = None,
    marker_price_mode: MarkerPriceMode = MarkerPriceMode.LAST_PRICE,
) -> BigTradesSettingsSnapshot:
    return BigTradesSettingsSnapshot(
        settings_id=settings_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        filter_mode=filter_mode,
        manual_min_quantity=Decimal(minimum),
        manual_max_quantity=Decimal(maximum),
        automatic_intensity=intensity,
        side_filter=SideFilter.BOTH,
        marker_price_mode=marker_price_mode,
        calibration_id=calibration_id,
    )


def event_zone(
    *,
    prices: tuple[str, ...] = ("100", "101", "102"),
    quantities: tuple[str, ...] = ("18", "17", "20"),
    side: str = "BUY",
    times_ms: tuple[int, ...] = (0, 25, 60),
    minimum: str = "50",
    base: datetime = BASE,
):
    configured = settings(minimum=minimum)
    fills = tuple(
        fill(ms, price, quantity, side, trade_id=index + 1, base=base)
        for index, (ms, price, quantity) in enumerate(zip(times_ms, prices, quantities, strict=True))
    )
    cluster = ExecutionCluster(fills, configured, ClusterCloseReason.SIDE_CHANGED)
    decision = ManualSizeFilter(Decimal(minimum), Decimal("0")).decide(cluster.aggregate_quantity)
    event = create_big_trade_event(cluster, decision)
    return event, create_reaction_zone(event), fills
