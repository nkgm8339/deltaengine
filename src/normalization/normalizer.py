"""Data Normalizer — exchange-specific raw events → canonical records.

Spec: docs/30_Modules/DataNormalizer_v3.2.md. Canonical records:
  Trade: docs/40_Reference/MarketDataSchema_v3.2.md (Tick Record).
  Depth: docs/40_Reference/MarketDataSchema_v3.2.md (Order Book Update Record).
Exchange profile schema/sample: docs/40_Reference/YAMLReference_v3.2.md §4.
Sides: docs/40_Reference/EnumDefinitions_v3.1.md (TradeSide).
Errors: docs/40_Reference/ErrorCodes_v3.1.md.

Verified by TestSpecification_v3.2 §4.6 TV-NRM-01..04.
Depth path added in B-1 (DataNormalizer §2 §3 §4 already declared order book
inputs/outputs; this implements that path).

Guarantees (DataNormalizer §5/§7):
    - Deterministic: identical raw sequence + profile/config → identical output.
    - No silent data loss: every discarded/rejected event is counted and logged.
    - Decimal for price/quantity (MarketDataSchema: decimal), no float in values.

Ordering model (reorder_tolerance):
    Events are buffered and released in event_time order behind a watermark of
    `newest_seen - reorder_tolerance`; a late event still in the buffer window is
    reordered (TV-NRM-03). An event older than the last already-emitted event can
    no longer be reordered and is rejected as out-of-order, E3004 (TV-NRM-04).

Implementation note (reported as a spec-refinement candidate): YAMLReference §4
defines `side_rule` as free text. This module interprets side deterministically
from the mapped value's type — a TradeSide string ("BUY"/"SELL") is used
directly; a boolean is resolved via the documented "== true → SELL" grammar.
A structured side spec would remove the free-text dependency.
"""

from __future__ import annotations

import bisect
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from ..orderflow.orderbook import BookLevel, OrderBookUpdate

logger = logging.getLogger("normalization.normalizer")

# --- Error codes (ErrorCodes_v3.1) --------------------------------------------
ERROR_CONFIG_VALIDATION = "E1002"   # invalid / unknown exchange profile
ERROR_INVALID_TRADE = "E3001"       # unmappable field / invalid enum value
ERROR_DUPLICATE_TRADE = "E3002"     # duplicate trade_id
ERROR_OUT_OF_ORDER = "E3004"        # out-of-order beyond reorder tolerance

VALID_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})  # EnumDefinitions TradeSide
VALID_TIMESTAMP_FORMATS: frozenset[str] = frozenset({"epoch_ms", "epoch_us", "iso8601"})
# Required keys in a profile field_mapping (YAMLReference §4 sample).
REQUIRED_MAPPING_FIELDS: frozenset[str] = frozenset(
    {"event_time", "trade_time", "trade_id", "symbol", "price", "quantity",
     "side_field", "side_rule"}
)

_UTC = timezone.utc
_SIDE_TRUE_RE = re.compile(r"true\s*(?:→|->)\s*(BUY|SELL)", re.IGNORECASE)
_SIDE_FALSE_RE = re.compile(r"false\s*(?:→|->)\s*(BUY|SELL)", re.IGNORECASE)


class ProfileError(Exception):
    """Invalid or unknown exchange profile (E1002)."""

    code = ERROR_CONFIG_VALIDATION

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


class NormalizationError(Exception):
    """A raw event that cannot be normalized (E3001)."""

    def __init__(self, reason: str, code: str = ERROR_INVALID_TRADE) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"[{code}] {reason}")


# Required keys in an order_book_mapping block (YAMLReference_v3.2 §4.1).
REQUIRED_OB_MAPPING_FIELDS: frozenset[str] = frozenset({
    "event_type_field", "event_type_snapshot", "event_type_diff",
    "symbol_field", "event_time_field",
    "first_update_id_field", "final_update_id_field",
    "bids_field", "asks_field",
    "level_price_index", "level_quantity_index",
})


