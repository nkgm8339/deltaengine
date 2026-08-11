"""Frozen value models used by the Big Trades V2 pure core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from .constants import (
    AGGREGATION_CANDLE_TIMEFRAME,
    AGGREGATION_WINDOW_MS,
    ASSESSMENT_NOTE_MAX_LENGTH,
    INPUT_MODE_AGGREGATE_TRADES,
    LOGIC_VERSION,
    AutomaticIntensity,
    CandleResultLabel,
    ClusterCloseReason,
    FilterDecisionReason,
    FilterMode,
    InteractionType,
    MarkerPriceMode,
    PriceRelation,
    SideFilter,
    SnapshotValidity,
    UserAssessmentValue,
    ZoneLifecycle,
)
from .time_buckets import candle_id, event_time_ms, require_aware_utc, session_id, source_key


ZERO = Decimal("0")


def _finite_positive(value: Decimal | str | int, name: str) -> Decimal:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed <= ZERO:
        raise ValueError(f"{name} must be a finite positive Decimal")
    return parsed


def _finite_nonnegative(value: Decimal | str | int, name: str) -> Decimal:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{name} must be a finite non-negative Decimal")
    return parsed


@dataclass(frozen=True)
class BigTradeFill:
    event_time: datetime
    trade_time: datetime
    trade_id: int
    symbol: str
    venue: str
    price: Decimal
    quantity: Decimal
    side: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_aware_utc(self.event_time, "event_time"))
        object.__setattr__(self, "trade_time", require_aware_utc(self.trade_time, "trade_time"))
        if not isinstance(self.trade_id, int) or isinstance(self.trade_id, bool) or self.trade_id < 0:
            raise ValueError("trade_id must be a non-negative integer")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be non-empty")
        if not isinstance(self.venue, str) or not self.venue:
            raise ValueError("venue must be non-empty")
        object.__setattr__(self, "price", _finite_positive(self.price, "price"))
        object.__setattr__(self, "quantity", _finite_positive(self.quantity, "quantity"))
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

    @property
    def event_time_ms(self) -> int:
        return event_time_ms(self.event_time)

    @property
    def source_key(self) -> tuple[int, int]:
        return source_key(self.event_time, self.trade_id)

    @property
    def session_id(self) -> str:
        return session_id(self.event_time)

    @property
    def candle_id(self) -> int:
        return candle_id(self.event_time)

    @classmethod
    def from_normalized(cls, trade: Any, *, venue: str) -> "BigTradeFill":
        return cls(
            event_time=trade.event_time,
            trade_time=getattr(trade, "trade_time", trade.event_time),
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            venue=venue,
            price=trade.price,
            quantity=trade.quantity,
            side=trade.side,
        )


@dataclass(frozen=True)
class BigTradesSettingsSnapshot:
    settings_id: str
    symbol: str
    venue: str
    filter_mode: FilterMode
    manual_min_quantity: Decimal = ZERO
    manual_max_quantity: Decimal = ZERO
    automatic_intensity: AutomaticIntensity = AutomaticIntensity.MEDIUM
    side_filter: SideFilter = SideFilter.BOTH
    marker_price_mode: MarkerPriceMode = MarkerPriceMode.LAST_PRICE
    calibration_id: Optional[str] = None
    activation_id: Optional[str] = None
    input_mode: str = INPUT_MODE_AGGREGATE_TRADES
    logic_version: str = LOGIC_VERSION

    def __post_init__(self) -> None:
        if not self.settings_id:
            raise ValueError("settings_id must be non-empty")
        if not self.symbol or not self.venue:
            raise ValueError("symbol and venue must be non-empty")
        object.__setattr__(
            self,
            "manual_min_quantity",
            _finite_nonnegative(self.manual_min_quantity, "manual_min_quantity"),
        )
        object.__setattr__(
            self,
            "manual_max_quantity",
            _finite_nonnegative(self.manual_max_quantity, "manual_max_quantity"),
        )
        if self.manual_max_quantity > ZERO and self.manual_max_quantity < self.manual_min_quantity:
            raise ValueError("manual_max_quantity must be zero or >= manual_min_quantity")
        if self.input_mode != INPUT_MODE_AGGREGATE_TRADES:
            raise ValueError("only AGGREGATE_TRADES is supported")


@dataclass(frozen=True)
class ExecutionCluster:
    fills: tuple[BigTradeFill, ...]
    settings: BigTradesSettingsSnapshot
    close_reason: ClusterCloseReason
    logic_version: str = LOGIC_VERSION
    input_mode: str = INPUT_MODE_AGGREGATE_TRADES

    def __post_init__(self) -> None:
        if not self.fills:
            raise ValueError("cluster must contain at least one fill")
        first = self.fills[0]
        previous_key: Optional[tuple[int, int]] = None
        for fill in self.fills:
            if fill.symbol != first.symbol or fill.venue != first.venue or fill.side != first.side:
                raise ValueError("cluster fills must have one symbol, venue, and side")
            if fill.session_id != first.session_id or fill.candle_id != first.candle_id:
                raise ValueError("cluster fills must share session and candle")
            if previous_key is not None and fill.source_key < previous_key:
                raise ValueError("cluster fills must be source ordered")
            previous_key = fill.source_key
        if self.settings.symbol != first.symbol or self.settings.venue != first.venue:
            raise ValueError("settings identity must match cluster")

    @property
    def symbol(self) -> str:
        return self.fills[0].symbol

    @property
    def venue(self) -> str:
        return self.fills[0].venue

    @property
    def side(self) -> str:
        return self.fills[0].side

    @property
    def first_time(self) -> datetime:
        return self.fills[0].event_time

    @property
    def last_time(self) -> datetime:
        return self.fills[-1].event_time

    @property
    def first_trade_id(self) -> int:
        return self.fills[0].trade_id

    @property
    def last_trade_id(self) -> int:
        return self.fills[-1].trade_id

    @property
    def first_price(self) -> Decimal:
        return self.fills[0].price

    @property
    def last_price(self) -> Decimal:
        return self.fills[-1].price

    @property
    def low_price(self) -> Decimal:
        return min(fill.price for fill in self.fills)

    @property
    def high_price(self) -> Decimal:
        return max(fill.price for fill in self.fills)

    @property
    def aggregate_quantity(self) -> Decimal:
        return sum((fill.quantity for fill in self.fills), ZERO)

    @property
    def aggregate_notional(self) -> Decimal:
        return sum((fill.price * fill.quantity for fill in self.fills), ZERO)

    @property
    def vwap(self) -> Decimal:
        return self.aggregate_notional / self.aggregate_quantity

    @property
    def fill_count(self) -> int:
        return len(self.fills)

    @property
    def price_level_count(self) -> int:
        return len({fill.price for fill in self.fills})

    @property
    def duration_ms(self) -> int:
        return self.fills[-1].event_time_ms - self.fills[0].event_time_ms

    @property
    def session_id(self) -> str:
        return self.fills[0].session_id

    @property
    def candle_id(self) -> int:
        return self.fills[0].candle_id


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: FilterDecisionReason
    threshold_used: Decimal
    max_threshold_used: Decimal
    filter_mode: FilterMode
    intensity: Optional[AutomaticIntensity]
    calibration_id: Optional[str]


@dataclass(frozen=True)
class BigTradeEvent:
    event_id: str
    content_hash: str
    logic_version: str
    symbol: str
    venue: str
    side: str
    input_mode: str
    first_trade_id: int
    last_trade_id: int
    first_time: datetime
    last_time: datetime
    event_time: datetime
    marker_time: datetime
    first_price: Decimal
    last_price: Decimal
    marker_price: Decimal
    low_price: Decimal
    high_price: Decimal
    vwap: Decimal
    aggregate_quantity: Decimal
    aggregate_notional: Decimal
    fill_count: int
    price_level_count: int
    duration_ms: int
    close_reason: ClusterCloseReason
    filter_mode: FilterMode
    intensity: Optional[AutomaticIntensity]
    threshold_used: Decimal
    max_threshold_used: Decimal
    side_filter: SideFilter
    marker_price_mode: MarkerPriceMode
    settings_id: str
    calibration_id: Optional[str]
    activation_id: Optional[str]
    session_id: str
    candle_id: int
    aggregation_window_ms: int = AGGREGATION_WINDOW_MS
    aggregation_candle_timeframe: str = AGGREGATION_CANDLE_TIMEFRAME
    schema_version: int = 2


@dataclass(frozen=True)
class ReactionZone:
    zone_id: str
    content_hash: str
    origin_event_id: str
    zone_low: Decimal
    zone_high: Decimal
    zone_anchor: Decimal
    zone_visual_start: datetime
    zone_source_start: datetime
    origin_last_trade_id: int
    origin_last_price: Decimal
    origin_side: str
    symbol: str
    venue: str
    session_id: str
    logic_version: str
    settings_id: str
    calibration_id: Optional[str]
    activation_id: Optional[str]
    lifecycle: ZoneLifecycle = ZoneLifecycle.ACTIVE
    zone_schema_version: int = 1


@dataclass(frozen=True)
class ZoneInteraction:
    interaction_id: str
    content_hash: str
    zone_id: str
    interaction_type: InteractionType
    source_event_time: datetime
    source_trade_id: Optional[int]
    source_candle_id: Optional[int]
    price: Optional[Decimal]
    previous_relation: Optional[PriceRelation]
    current_relation: Optional[PriceRelation]
    direction: Optional[str]
    ordinal: int
    gap_epoch_id: Optional[str] = None
    time_to_exit_ms: Optional[int] = None
    distance_from_nearest_boundary_ticks: Optional[Decimal] = None


@dataclass(frozen=True)
class ZoneMetricsSnapshot:
    source_event_time: datetime
    source_trade_id: int
    relation: PriceRelation
    max_price_seen: Decimal
    min_price_seen: Decimal
    max_above_ticks: Decimal
    max_below_ticks: Decimal
    max_above_bps: Decimal
    max_below_bps: Decimal
    touch_count: int
    reentry_count: int
    cross_count: int
    linked_big_trade_count: int
    linked_buy_quantity: Decimal
    linked_sell_quantity: Decimal
    inside_buy_quantity: Decimal
    inside_sell_quantity: Decimal
    inside_buy_trade_count: int
    inside_sell_trade_count: int


@dataclass(frozen=True)
class ZoneEventLink:
    link_id: str
    content_hash: str
    zone_id: str
    origin_event_id: str
    linked_event_id: str
    linked_side: str
    linked_quantity: Decimal
    linked_low: Decimal
    linked_high: Decimal
    linked_time: datetime
    interval_gap_ticks: Decimal
    same_as_origin_side: bool
    ordinal_for_zone: int


@dataclass(frozen=True)
class PriceObservation:
    event_time: datetime
    trade_id: int
    price: Decimal
    symbol: str
    venue: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_aware_utc(self.event_time))
        object.__setattr__(self, "price", _finite_positive(self.price, "price"))

    @property
    def source_key(self) -> tuple[int, int]:
        return source_key(self.event_time, self.trade_id)


@dataclass(frozen=True)
class SourceGap:
    gap_epoch_id: str
    start_time: datetime
    end_time: Optional[datetime]


@dataclass(frozen=True)
class ResultSnapshot:
    snapshot_id: str
    content_hash: str
    zone_id: str
    horizon_seconds: int
    target_time: datetime
    snapshot_trade_id: Optional[int]
    snapshot_trade_time: Optional[datetime]
    snapshot_source_age_ms: Optional[int]
    snapshot_price: Optional[Decimal]
    relation: Optional[PriceRelation]
    return_from_last_price_bps: Optional[Decimal]
    return_from_vwap_bps: Optional[Decimal]
    origin_side_signed_return_bps: Optional[Decimal]
    max_above_ticks_to_horizon: Decimal
    max_below_ticks_to_horizon: Decimal
    touch_count_to_horizon: int
    cross_count_to_horizon: int
    linked_big_trade_count_to_horizon: int
    inside_buy_quantity_to_horizon: Decimal
    inside_sell_quantity_to_horizon: Decimal
    validity: SnapshotValidity


@dataclass(frozen=True)
class ClosedCandle:
    candle_id: int
    open_time: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_time", require_aware_utc(self.open_time, "open_time"))
        for name in ("open", "high", "low", "close"):
            object.__setattr__(self, name, _finite_positive(getattr(self, name), name))
        if self.high < self.low:
            raise ValueError("candle high must be >= candle low")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("candle high/low do not contain the body")


@dataclass(frozen=True)
class ZoneCandleObservation:
    candle_observation_id: str
    content_hash: str
    zone_id: str
    candle_id: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    candle_open_relation: PriceRelation
    candle_close_relation: PriceRelation
    candle_high_above_ticks: Decimal
    candle_low_below_ticks: Decimal
    body_low: Decimal
    body_high: Decimal
    body_overlaps_zone: bool
    wick_overlaps_zone: bool
    closed_above_zone: bool
    closed_below_zone: bool
    returned_inside_after_upper_excursion: bool
    returned_inside_after_lower_excursion: bool
    labels: tuple[CandleResultLabel, ...]


@dataclass(frozen=True)
class ZoneStateCheckpoint:
    checkpoint_id: str
    zone_id: str
    source_bucket_time: datetime
    current_relation: PriceRelation
    first_exit_direction: Optional[str]
    first_exit_time: Optional[datetime]
    touch_count: int
    cross_count: int
    inside_buy_quantity: Decimal
    inside_sell_quantity: Decimal
    linked_event_count: int
    gap_epoch_id: Optional[str]
    content_hash: str


@dataclass(frozen=True)
class UserAssessment:
    assessment_id: str
    zone_id: str
    assessment: str
    assessed_at_utc: datetime
    assessed_against_source_time: datetime
    user_note: Optional[str]
    supersedes_assessment_id: Optional[str]
    content_hash: str

    @classmethod
    def create(
        cls,
        *,
        zone_id: str,
        assessment: UserAssessmentValue | str,
        assessed_at_utc: datetime,
        assessed_against_source_time: datetime,
        user_note: Optional[str] = None,
        supersedes_assessment_id: Optional[str] = None,
    ) -> "UserAssessment":
        from .ids import assessment_id_for_payload, content_hash

        if not zone_id:
            raise ValueError("zone_id must be non-empty")
        if user_note is not None and len(user_note) > ASSESSMENT_NOTE_MAX_LENGTH:
            raise ValueError(
                f"user_note must be <= {ASSESSMENT_NOTE_MAX_LENGTH} characters"
            )
        payload = {
            "zone_id": zone_id,
            "assessment": UserAssessmentValue(assessment).value,
            "assessed_at_utc": require_aware_utc(assessed_at_utc, "assessed_at_utc"),
            "assessed_against_source_time": require_aware_utc(
                assessed_against_source_time,
                "assessed_against_source_time",
            ),
            "user_note": user_note,
            "supersedes_assessment_id": supersedes_assessment_id,
        }
        identifier = assessment_id_for_payload(payload)
        return cls(
            assessment_id=identifier,
            content_hash=content_hash({"assessment_id": identifier, **payload}),
            **payload,
        )
