"""Canonical catalog registry for all 88 Hook IDs."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .models import DirectionHint


@dataclass(frozen=True)
class HookDefinition:
    hook_id: str
    category: str
    name: str
    direction_hint: DirectionHint
    suspected: bool = False


_NAMES: dict[str, tuple[str, ...]] = {
    "A": (
        "large_bid_wall_appeared", "large_ask_wall_appeared",
        "bid_wall_pulled", "ask_wall_pulled",
        "bid_depth_thinned", "ask_depth_thinned",
        "bid_depth_strengthened", "ask_depth_strengthened",
        "book_asymmetry_bid", "book_asymmetry_ask",
        "best_bid_retreat", "best_ask_retreat",
        "best_bid_advance", "best_ask_advance",
        "spread_expansion", "spread_recovery",
        "bid_iceberg_suspected", "ask_iceberg_suspected",
        "bid_spoofing_suspected", "ask_spoofing_suspected",
        "upside_vacuum", "downside_vacuum",
        "bid_wall_tracks_up", "ask_wall_tracks_down",
    ),
    "B": (
        "consecutive_market_buys", "consecutive_market_sells",
        "buy_aggression", "sell_aggression",
        "trade_speed_spike", "trade_pause",
        "large_market_buy", "large_market_sell",
        "large_buy_cluster", "large_sell_cluster",
        "buy_sweep", "sell_sweep",
        "average_trade_size_spike", "small_trade_burst",
        "buy_delta_spike", "sell_delta_spike",
        "delta_flip_buy_to_sell", "delta_flip_sell_to_buy",
        "directional_persistence", "high_volume_neutral_delta",
    ),
    "C": (
        "buy_absorption", "sell_absorption",
        "buy_absorption_failed", "sell_absorption_failed",
        "repeated_absorption", "wall_collision_started",
        "ask_wall_consumed", "bid_wall_consumed",
        "liquidation_absorbed",
    ),
    "D": (
        "buy_effective_transition", "sell_effective_transition",
        "buy_trapped_transition", "sell_trapped_transition",
        "stalled_transition", "effective_to_trapped_fast",
        "trapped_resolved", "multi_window_alignment",
    ),
    "E": (
        "large_long_liquidation", "large_short_liquidation",
        "long_liquidation_cascade", "short_liquidation_cascade",
        "liquidation_no_price_response", "liquidation_exhaustion",
    ),
    "F": (
        "oi_up_price_up", "oi_up_price_down",
        "oi_down_price_up", "oi_down_price_down", "oi_shock",
    ),
    "G": (
        "recent_high_touch", "recent_low_touch",
        "high_break", "low_break",
        "failed_high_break", "failed_low_break",
        "vwap_touch", "vwap_deviation_extreme",
        "volume_node_touch", "round_number_touch",
        "range_edge", "higher_timeframe_direction",
    ),
    "H": (
        "session_context", "high_volatility_context",
        "low_liquidity_context", "hfm_spread_normal",
    ),
}


def _direction(hook_id: str) -> DirectionHint:
    up = {
        "A01", "A04", "A06", "A07", "A09", "A12", "A13", "A17", "A20",
        "A21", "A23", "B01", "B03", "B07", "B09", "B11", "B15", "B18",
        "C01", "C04", "C07", "D01", "D04", "E02", "E04", "F01", "F03",
        "G03", "G06",
    }
    down = {
        "A02", "A03", "A05", "A08", "A10", "A11", "A14", "A18", "A19",
        "A22", "A24", "B02", "B04", "B08", "B10", "B12", "B16", "B17",
        "C02", "C03", "C08", "D02", "D03", "E01", "E03", "F02", "F04",
        "G04", "G05",
    }
    if hook_id in up:
        return DirectionHint.UP
    if hook_id in down:
        return DirectionHint.DOWN
    if hook_id in {"C05", "C06", "D05", "D06", "D07", "D08", "E05", "E06", "F05", "G11", "G12"}:
        return DirectionHint.BOTH
    return DirectionHint.NONE


def _build() -> dict[str, HookDefinition]:
    result: dict[str, HookDefinition] = {}
    for category, names in _NAMES.items():
        for index, name in enumerate(names, start=1):
            hook_id = f"{category}{index:02d}"
            result[hook_id] = HookDefinition(
                hook_id=hook_id,
                category=category,
                name=name,
                direction_hint=_direction(hook_id),
                suspected=hook_id in {"A17", "A18", "A19", "A20"},
            )
    return result


HOOK_REGISTRY = MappingProxyType(_build())


def require_hook(hook_id: str) -> HookDefinition:
    try:
        return HOOK_REGISTRY[hook_id]
    except KeyError as exc:
        raise ValueError(f"unknown hook_id: {hook_id!r}") from exc