# --- Value types --------------------------------------------------------------
@dataclass(frozen=True)
class ExchangeProfile:
    profile_name: str
    field_mapping: dict[str, str]
    timestamp_format: str
    order_book_mapping: Optional[dict[str, Any]] = None   # B-1: optional depth mapping

    @classmethod
    def from_dict(cls, data: Any) -> "ExchangeProfile":
        if not isinstance(data, dict):
            raise ProfileError("profile must be a mapping")
        name = data.get("profile_name")
        mapping = data.get("field_mapping")
        ts_format = data.get("timestamp_format")
        ob_mapping = data.get("order_book_mapping")
        problems: list[str] = []
        if not isinstance(name, str) or not name.strip():
            problems.append("profile_name must be a non-empty string")
        if not isinstance(mapping, dict):
            problems.append("field_mapping must be a mapping")
        else:
            missing = REQUIRED_MAPPING_FIELDS - set(mapping)
            if missing:
                problems.append(f"field_mapping missing fields: {sorted(missing)}")
        if ts_format not in VALID_TIMESTAMP_FORMATS:
            problems.append(f"timestamp_format must be one of {sorted(VALID_TIMESTAMP_FORMATS)}")
        # order_book_mapping is optional; if present, validate required keys.
        validated_ob: Optional[dict[str, Any]] = None
        if ob_mapping is not None:
            if not isinstance(ob_mapping, dict):
                problems.append("order_book_mapping must be a mapping")
            else:
                missing_ob = REQUIRED_OB_MAPPING_FIELDS - set(ob_mapping)
                if missing_ob:
                    problems.append(
                        f"order_book_mapping missing fields: {sorted(missing_ob)}"
                    )
                else:
                    for idx_key in ("level_price_index", "level_quantity_index"):
                        if not isinstance(ob_mapping[idx_key], int):
                            problems.append(
                                f"order_book_mapping.{idx_key} must be an int"
                            )
                if not problems:
                    validated_ob = dict(ob_mapping)
        if problems:
            raise ProfileError("; ".join(problems))
        return cls(
            profile_name=name,
            field_mapping=dict(mapping),
            timestamp_format=ts_format,
            order_book_mapping=validated_ob,
        )


@dataclass(frozen=True)
class NormalizedTrade:
    """Canonical Tick Record (MarketDataSchema_v3.1)."""

    event_time: datetime
    trade_time: datetime
    trade_id: int
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str


@dataclass(frozen=True)
class LiquidationEvent:
    """Canonical Liquidation Record from Binance @forceOrder stream.

    side: the direction of the liquidation order (forced order side).
    SELL = long position was liquidated (forced sell).
    BUY  = short position was liquidated (forced buy).
    """

    event_time: datetime
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class Rejection:
    code: str
    reason: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class NrmRun:
    """Result of a full deterministic run over a raw-event sequence."""

    emitted: list[NormalizedTrade]
    rejections: list[Rejection]
    processed: int
    duplicates: int
    reordered: int
    rejected: int


# --- Pure conversion helpers --------------------------------------------------
def _convert_timestamp(value: Any, timestamp_format: str) -> datetime:
    if timestamp_format == "epoch_ms":
        seconds, millis = divmod(int(value), 1000)
        return datetime.fromtimestamp(seconds, tz=_UTC) + timedelta(milliseconds=millis)
    if timestamp_format == "epoch_us":
        seconds, micros = divmod(int(value), 1_000_000)
        return datetime.fromtimestamp(seconds, tz=_UTC) + timedelta(microseconds=micros)
    if timestamp_format == "iso8601":
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_UTC)
        return parsed.astimezone(_UTC)
    raise NormalizationError(f"unknown timestamp_format {timestamp_format!r}")


def _resolve_side(raw: dict[str, Any], profile: ExchangeProfile) -> str:
    side_key = profile.field_mapping["side_field"]
    if side_key not in raw:
        raise NormalizationError(f"missing raw side field {side_key!r}")
    value = raw[side_key]
    # Direct: value already a TradeSide string.
    if isinstance(value, str) and value in VALID_SIDES:
        return value
    # Boolean flag: resolve via the documented side_rule grammar.
    if isinstance(value, bool):
        rule = profile.field_mapping["side_rule"]
        m_true = _SIDE_TRUE_RE.search(rule)
        m_false = _SIDE_FALSE_RE.search(rule)
        if not (m_true and m_false):
            raise NormalizationError(f"unparseable side_rule {rule!r}")
        return (m_true.group(1) if value else m_false.group(1)).upper()
    raise NormalizationError(f"invalid side value {value!r}")


