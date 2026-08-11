from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from src.orderflow.big_trades.constants import InteractionType, PriceRelation, ZoneLifecycle
from src.orderflow.big_trades.reaction_zones import (
    ReactionZoneObserver,
    interval_gap,
    link_event_to_zone,
    relation_for_price,
)
from tests.orderflow._big_trades_helpers import BASE, event_zone, fill


def test_relation_boundaries_are_inclusive() -> None:
    event, zone, _ = event_zone()
    assert zone.zone_low == event.low_price
    assert zone.zone_high == event.high_price
    assert zone.zone_anchor == event.vwap
    assert zone.zone_visual_start == event.first_time
    assert zone.zone_source_start == event.last_time
    assert zone.origin_side == event.side
    assert relation_for_price(zone, Decimal("99.9")) is PriceRelation.BELOW
    assert relation_for_price(zone, Decimal("100")) is PriceRelation.INSIDE
    assert relation_for_price(zone, Decimal("101")) is PriceRelation.INSIDE
    assert relation_for_price(zone, Decimal("102")) is PriceRelation.INSIDE
    assert relation_for_price(zone, Decimal("102.1")) is PriceRelation.ABOVE


def test_single_price_event_creates_zero_height_authoritative_zone() -> None:
    event, zone, _ = event_zone(prices=("100",), quantities=("50",), times_ms=(0,))
    assert event.low_price == event.high_price == Decimal("100")
    assert zone.zone_low == zone.zone_high == Decimal("100")


def test_fixed_vector_first_exit_return_and_excursions() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))

    assert observer.observe_trade(fill(70, "102", "2", "BUY", trade_id=4)) == ()
    exit_interactions = observer.observe_trade(fill(80, "103", "3", "BUY", trade_id=5))
    assert [item.interaction_type for item in exit_interactions] == [
        InteractionType.FIRST_EXIT_UP,
        InteractionType.RELATION_ABOVE,
    ]
    assert exit_interactions[0].time_to_exit_ms == 20
    assert exit_interactions[0].distance_from_nearest_boundary_ticks == Decimal("1")

    observer.observe_trade(fill(90, "104", "4", "BUY", trade_id=6))
    return_interactions = observer.observe_trade(fill(120, "102", "5", "SELL", trade_id=7))
    assert [item.interaction_type for item in return_interactions] == [
        InteractionType.TOUCH_FROM_ABOVE,
        InteractionType.REENTER_FROM_ABOVE,
        InteractionType.RELATION_INSIDE,
    ]
    observer.observe_trade(fill(130, "101", "6", "BUY", trade_id=8))
    observer.observe_trade(fill(150, "99", "7", "SELL", trade_id=9))

    assert observer.first_exit_direction == "UP"
    assert observer.touch_count == 1
    assert observer.reentry_count == 1
    assert observer.cross_count == 0
    assert observer.inside_buy_quantity == Decimal("8")
    assert observer.inside_sell_quantity == Decimal("5")
    assert observer.inside_buy_trade_count == 2
    assert observer.inside_sell_trade_count == 1
    assert observer.metrics[-1].max_above_ticks == Decimal("2")
    assert observer.metrics[-1].max_below_ticks == Decimal("1")


def test_direct_cross_has_no_fabricated_inside_interaction() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    observer.observe_trade(fill(70, "99", trade_id=4))
    interactions = observer.observe_trade(fill(80, "103", trade_id=5))
    assert [item.interaction_type for item in interactions] == [
        InteractionType.CROSS_UP,
        InteractionType.RELATION_ABOVE,
    ]
    assert observer.cross_count == 1
    assert observer.touch_count == 0


def test_down_exit_reentry_continuous_inside_cross_down_and_break_persistence() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    first = observer.observe_trade(fill(70, "99", trade_id=4))
    assert [item.interaction_type for item in first] == [
        InteractionType.FIRST_EXIT_DOWN,
        InteractionType.RELATION_BELOW,
    ]
    returned = observer.observe_trade(fill(80, "100", trade_id=5))
    assert [item.interaction_type for item in returned] == [
        InteractionType.TOUCH_FROM_BELOW,
        InteractionType.REENTER_FROM_BELOW,
        InteractionType.RELATION_INSIDE,
    ]
    assert observer.observe_trade(fill(90, "101", trade_id=6)) == ()
    assert observer.touch_count == 1
    observer.observe_trade(fill(100, "103", trade_id=7))
    crossed = observer.observe_trade(fill(110, "99", trade_id=8))
    assert [item.interaction_type for item in crossed] == [
        InteractionType.CROSS_DOWN,
        InteractionType.RELATION_BELOW,
    ]
    assert observer.first_exit_direction == "DOWN"
    assert observer.cross_count == 1
    assert observer.lifecycle is ZoneLifecycle.ACTIVE
    assert observer.zone == zone


def test_origin_and_old_session_trades_are_not_observed() -> None:
    _, zone, origin_fills = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    assert observer.observe_trade(origin_fills[-1]) == ()
    assert observer.observe_trade(fill(0, "110", base=BASE.replace(day=2))) == ()
    assert len(observer.interactions) == 1


