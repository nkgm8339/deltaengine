"""Configuration loading and startup validation.

Schema source of truth: docs/40_Reference/YAMLReference_v3.1.md §2 (sample = the
canonical configuration; §3 = rules). Per-parameter types/ranges follow the
module Config Parameter tables:
    - docs/30_Modules/WebSocket_v3.2.md §6
    - docs/30_Modules/Database_v3.2.md §6
    - docs/30_Modules/DataNormalizer_v3.2.md §6
    - docs/30_Modules/CVD_v3.2.md §5 (market.bar_timeframe)
Timeframe values: docs/40_Reference/EnumDefinitions_v3.1.md §5.
Error codes: docs/40_Reference/ErrorCodes_v3.1.md (E1001 / E1002).
Log levels: docs/40_Reference/LoggingReference_v3.0.md.

Validation is strict (YAMLReference §3): unknown keys and invalid values cause a
ConfigError so the application fails at startup rather than running undefined.

Policy notes (implementation-level, documented here for auditability):
    - The YAMLReference §2 sample defines the canonical default for every key,
      so an omitted key falls back to its sample value — EXCEPT keys marked "—"
      in the WebSocket §6 table (`websocket.url`, `websocket.subscribe_streams`),
      which are REQUIRED (missing → E1002, per WebSocket §6).
    - Ranges stated in the module tables (e.g. "int ≥ 1") are enforced as given.
      Where a spec gives no explicit bound, a non-restrictive sanity bound is
      applied so the canonical sample stays valid; these are marked below.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

import yaml

# --- Error codes (ErrorCodes_v3.1 §4, E1xxx = Configuration) -------------------
ERROR_CONFIG_NOT_FOUND = "E1001"        # Configuration file not found
ERROR_CONFIG_VALIDATION = "E1002"       # Configuration validation failed

# --- Constrained value sets (spec-backed) -------------------------------------
LOG_LEVELS: frozenset[str] = frozenset(
    {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
)  # LoggingReference_v3.0
TIMEFRAMES: frozenset[str] = frozenset(
    {"1s", "1m", "5m", "10m", "15m", "1h", "4h", "1d"}
)  # EnumDefinitions_v3.1 §5


class ConfigError(Exception):
    """Base class for configuration failures. Carries an ErrorCodes_v3.1 code."""

    code: str = ERROR_CONFIG_VALIDATION

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


class ConfigFileNotFoundError(ConfigError):
    """Configuration file does not exist (E1001)."""

    code = ERROR_CONFIG_NOT_FOUND


class ConfigValidationError(ConfigError):
    """Configuration content is invalid (E1002). Aggregates all problems."""

    code = ERROR_CONFIG_VALIDATION

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("configuration validation failed: " + "; ".join(self.problems))


# --- Validator factories: each returns fn(value) -> Optional[error message] ----
Validator = Callable[[Any], Optional[str]]


def v_str(value: Any) -> Optional[str]:
    return None if isinstance(value, str) else "must be a string"


def v_nonempty_str(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return "must be a non-empty string"
    return None


def v_bool(value: Any) -> Optional[str]:
    return None if isinstance(value, bool) else "must be a boolean"


def v_int(lo: Optional[int] = None, hi: Optional[int] = None) -> Validator:
    def check(value: Any) -> Optional[str]:
        if not isinstance(value, int) or isinstance(value, bool):
            return "must be an integer"
        if lo is not None and value < lo:
            return f"must be >= {lo}"
        if hi is not None and value > hi:
            return f"must be <= {hi}"
        return None
    return check


def v_number(
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    gt: Optional[float] = None,
) -> Validator:
    def check(value: Any) -> Optional[str]:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "must be a number"
        if gt is not None and value <= gt:
            return f"must be > {gt}"
        if lo is not None and value < lo:
            return f"must be >= {lo}"
        if hi is not None and value > hi:
            return f"must be <= {hi}"
        return None
    return check

def v_positive_decimal_string(value: Any) -> Optional[str]:
    error = v_decimal_string()(value)
    if error:
        return error
    if Decimal(value) <= Decimal("0"):
        return "must be a finite Decimal string > 0"
    return None


def v_decimal_string(lo: Decimal = Decimal("0")) -> Validator:
    def check(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return "must be a Decimal string"
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            return "must be a valid Decimal string"
        if not parsed.is_finite() or parsed < lo:
            return f"must be a finite Decimal string >= {lo}"
        return None
    return check

def v_enum(allowed: frozenset[str]) -> Validator:
    def check(value: Any) -> Optional[str]:
        return (
            None
            if isinstance(value, str) and value in allowed
            else f"must be one of {sorted(allowed)}"
        )
    return check


def v_nullable(inner: Validator) -> Validator:
    def check(value: Any) -> Optional[str]:
        return None if value is None else inner(value)
    return check


def v_list_of(inner: Validator, nonempty: bool = False) -> Validator:
    def check(value: Any) -> Optional[str]:
        if not isinstance(value, list):
            return "must be a list"
        if nonempty and not value:
            return "must be a non-empty list"
        for idx, item in enumerate(value):
            err = inner(item)
            if err:
                return f"[{idx}] {err}"
        return None
    return check


def v_big_trades_horizons(value: Any) -> Optional[str]:
    error = v_list_of(v_int(lo=1, hi=600), nonempty=True)(value)
    if error:
        return error
    assert isinstance(value, list)
    if value != sorted(set(value)):
        return "must be strictly ascending with no duplicates"
    return None


def v_confluence(value: Any) -> Optional[str]:
    """webapp.confluence: nested mapping with score_threshold and strength_threshold."""
    if not isinstance(value, dict):
        return "must be a mapping"
    allowed = {"score_threshold", "strength_threshold"}
    for key in value:
        if key not in allowed:
            return f"unknown key '{key}'"
    if "score_threshold" in value:
        err = v_number(lo=0)(value["score_threshold"])
        if err:
            return f"score_threshold {err}"
    if "strength_threshold" in value:
        err = v_number(lo=0, hi=1)(value["strength_threshold"])
        if err:
            return f"strength_threshold {err}"
    return None


def v_weight(value: Any) -> Optional[str]:
    """signal.weight: required {cvd, footprint, imbalance}, optional {flow} -> number >= 0."""
    if not isinstance(value, dict):
        return "must be a mapping"
    required = {"cvd", "footprint", "imbalance"}
    optional = {"flow"}
    allowed = required | optional
    for key in value:
        if key not in allowed:
            return f"unknown key '{key}'"
    for key in required:
        if key not in value:
            return f"missing key '{key}'"
        err = v_number(lo=0)(value[key])
        if err:
            return f"{key} {err}"
    for key in optional:
        if key in value:
            err = v_number(lo=0)(value[key])
            if err:
                return f"{key} {err}"
    return None


# --- Schema -------------------------------------------------------------------
# Sentinel: key has no default and must be present.
class _Required:
    __slots__ = ()


REQUIRED = _Required()


class Field:
    """A single config key: its validator and default (or REQUIRED)."""

    __slots__ = ("validator", "default")

    def __init__(self, validator: Validator, default: Any) -> None:
        self.validator = validator
        self.default = default


# Section -> key -> Field. Defaults mirror YAMLReference_v3.1 §2 sample.
# Range bounds marked (impl) have no explicit spec bound; chosen to keep the
# canonical sample valid without silently accepting nonsense.
SCHEMA: dict[str, dict[str, Field]] = {
    "system": {
        "timezone": Field(v_nonempty_str, "UTC"),
        "log_level": Field(v_enum(LOG_LEVELS), "INFO"),
    },
    "market": {
        "symbol": Field(v_nonempty_str, "BTCUSDT"),
        "exchange": Field(v_nonempty_str, "BINANCE"),
        "bar_timeframe": Field(v_enum(TIMEFRAMES), "1m"),  # CVD_v3.2 §5 default 1m
        "tick_size": Field(v_positive_decimal_string, REQUIRED),
    },
    "websocket": {
        "url": Field(v_nonempty_str, REQUIRED),                   # WebSocket §6 "—"
        "reconnect": Field(v_bool, True),
        "reconnect_delay_sec": Field(v_int(lo=1), 5),
        "reconnect_max_retries": Field(v_int(lo=0), 0),
        "heartbeat_sec": Field(v_int(lo=1), 30),
        "connect_timeout_sec": Field(v_int(lo=1), 10),
        "subscribe_streams": Field(v_list_of(v_nonempty_str, nonempty=True), REQUIRED),
    },
    "normalizer": {
        "exchange_profile": Field(v_nonempty_str, "binance"),
        "dedup_window": Field(v_int(lo=1), 10000),
        "reorder_tolerance_ms": Field(v_int(lo=0), 500),
        "live_reorder_tolerance_ms": Field(v_int(lo=0), 0),
    },
    "queue": {
        "default_depth": Field(v_int(lo=1), 10000),
        "overflow_policy": Field(v_nonempty_str, "drop_oldest_log"),  # (impl) no enum in spec
        "pipeline_chunk_max_events": Field(v_int(lo=1), 32),
        "pipeline_chunk_max_wall_ms": Field(v_int(lo=1), 50),
    },
    "database": {
        "parquet_path": Field(v_nonempty_str, "data/parquet"),
        "duckdb_path": Field(v_nonempty_str, "data/duckdb/orderflow.duckdb"),
        "batch_size": Field(v_int(lo=1), 1000),
        "flush_interval_sec": Field(v_int(lo=1), 5),
    },
    "signal": {
        "enabled": Field(v_bool, False),
        "weight": Field(v_weight, {"cvd": 1.0, "footprint": 1.0, "imbalance": 1.0}),
        "confidence_threshold": Field(v_number(lo=0.0, hi=1.0), 0.6),
        "cvd_slope_ref": Field(v_nullable(v_number()), None),      # reserved (TBD)
        "stack_ref": Field(v_int(lo=1), 3),
        "absorption_veto_threshold": Field(v_number(lo=0.0, hi=1.0), 0.5),
        "evaluation_window": Field(v_nonempty_str, "1 bar"),
    },
    "imbalance": {
        "ratio_threshold": Field(v_number(gt=0), 3.0),
        "min_volume": Field(v_nullable(v_number(lo=0)), None),
        "ratio_cap": Field(v_number(gt=0), 10.0),
        "stack_count": Field(v_int(lo=1), 3),
    },
    "absorption": {
        "window_sec": Field(v_int(lo=1), 10),
        "price_stall_ticks": Field(v_int(lo=0), 1),
        "volume_multiplier": Field(v_number(gt=0), 2.0),
        "volume_ref_bars": Field(v_int(lo=1), 20),
    },
    "mt5": {
        "enabled": Field(v_bool, False),
        "bind_address": Field(v_nonempty_str, "127.0.0.1"),
        "port": Field(v_int(lo=1, hi=65535), 5555),
        "max_clients": Field(v_int(lo=1), 3),
        "heartbeat_interval_sec": Field(v_int(lo=1), 5),
        "max_buffer_messages": Field(v_int(lo=1), 1000),
    },
    "ai": {
        "enabled": Field(v_bool, False),
        "confidence_threshold": Field(v_number(lo=0.0, hi=1.0), 0.70),
    },
    "replay": {
        "enabled": Field(v_bool, False),
        "data_path": Field(v_nullable(v_nonempty_str), None),
        "speed": Field(v_number(lo=0), 1.0),
    },
    "calibration": {
        "cvd_slope_ref": Field(v_nullable(v_number()), None),      # reserved (TBD)
    },
    "flow_detector": {
        "large_trade_min_qty": Field(v_nonempty_str, "5.0"),
        "sweep_window_ms": Field(v_int(lo=1), 500),
        "sweep_min_qty": Field(v_nonempty_str, "8.0"),
        "sweep_min_levels": Field(v_int(lo=1), 3),
        "sweep_cooldown_ms": Field(v_int(lo=0), 2000),
        "exhaustion_ratio": Field(v_nonempty_str, "0.25"),
        "ua_min_vol": Field(v_nonempty_str, "2.0"),
        "tape_window_ms": Field(v_int(lo=1), 5000),
        "tape_emit_interval_ms": Field(v_int(lo=1), 1000),
        "tape_pause_threshold_ms": Field(v_int(lo=0), 3000),
    },
    "webapp": {
        "enabled": Field(v_bool, True),
        "host": Field(v_nonempty_str, "0.0.0.0"),
        "port": Field(v_int(lo=1, hi=65535), 8080),
        "depth_levels": Field(v_int(lo=1), 15),
        "live_dom_depth_levels": Field(v_int(lo=1), 50),
        "book_update_interval_ms": Field(v_int(lo=10), 100),
        "book_stale_after_ms": Field(v_int(lo=100), 2000),
        "market_heartbeat_interval_ms": Field(v_int(lo=1), 1000),
        "market_heartbeat_timeout_ms": Field(v_int(lo=1), 3000),
        "tape_batch_interval_ms": Field(v_int(lo=10), 100),
        "tape_max_trades_per_message": Field(v_int(lo=1), 250),
        "tape_pending_capacity": Field(v_int(lo=1), 10000),
        "flow_window_sec": Field(v_int(lo=1), 60),
        "alert_threshold": Field(v_number(lo=0, hi=1), 0.85),
        "confluence": Field(v_confluence, {"score_threshold": 40, "strength_threshold": 0.5}),
        "oi_poll_interval_sec": Field(v_int(lo=1), 10),
        "tick_push_interval_ms": Field(v_int(lo=10), 50),
        "bar_update_interval_sec": Field(v_number(gt=0), 0.2),
    },
    "divergence": {
        "equal_pivot_policy": Field(v_enum(frozenset({"first"})), "first"),
        "min_price_move": Field(v_decimal_string(), "0"),
        "min_bar_distance": Field(v_int(lo=0), 0),
    },
    "flow_response": {
        # Observational pressure/response windows. These are intentionally not
        # confidence scores or BUY/SELL signals.
        "enabled": Field(v_bool, True),
        "windows_sec": Field(
            v_list_of(v_int(lo=1), nonempty=True),
            [30, 60, 180, 300, 900, 1800],
        ),
        "baseline_window_sec": Field(v_int(lo=1), 1800),
        "pressure_threshold": Field(v_decimal_string(), "0.20"),
        "persistence_threshold": Field(v_decimal_string(), "0.60"),
        "stall_bps": Field(v_decimal_string(), "1.0"),
        "effective_bps": Field(v_decimal_string(), "2.0"),
        "opposite_bps": Field(v_decimal_string(), "1.0"),
        "min_trades": Field(v_int(lo=1), 20),
        "outcome_horizons_sec": Field(
            v_list_of(v_int(lo=1), nonempty=True),
            [60, 180, 300, 600],
        ),
    },
    "big_trades": {
        "enabled": Field(v_bool, False),
        "input_mode": Field(v_enum(frozenset({"AGGREGATE_TRADES"})), "AGGREGATE_TRADES"),
        "filter_mode": Field(v_enum(frozenset({"MANUAL", "AUTOMATIC"})), "MANUAL"),
        "manual_min_quantity": Field(v_decimal_string(), "5.000"),
        "manual_max_quantity": Field(v_decimal_string(), "0"),
        "automatic_intensity": Field(
            v_enum(frozenset({"LOW", "MEDIUM", "STRONG"})), "MEDIUM"
        ),
        "side_filter": Field(v_enum(frozenset({"BOTH", "BUY", "SELL"})), "BOTH"),
        "marker_price_mode": Field(
            v_enum(frozenset({"START_PRICE", "LAST_PRICE", "VWAP_PRICE"})),
            "LAST_PRICE",
        ),
        "calibration_schedule": Field(
            v_enum(frozenset({"MANUAL", "WEEKLY", "MONTHLY"})), "MANUAL"
        ),
        "calibration_activation_policy": Field(
            v_enum(frozenset({"SCHEDULED_SESSION_BOUNDARY", "MANUAL_ONLY"})),
            "SCHEDULED_SESSION_BOUNDARY",
        ),
        "replay_calibration_mode": Field(
            v_enum(frozenset({"HISTORICAL_ACTIVATION", "FIXED_RESEARCH"})),
            "HISTORICAL_ACTIVATION",
        ),
        "quantity_step": Field(v_positive_decimal_string, "0.001"),
        "reaction_zones_enabled": Field(v_bool, True),
        "reaction_zone_match_tolerance_ticks": Field(v_int(lo=1), 1),
        "reaction_observation_mode": Field(
            v_enum(frozenset({"UTC_SESSION"})), "UTC_SESSION"
        ),
        "result_horizons_seconds": Field(
            v_big_trades_horizons,
            [1, 5, 15, 30, 60, 180, 300, 600],
        ),
        "result_snapshot_max_staleness_ms": Field(v_int(lo=1), 1000),
        "active_zone_capacity": Field(v_int(lo=1), 5000),
        "recent_event_capacity": Field(v_int(lo=1), 5000),
        "recent_interaction_capacity": Field(v_int(lo=1), 20000),
        "history_api_max_limit": Field(v_int(lo=1), 5000),
        "batch_interval_ms": Field(v_int(lo=1), 100),
        "batch_max_records": Field(v_int(lo=1), 200),
        "batch_pending_capacity": Field(v_int(lo=1), 10000),
        "max_fills_per_cluster": Field(v_int(lo=1), 10000),
    },
    "monitor": {
        "enabled": Field(v_bool, True),
        "interval_sec": Field(v_int(lo=1), 5),
        "log_dir": Field(v_nonempty_str, "data/monitor"),
        "bar_missing_tolerance_sec": Field(v_int(lo=1), 90),
        "latency_yellow_ms": Field(v_int(lo=1), 2000),
        "latency_red_ms": Field(v_int(lo=1), 10000),
        "memory_yellow_mb": Field(v_int(lo=1), 900),
        "memory_red_mb": Field(v_int(lo=1), 1500),
        "window_min": Field(v_int(lo=1), 15),
        "reconnect_yellow": Field(v_int(lo=1), 1),
        "reconnect_red": Field(v_int(lo=1), 3),
        "gap_yellow": Field(v_int(lo=1), 1),
        "gap_red": Field(v_int(lo=1), 5),
        "exception_yellow": Field(v_int(lo=1), 1),
        "exception_red": Field(v_int(lo=1), 3),
    },
}


# --- Immutable config view ----------------------------------------------------
class ConfigNode(Mapping):
    """Read-only attribute/item access over a validated config (nested)."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        object.__setattr__(
            self,
            "_data",
            {
                key: (ConfigNode(val) if isinstance(val, dict) else val)
                for key, val in data.items()
            },
        )

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ConfigNode({self._data!r})"


