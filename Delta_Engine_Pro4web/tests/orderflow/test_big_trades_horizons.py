from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.orderflow.big_trades.constants import DEFAULT_HORIZONS_SECONDS, SnapshotValidity
from src.orderflow.big_trades.horizons import ResultHorizonTracker
from src.orderflow.big_trades.price_path import SourcePricePathIndex
from src.orderflow.big_trades.reaction_zones import ReactionZoneObserver
from src.orderflow.big_trades.reaction_zones import link_event_to_zone
from tests.orderflow._big_trades_helpers import BASE, event_zone, fill


def _tracker(*, horizons=(1,), max_staleness_ms=1_000):
    event, zone, origin_fills = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    path = SourcePricePathIndex(symbol=event.symbol, venue=event.venue)
    for trade in origin_fills:
        path.append(trade)
    return event, zone, observer, path, ResultHorizonTracker(
        event,
        zone,
        observer,
        path,
        horizons_seconds=horizons,
        max_staleness_ms=max_staleness_ms,
    )


def test_default_horizons_are_exact_contract_values() -> None:
    assert DEFAULT_HORIZONS_SECONDS == (1, 5, 15, 30, 60, 180, 300, 600)


def test_snapshot_uses_last_trade_at_target_not_trigger_trade() -> None:
    event, _, observer, path, tracker = _tracker()
    before = fill(1_060, "105", trade_id=10)
    trigger = fill(1_061, "200", trade_id=11)
    for trade in (before, trigger):
        path.append(trade)
        observer.observe_trade(trade)
    snapshots = tracker.on_trade(trigger)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.snapshot_price == Decimal("105")
    assert snapshot.snapshot_trade_id == 10
    assert snapshot.snapshot_source_age_ms == 0
    assert snapshot.max_above_ticks_to_horizon == Decimal("3")
    assert snapshot.validity is SnapshotValidity.VALID
    assert snapshot.return_from_last_price_bps == Decimal("105") / Decimal("102") * 10000 - 10000


def test_source_age_exactly_1000ms_is_valid_and_1001ms_is_stale() -> None:
    event, _, _, path, tracker = _tracker(horizons=(1, 5))
    first_trigger = fill(1_061, "110", trade_id=10)
    path.append(first_trigger)
    one_second = tracker.on_trade(first_trigger)[0]
    assert one_second.snapshot_source_age_ms == 1_000
    assert one_second.validity is SnapshotValidity.VALID

    near_five = fill(4_059, "104", trade_id=11)
    five_trigger = fill(5_061, "120", trade_id=12)
    path.append(near_five)
    path.append(five_trigger)
    five_second = tracker.on_trade(five_trigger)[0]
    assert five_second.horizon_seconds == 5
    assert five_second.validity is SnapshotValidity.MISSING_STALE
    assert five_second.snapshot_price is None
    assert five_second.snapshot_source_age_ms is None


def test_gap_crossing_horizon_is_missing_without_interpolation() -> None:
    _, _, _, path, tracker = _tracker(horizons=(30,))
    path.start_gap(BASE + timedelta(seconds=20))
    path.end_gap(BASE + timedelta(seconds=40))
    trigger = fill(30_061, "110", trade_id=10)
    path.append(trigger)
    snapshot = tracker.on_trade(trigger)[0]
    assert snapshot.validity is SnapshotValidity.MISSING_SOURCE_GAP
    assert snapshot.snapshot_price is None


def test_horizon_crossing_utc_session_is_missing_session() -> None:
    late_base = BASE.replace(hour=23, minute=59, second=59, microsecond=500_000)
    event, zone, origin_fills = event_zone(base=late_base)
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    path = SourcePricePathIndex(symbol=event.symbol, venue=event.venue)
    for trade in origin_fills:
        path.append(trade)
    tracker = ResultHorizonTracker(event, zone, observer, path, horizons_seconds=(1,))
    trigger = fill(1_061, "110", trade_id=10, base=late_base)
    path.append(trigger)
    assert tracker.on_trade(trigger)[0].validity is SnapshotValidity.MISSING_SESSION


def _fact_rich_snapshot(side: str):
    event, zone, origin_fills = event_zone(side=side)
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    path = SourcePricePathIndex(symbol=event.symbol, venue=event.venue)
    for trade in origin_fills:
        path.append(trade)
    observations = (
        fill(100, "103", "1", "BUY", trade_id=10),
        fill(200, "102", "2", "SELL", trade_id=11),
        fill(300, "99", "3", "BUY", trade_id=12),
    )
    for trade in observations:
        path.append(trade)
        observer.observe_trade(trade)
    linked, _, _ = event_zone(
        prices=("101",),
        quantities=("7",),
        side="SELL" if side == "BUY" else "BUY",
        times_ms=(500,),
        minimum="0",
    )
    link = link_event_to_zone(
        zone, linked, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=1
    )
    assert link is not None
    observer.register_link(link, linked_trade_id=linked.last_trade_id)
    at_target = fill(1_060, "104", "1", "BUY", trade_id=13)
    path.append(at_target)
    observer.observe_trade(at_target)
    tracker = ResultHorizonTracker(
        event, zone, observer, path, horizons_seconds=(1,), max_staleness_ms=1_000
    )
    trigger = fill(1_061, "500", trade_id=14)
    path.append(trigger)
    return tracker.on_trade(trigger)[0]


def test_snapshot_cuts_off_future_trade_and_preserves_all_metric_facts() -> None:
    snapshot = _fact_rich_snapshot("BUY")
    assert snapshot.snapshot_price == Decimal("104")
    assert snapshot.max_above_ticks_to_horizon == Decimal("2")
    assert snapshot.max_below_ticks_to_horizon == Decimal("1")
    assert snapshot.touch_count_to_horizon == 1
    assert snapshot.cross_count_to_horizon == 1
    assert snapshot.linked_big_trade_count_to_horizon == 1
    assert snapshot.inside_sell_quantity_to_horizon == Decimal("2")
    assert snapshot.origin_side_signed_return_bps == snapshot.return_from_vwap_bps


def test_sell_signed_return_is_inverse_and_replay_speed_independent() -> None:
    first = _fact_rich_snapshot("SELL")
    second = _fact_rich_snapshot("SELL")
    assert first == second
    assert first.origin_side_signed_return_bps == -first.return_from_vwap_bps