def test_gap_and_source_confirmed_session_close_are_explicit() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    started = observer.start_gap("gap-1", BASE)
    ended = observer.end_gap("gap-1", BASE)
    assert started.interaction_type is InteractionType.SOURCE_GAP_STARTED
    assert ended.interaction_type is InteractionType.SOURCE_GAP_ENDED
    assert observer.lifecycle is ZoneLifecycle.ACTIVE_WITH_GAP

    closed = observer.close_session()
    assert closed.interaction_type is InteractionType.ZONE_SESSION_CLOSED
    assert observer.lifecycle is ZoneLifecycle.SESSION_CLOSED
    assert observer.observe_trade(fill(500, "110", trade_id=99)) == ()


def test_later_event_links_by_interval_gap_without_merging_identity() -> None:
    origin, zone, _ = event_zone()
    later, _, _ = event_zone(
        prices=("99", "100"),
        quantities=("3", "4"),
        side="SELL",
        times_ms=(200, 225),
        minimum="0",
    )
    assert interval_gap(zone, later) == Decimal("0")
    link = link_event_to_zone(
        zone,
        later,
        tick_size=Decimal("1"),
        tolerance_ticks=1,
        ordinal_for_zone=1,
    )
    assert link is not None
    assert link.origin_event_id == origin.event_id
    assert link.linked_event_id == later.event_id
    assert link.same_as_origin_side is False
    assert link.interval_gap_ticks == Decimal("0")

    adjacent, _, _ = event_zone(
        prices=("103",), quantities=("2",), times_ms=(300,), minimum="0"
    )
    assert link_event_to_zone(
        zone, adjacent, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=2
    ) is not None

    too_far, _, _ = event_zone(
        prices=("104", "105"),
        quantities=("2", "3"),
        times_ms=(400, 420),
        minimum="0",
    )
    assert link_event_to_zone(
        zone, too_far, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=3
    ) is None

    assert link_event_to_zone(
        zone,
        replace(later, symbol="ETHUSDT"),
        tick_size=Decimal("1"),
        tolerance_ticks=1,
        ordinal_for_zone=3,
    ) is None
    assert link_event_to_zone(
        zone,
        replace(later, venue="OTHER"),
        tick_size=Decimal("1"),
        tolerance_ticks=1,
        ordinal_for_zone=3,
    ) is None
    assert link_event_to_zone(
        zone,
        replace(later, session_id="2026-01-02"),
        tick_size=Decimal("1"),
        tolerance_ticks=1,
        ordinal_for_zone=3,
    ) is None
    assert not hasattr(link, "participant_id")
    assert not hasattr(link, "parent_order_id")


def test_registered_buy_and_sell_links_update_separate_quantities() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    buy, _, _ = event_zone(prices=("102",), quantities=("4",), times_ms=(200,), minimum="0")
    sell, _, _ = event_zone(
        prices=("100",), quantities=("7",), side="SELL", times_ms=(300,), minimum="0"
    )
    buy_link = link_event_to_zone(
        zone, buy, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=1
    )
    sell_link = link_event_to_zone(
        zone, sell, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=2
    )
    assert buy_link is not None and sell_link is not None
    assert buy_link.ordinal_for_zone == 1
    assert sell_link.ordinal_for_zone == 2
    observer.register_link(buy_link, linked_trade_id=buy.last_trade_id)
    observer.register_link(sell_link, linked_trade_id=sell.last_trade_id)
    assert observer.linked_big_trade_count == 2
    assert observer.linked_buy_quantity == Decimal("4")
    assert observer.linked_sell_quantity == Decimal("7")


def test_delayed_link_discovery_records_metrics_at_observation_source_key() -> None:
    _, zone, _ = event_zone()
    observer = ReactionZoneObserver(zone, tick_size=Decimal("1"))
    linked, _, _ = event_zone(
        prices=("102",), quantities=("4",), times_ms=(200,), minimum="0"
    )
    link = link_event_to_zone(
        zone, linked, tick_size=Decimal("1"), tolerance_ticks=1, ordinal_for_zone=1
    )
    trigger = fill(300, "103", trade_id=50)
    observer.observe_trade(trigger)
    assert link is not None

    observer.register_link(
        link,
        linked_trade_id=linked.last_trade_id,
        observed_time=trigger.event_time,
        observed_trade_id=trigger.trade_id,
    )

    assert observer.metrics_at_or_before(link.linked_time).linked_big_trade_count == 0
    assert observer.metrics_at_or_before(trigger.event_time).linked_big_trade_count == 1


def test_overlapping_zones_each_observe_one_trade_once() -> None:
    _, first_zone, _ = event_zone()
    second_zone = replace(
        first_zone,
        zone_id="btz2_overlap",
        origin_event_id="bt2_overlap",
        zone_low=Decimal("101"),
        zone_high=Decimal("103"),
    )
    first = ReactionZoneObserver(first_zone, tick_size=Decimal("1"))
    second = ReactionZoneObserver(second_zone, tick_size=Decimal("1"))
    trade = fill(70, "101.5", "2", "BUY", trade_id=10)
    first.observe_trade(trade)
    second.observe_trade(trade)
    assert first.inside_buy_trade_count == 1
    assert second.inside_buy_trade_count == 1
    assert first.inside_buy_quantity == second.inside_buy_quantity == Decimal("2")
