"""Deterministic Big Trades V2 effort/result core.

The package is intentionally independent from storage, networking, UI, and
order execution.  Runtime integration is layered on top of these pure models.
"""

from .aggregation import ExecutionClusterAggregator, create_big_trade_event
from .candle_observer import ZoneCandleObserver
from .constants import (
    AutomaticIntensity,
    ClusterCloseReason,
    FilterDecisionReason,
    FilterMode,
    InteractionType,
    MarkerPriceMode,
    PriceRelation,
    SideFilter,
    SnapshotValidity,
    ZoneLifecycle,
)
from .filtering import AutomaticSizeFilter, ManualSizeFilter
from .horizons import ResultHorizonTracker
from .models import (
    BigTradeEvent,
    BigTradeFill,
    BigTradesSettingsSnapshot,
    ClosedCandle,
    ExecutionCluster,
    ReactionZone,
    ResultSnapshot,
    ZoneCandleObservation,
    ZoneEventLink,
    ZoneInteraction,
)
from .ordering import SameMillisecondTradeOrderBuffer
from .reaction_zones import ReactionZoneObserver, create_reaction_zone, link_event_to_zone

__all__ = [
    "AutomaticIntensity",
    "AutomaticSizeFilter",
    "BigTradeEvent",
    "BigTradeFill",
    "BigTradesSettingsSnapshot",
    "ClosedCandle",
    "ClusterCloseReason",
    "ExecutionCluster",
    "ExecutionClusterAggregator",
    "FilterDecisionReason",
    "FilterMode",
    "InteractionType",
    "ManualSizeFilter",
    "MarkerPriceMode",
    "PriceRelation",
    "ReactionZone",
    "ReactionZoneObserver",
    "ResultHorizonTracker",
    "ResultSnapshot",
    "SameMillisecondTradeOrderBuffer",
    "SideFilter",
    "SnapshotValidity",
    "ZoneCandleObservation",
    "ZoneCandleObserver",
    "ZoneEventLink",
    "ZoneInteraction",
    "ZoneLifecycle",
    "create_big_trade_event",
    "create_reaction_zone",
    "link_event_to_zone",
]