# --- Validation ---------------------------------------------------------------
def _validate(raw: Any) -> ConfigNode:
    if not isinstance(raw, dict):
        raise ConfigValidationError(["top-level document must be a mapping"])

    problems: list[str] = []
    result: dict[str, Any] = {}

    # Reject unknown top-level sections (YAMLReference §3).
    for section in raw:
        if section not in SCHEMA:
            problems.append(f"unknown top-level section: '{section}'")

    for section, fields in SCHEMA.items():
        body = raw.get(section, {})
        if section in raw and not isinstance(body, dict):
            problems.append(f"section '{section}' must be a mapping")
            continue
        body = body if isinstance(body, dict) else {}

        # Reject unknown keys within the section.
        for key in body:
            if key not in fields:
                problems.append(f"unknown key: '{section}.{key}'")

        section_result: dict[str, Any] = {}
        for key, field in fields.items():
            if key in body:
                err = field.validator(body[key])
                if err:
                    problems.append(f"{section}.{key} {err}")
                else:
                    section_result[key] = body[key]
            elif field.default is REQUIRED:
                problems.append(f"missing required key: '{section}.{key}'")
            else:
                section_result[key] = field.default
        result[section] = section_result

    webapp = result.get("webapp", {})
    heartbeat_interval = webapp.get("market_heartbeat_interval_ms")
    heartbeat_timeout = webapp.get("market_heartbeat_timeout_ms")
    if (
        isinstance(heartbeat_interval, int)
        and not isinstance(heartbeat_interval, bool)
        and isinstance(heartbeat_timeout, int)
        and not isinstance(heartbeat_timeout, bool)
        and heartbeat_timeout < heartbeat_interval * 3
    ):
        problems.append(
            "webapp.market_heartbeat_timeout_ms must be >= "
            "webapp.market_heartbeat_interval_ms * 3"
        )

    big_trades = result.get("big_trades", {})
    minimum = big_trades.get("manual_min_quantity")
    maximum = big_trades.get("manual_max_quantity")
    if isinstance(minimum, str) and isinstance(maximum, str):
        try:
            parsed_minimum = Decimal(minimum)
            parsed_maximum = Decimal(maximum)
        except InvalidOperation:
            pass
        else:
            if (
                parsed_minimum.is_finite()
                and parsed_maximum.is_finite()
                and parsed_maximum > 0
                and parsed_maximum < parsed_minimum
            ):
                problems.append(
                    "big_trades.manual_max_quantity must be zero or >= "
                    "big_trades.manual_min_quantity"
                )

    if problems:
        raise ConfigValidationError(problems)

    return ConfigNode(result)


def load_config(path: str | Path) -> ConfigNode:
    """Load and validate a YAML configuration file.

    Raises:
        ConfigFileNotFoundError: file does not exist (E1001).
        ConfigValidationError: unparseable or invalid (E1002).
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigFileNotFoundError(f"configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigValidationError([f"YAML parse error: {exc}"]) from exc

    if raw is None:
        raise ConfigValidationError(["configuration file is empty"])

    return _validate(raw)