def normalize_raw(raw: dict[str, Any], profile: ExchangeProfile) -> NormalizedTrade:
    """Map one raw exchange event to a canonical record. Raises NormalizationError."""
    if not isinstance(raw, dict):
        raise NormalizationError("raw event must be a mapping")
    mapping = profile.field_mapping

    def field(name: str) -> Any:
        raw_key = mapping[name]
        if raw_key not in raw:
            raise NormalizationError(f"missing raw field {raw_key!r} (for {name})")
        return raw[raw_key]

    # trade_id: try primary field, then fallback (e.g. @aggTrade uses 'a', @trade uses 't').
    try:
        _tid_key = mapping["trade_id"]
        if _tid_key not in raw and "trade_id_fallback" in mapping:
            _fallback = mapping["trade_id_fallback"]
            if _fallback in raw:
                _tid_key = _fallback
        if _tid_key not in raw:
            raise NormalizationError(f"missing raw field {mapping['trade_id']!r} (for trade_id)")
        trade_id = int(raw[_tid_key])
        price = Decimal(str(field("price")))
        quantity = Decimal(str(field("quantity")))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise NormalizationError(f"unmappable numeric field: {exc}") from exc

    # A zero/non-finite trade is not an executable market trade. Letting it
    # through corrupts price extrema and can later make forward-return code
    # divide by a zero observation price. Reject it at the canonical boundary
    # before storage or any order-flow consumer sees it.
    if not price.is_finite() or price <= 0:
        raise NormalizationError("price must be finite and greater than zero")
    if not quantity.is_finite() or quantity <= 0:
        raise NormalizationError("quantity must be finite and greater than zero")

    return NormalizedTrade(
        event_time=_convert_timestamp(field("event_time"), profile.timestamp_format),
        trade_time=_convert_timestamp(field("trade_time"), profile.timestamp_format),
        trade_id=trade_id,
        symbol=str(field("symbol")),
        price=price,
        quantity=quantity,
        side=_resolve_side(raw, profile),
    )


# --- Deterministic normalizer -------------------------------------------------
class DataNormalizer:
    """Normalize, deduplicate, and reorder a stream of raw exchange events."""

    def __init__(
        self,
        profile: ExchangeProfile,
        dedup_window: int = 10000,
        reorder_tolerance_ms: int = 500,
    ) -> None:
        if dedup_window < 1:
            raise ValueError("dedup_window must be >= 1")
        if reorder_tolerance_ms < 0:
            raise ValueError("reorder_tolerance_ms must be >= 0")
        self.profile = profile
        self.dedup_window = dedup_window
        self.tolerance = timedelta(milliseconds=reorder_tolerance_ms)
        # dedup: sliding window of the last N accepted trade_ids
        self._recent_ids: list[int] = []
        self._recent_set: set[int] = set()
        # reorder buffer of (event_time, seq, trade), kept sorted
        self._buffer: list[tuple[datetime, int, NormalizedTrade]] = []
        self._seq = 0
        self._newest_seen: Optional[datetime] = None
        self._last_emitted: Optional[datetime] = None
        # counters — trade path (no silent loss)
        self.processed = 0
        self.duplicates = 0
        self.reordered = 0
        self.rejected = 0
        # counters — depth path (B-1)
        self.depth_processed = 0
        self.depth_rejected = 0
        self.depth_filtered = 0

    # -- dedup helpers --
    def _is_duplicate(self, trade_id: int) -> bool:
        return trade_id in self._recent_set

    def _register(self, trade_id: int) -> None:
        self._recent_ids.append(trade_id)
        self._recent_set.add(trade_id)
        if len(self._recent_ids) > self.dedup_window:
            evicted = self._recent_ids.pop(0)
            # only drop from the set if no later duplicate keeps it live
            if evicted not in self._recent_ids:
                self._recent_set.discard(evicted)

    # -- release (watermark flush) --
    def _release(self) -> list[NormalizedTrade]:
        if self._newest_seen is None:
            return []
        watermark = self._newest_seen - self.tolerance
        emitted: list[NormalizedTrade] = []
        while self._buffer and self._buffer[0][0] <= watermark:
            _, _, trade = self._buffer.pop(0)
            emitted.append(trade)
            self._last_emitted = trade.event_time
        return emitted

    def process(self, raw: dict[str, Any]) -> list[NormalizedTrade]:
        """Process one raw event; return the events released by this arrival."""
        try:
            trade = normalize_raw(raw, self.profile)
        except NormalizationError as exc:
            self.rejected += 1
            logger.warning("%s normalization rejected: %s", exc.code, exc.reason)
            return []

        if self._is_duplicate(trade.trade_id):
            self.duplicates += 1
            logger.warning("%s duplicate trade_id=%s discarded", ERROR_DUPLICATE_TRADE, trade.trade_id)
            return []

        if self._last_emitted is not None and trade.event_time < self._last_emitted:
            self.rejected += 1
            logger.warning(
                "%s out-of-order trade_id=%s (%s < last emitted %s) rejected",
                ERROR_OUT_OF_ORDER, trade.trade_id, trade.event_time, self._last_emitted,
            )
            return []

        if self._newest_seen is not None and trade.event_time < self._newest_seen:
            self.reordered += 1

        self._register(trade.trade_id)
        bisect.insort(self._buffer, (trade.event_time, self._seq, trade))
        self._seq += 1
        self._newest_seen = (
            trade.event_time if self._newest_seen is None
            else max(self._newest_seen, trade.event_time)
        )
        self.processed += 1
        return self._release()

    def flush(self) -> list[NormalizedTrade]:
        """Release all remaining buffered events in event_time order (end of stream)."""
        emitted = [trade for _, _, trade in self._buffer]
        if emitted:
            self._last_emitted = self._buffer[-1][0]
        self._buffer = []
        return emitted

    # -- depth path (B-1) -------------------------------------------------------
    # Trade-side methods (process / flush / dedup / reorder) are NOT changed.

    def process_depth(self, raw: dict[str, Any]) -> Optional[OrderBookUpdate]:
        """Normalize one raw depth event; return canonical update or None.

        Returns None and increments depth_filtered when the profile has no
        order_book_mapping (decision 5 — backward compatible). Returns None
        and increments depth_rejected on normalization failure.
        """
        if self.profile.order_book_mapping is None:
            self.depth_filtered += 1
            return None
        try:
            update = normalize_raw_depth(raw, self.profile)
        except NormalizationError as exc:
            self.depth_rejected += 1
            logger.warning("%s depth normalization rejected: %s", exc.code, exc.reason)
            return None
        self.depth_processed += 1
        return update

    def classify_raw(self, raw: dict[str, Any]) -> str:
        """Return "trade" | "depth" | "liquidation" based on the active exchange profile.

        "liquidation" when the raw event's "e" field is "forceOrder" (@forceOrder stream).
        "depth" when the profile has order_book_mapping AND the raw event's
        event_type_field matches a known depth event type. Otherwise "trade"
        (consumers treat unknown / unmappable events as trade for backward compat).
        """
        if raw.get("e") == "forceOrder":
            return "liquidation"
        ob = self.profile.order_book_mapping
        if ob is not None:
            etype = raw.get(ob["event_type_field"])
            if etype in (ob["event_type_snapshot"], ob["event_type_diff"]):
                return "depth"
        return "trade"


_LIQUIDATION_REQUIRED_FIELDS: frozenset[str] = frozenset({"s", "S", "p", "q", "T"})


def normalize_raw_liquidation(
    raw: dict[str, Any],
    profile: ExchangeProfile,
) -> LiquidationEvent:
    """Map one raw forceOrder event to a canonical LiquidationEvent.

    Raises NormalizationError on unmappable input.

    Binance forceOrder payload: {"e":"forceOrder","E":epoch_ms,"o":{...}}
    "o" object fields:
      s = symbol
      S = side of the liquidation order.
          SELL = the liquidated position was LONG (forced sell to close long).
          BUY  = the liquidated position was SHORT (forced buy to close short).
      p = price (string)
      q = quantity (string)
      T = trade time (epoch_ms)
    """
    if not isinstance(raw, dict):
        raise NormalizationError("forceOrder raw event must be a mapping")
    e_time_raw = raw.get("E")
    if e_time_raw is None:
        raise NormalizationError("forceOrder missing event_time field 'E'")
    o = raw.get("o")
    if not isinstance(o, dict):
        raise NormalizationError("forceOrder missing or invalid 'o' object")
    missing = _LIQUIDATION_REQUIRED_FIELDS - set(o)
    if missing:
        raise NormalizationError(f"forceOrder 'o' missing fields: {sorted(missing)}")
    try:
        event_time = _convert_timestamp(e_time_raw, profile.timestamp_format)
        price = Decimal(str(o["p"]))
        quantity = Decimal(str(o["q"]))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise NormalizationError(f"forceOrder unmappable numeric field: {exc}") from exc
    side = str(o["S"])
    if side not in VALID_SIDES:
        raise NormalizationError(f"forceOrder invalid side {side!r}")
    return LiquidationEvent(
        event_time=event_time,
        symbol=str(o["s"]),
        side=side,
        price=price,
        quantity=quantity,
    )


def normalize_raw_depth(
    raw: dict[str, Any],
    profile: ExchangeProfile,
) -> OrderBookUpdate:
    """Map one raw depth event to a canonical Order Book Update Record.

    Raises NormalizationError on unmappable input. The caller (process_depth)
    guards against a None order_book_mapping before calling here.
    """
    ob = profile.order_book_mapping
    if ob is None:
        raise NormalizationError("no order_book_mapping in profile")

    # Determine update_type from event type discriminator.
    raw_etype = raw.get(ob["event_type_field"])
    if raw_etype == ob["event_type_snapshot"]:
        update_type = "SNAPSHOT"
    elif raw_etype == ob["event_type_diff"]:
        update_type = "DIFF"
    else:
        raise NormalizationError(
            f"unknown depth event type {raw_etype!r} "
            f"(expected {ob['event_type_snapshot']!r} or {ob['event_type_diff']!r})"
        )

    # symbol
    sym_key = ob["symbol_field"]
    if sym_key not in raw:
        raise NormalizationError(f"missing depth symbol field {sym_key!r}")
    symbol = str(raw[sym_key])

    # event_time
    et_key = ob["event_time_field"]
    if et_key not in raw:
        raise NormalizationError(f"missing depth event_time field {et_key!r}")
    try:
        event_time = _convert_timestamp(raw[et_key], profile.timestamp_format)
    except (NormalizationError, Exception) as exc:
        raise NormalizationError(f"invalid depth event_time: {exc}") from exc

    # final_update_id (required for both SNAPSHOT and DIFF)
    fuid_key = ob["final_update_id_field"]
    if fuid_key not in raw:
        raise NormalizationError(f"missing final_update_id field {fuid_key!r}")
    try:
        final_update_id = int(raw[fuid_key])
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"invalid final_update_id: {exc}") from exc

    # first_update_id (required for DIFF, optional for SNAPSHOT)
    first_key = ob["first_update_id_field"]
    first_update_id: Optional[int] = None
    if update_type == "DIFF":
        if first_key not in raw:
            raise NormalizationError(
                f"DIFF missing first_update_id field {first_key!r}"
            )
        try:
            first_update_id = int(raw[first_key])
        except (TypeError, ValueError) as exc:
            raise NormalizationError(f"invalid first_update_id: {exc}") from exc
    elif first_key in raw and raw[first_key] is not None:
        try:
            first_update_id = int(raw[first_key])
        except (TypeError, ValueError):
            pass  # optional for SNAPSHOT — ignore invalid

    # bids and asks
    pi = ob["level_price_index"]
    qi = ob["level_quantity_index"]
    bids = _parse_levels(raw, ob["bids_field"], pi, qi, "bids")
    asks = _parse_levels(raw, ob["asks_field"], pi, qi, "asks")

    # previous_final_update_id (pu, Binance Futures @depth — optional field)
    pu_key = ob.get("previous_final_update_id_field")
    previous_final_update_id: Optional[int] = None
    if pu_key and pu_key in raw:
        try:
            previous_final_update_id = int(raw[pu_key])
        except (TypeError, ValueError):
            pass

    return OrderBookUpdate(
        event_time=event_time,
        symbol=symbol,
        update_type=update_type,
        first_update_id=first_update_id,
        final_update_id=final_update_id,
        bids=bids,
        asks=asks,
        previous_final_update_id=previous_final_update_id,
    )


def _parse_levels(
    raw: dict[str, Any],
    field: str,
    price_idx: int,
    qty_idx: int,
    side_name: str,
) -> tuple[BookLevel, ...]:
    if field not in raw:
        raise NormalizationError(f"missing {side_name} field {field!r}")
    raw_levels = raw[field]
    if not isinstance(raw_levels, list):
        raise NormalizationError(f"{side_name} field {field!r} must be a list")
    levels: list[BookLevel] = []
    for i, item in enumerate(raw_levels):
        try:
            price = Decimal(str(item[price_idx]))
            qty = Decimal(str(item[qty_idx]))
        except (IndexError, TypeError, ValueError) as exc:
            raise NormalizationError(
                f"{side_name}[{i}] cannot be parsed as BookLevel: {exc}"
            ) from exc
        levels.append(BookLevel(price=price, quantity=qty))
    return tuple(levels)


def run(
    raws: list[dict[str, Any]],
    profile: ExchangeProfile,
    dedup_window: int = 10000,
    reorder_tolerance_ms: int = 500,
) -> NrmRun:
    """Pure fold: normalize a full raw sequence and return all outputs in order."""
    normalizer = DataNormalizer(profile, dedup_window, reorder_tolerance_ms)
    emitted: list[NormalizedTrade] = []
    for raw in raws:
        emitted.extend(normalizer.process(raw))
    emitted.extend(normalizer.flush())
    # Rebuild rejection list is not tracked per-item here; counters suffice for
    # verification. Callers needing detail can drive DataNormalizer directly.
    return NrmRun(
        emitted=emitted,
        rejections=[],
        processed=normalizer.processed,
        duplicates=normalizer.duplicates,
        reordered=normalizer.reordered,
        rejected=normalizer.rejected,
    )
