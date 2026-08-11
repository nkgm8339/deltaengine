"""Authoritative DuckDB, Arrow, and row contracts for Big Trades V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping

import pyarrow as pa

from src.orderflow.big_trades.activation import ActivationArtifact
from src.orderflow.big_trades.artifacts import CalibrationArtifact, SessionStatsArtifact
from src.orderflow.big_trades.constants import (
    AutomaticIntensity,
    ClusterCloseReason,
    FilterMode,
    InteractionType,
    MarkerPriceMode,
    PriceRelation,
    SideFilter,
    SnapshotValidity,
    ZoneLifecycle,
)
from src.orderflow.big_trades.ids import canonical_json, content_hash, sha256_hex
from src.orderflow.big_trades.models import (
    BigTradeEvent,
    BigTradeFill,
    ReactionZone,
    ResultSnapshot,
    UserAssessment,
    ZoneCandleObservation,
    ZoneEventLink,
    ZoneInteraction,
    ZoneStateCheckpoint,
)
from src.orderflow.big_trades.settings import SettingsRequest, SettingsVersion
from src.orderflow.big_trades.time_buckets import (
    candle_id as candle_identifier,
    candle_start,
    require_aware_utc,
)


BIG_TRADES_SCHEMA_VERSION = 2

BIG_TRADES_SCHEMA_META_DDL = """
CREATE TABLE IF NOT EXISTS big_trades_schema_meta (
  component VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  installed_at_utc TIMESTAMP NOT NULL
)
"""

BIG_TRADE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_events (
  event_id VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  side VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  first_trade_id BIGINT NOT NULL,
  last_trade_id BIGINT NOT NULL,
  first_time TIMESTAMP NOT NULL,
  last_time TIMESTAMP NOT NULL,
  marker_time TIMESTAMP NOT NULL,
  first_price DECIMAL(20,8) NOT NULL,
  last_price DECIMAL(20,8) NOT NULL,
  marker_price DECIMAL(20,8) NOT NULL,
  low_price DECIMAL(20,8) NOT NULL,
  high_price DECIMAL(20,8) NOT NULL,
  vwap DECIMAL(38,16) NOT NULL,
  aggregate_quantity DECIMAL(38,16) NOT NULL,
  aggregate_notional DECIMAL(38,8) NOT NULL,
  fill_count INTEGER NOT NULL,
  price_level_count INTEGER NOT NULL,
  duration_ms BIGINT NOT NULL,
  close_reason VARCHAR NOT NULL,
  filter_mode VARCHAR NOT NULL,
  intensity VARCHAR,
  threshold_used DECIMAL(38,16) NOT NULL,
  max_threshold_used DECIMAL(38,16) NOT NULL,
  side_filter VARCHAR NOT NULL,
  marker_price_mode VARCHAR NOT NULL,
  settings_id VARCHAR NOT NULL,
  calibration_id VARCHAR,
  activation_id VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  candle_id TIMESTAMP NOT NULL,
  content_hash VARCHAR NOT NULL
)
"""

BIG_TRADE_EVENT_FILLS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_event_fills (
  event_id VARCHAR NOT NULL,
  fill_ordinal INTEGER NOT NULL,
  trade_id BIGINT NOT NULL,
  event_time TIMESTAMP NOT NULL,
  price DECIMAL(20,8) NOT NULL,
  quantity DECIMAL(20,8) NOT NULL,
  side VARCHAR NOT NULL,
  PRIMARY KEY(event_id, fill_ordinal)
)
"""

BIG_TRADE_REACTION_ZONES_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_reaction_zones (
  zone_id VARCHAR PRIMARY KEY,
  zone_schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  origin_event_id VARCHAR UNIQUE NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  origin_side VARCHAR NOT NULL,
  zone_low DECIMAL(20,8) NOT NULL,
  zone_high DECIMAL(20,8) NOT NULL,
  zone_anchor DECIMAL(38,16) NOT NULL,
  zone_visual_start TIMESTAMP NOT NULL,
  zone_source_start TIMESTAMP NOT NULL,
  session_id VARCHAR NOT NULL,
  settings_id VARCHAR NOT NULL,
  calibration_id VARCHAR,
  activation_id VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL
)
"""

BIG_TRADE_ZONE_INTERACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_zone_interactions (
  interaction_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  interaction_type VARCHAR NOT NULL,
  source_event_time TIMESTAMP NOT NULL,
  source_trade_id BIGINT,
  source_candle_id TIMESTAMP,
  price DECIMAL(20,8),
  previous_relation VARCHAR,
  current_relation VARCHAR,
  direction VARCHAR,
  ordinal BIGINT NOT NULL,
  gap_epoch_id VARCHAR,
  content_hash VARCHAR NOT NULL
)
"""

BIG_TRADE_ZONE_EVENT_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_zone_event_links (
  link_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  origin_event_id VARCHAR NOT NULL,
  linked_event_id VARCHAR NOT NULL,
  linked_side VARCHAR NOT NULL,
  linked_quantity DECIMAL(38,16) NOT NULL,
  linked_low DECIMAL(20,8) NOT NULL,
  linked_high DECIMAL(20,8) NOT NULL,
  linked_time TIMESTAMP NOT NULL,
  interval_gap_ticks DECIMAL(38,16) NOT NULL,
  same_as_origin_side BOOLEAN NOT NULL,
  ordinal_for_zone BIGINT NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, linked_event_id)
)
"""

BIG_TRADE_RESULT_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_result_snapshots (
  snapshot_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  horizon_seconds INTEGER NOT NULL,
  target_time TIMESTAMP NOT NULL,
  snapshot_trade_id BIGINT,
  snapshot_trade_time TIMESTAMP,
  source_age_ms BIGINT,
  snapshot_price DECIMAL(20,8),
  relation VARCHAR,
  return_last_bps DECIMAL(38,16),
  return_vwap_bps DECIMAL(38,16),
  origin_side_signed_return_bps DECIMAL(38,16),
  max_above_ticks DECIMAL(38,16),
  max_below_ticks DECIMAL(38,16),
  touch_count BIGINT NOT NULL,
  cross_count BIGINT NOT NULL,
  linked_event_count BIGINT NOT NULL,
  inside_buy_quantity DECIMAL(38,16) NOT NULL,
  inside_sell_quantity DECIMAL(38,16) NOT NULL,
  validity VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, horizon_seconds)
)
"""

BIG_TRADE_ZONE_CANDLES_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_zone_candle_observations (
  candle_observation_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  candle_id TIMESTAMP NOT NULL,
  open_price DECIMAL(20,8) NOT NULL,
  high_price DECIMAL(20,8) NOT NULL,
  low_price DECIMAL(20,8) NOT NULL,
  close_price DECIMAL(20,8) NOT NULL,
  open_relation VARCHAR NOT NULL,
  close_relation VARCHAR NOT NULL,
  high_above_ticks DECIMAL(38,16) NOT NULL,
  low_below_ticks DECIMAL(38,16) NOT NULL,
  body_overlaps_zone BOOLEAN NOT NULL,
  wick_overlaps_zone BOOLEAN NOT NULL,
  closed_above BOOLEAN NOT NULL,
  closed_below BOOLEAN NOT NULL,
  upper_wick_return BOOLEAN NOT NULL,
  lower_wick_return BOOLEAN NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, candle_id)
)
"""

BIG_TRADE_ZONE_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_zone_state_checkpoints (
  checkpoint_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  source_bucket_time TIMESTAMP NOT NULL,
  current_relation VARCHAR NOT NULL,
  first_exit_direction VARCHAR,
  first_exit_time TIMESTAMP,
  touch_count BIGINT NOT NULL,
  cross_count BIGINT NOT NULL,
  inside_buy_quantity DECIMAL(38,16) NOT NULL,
  inside_sell_quantity DECIMAL(38,16) NOT NULL,
  linked_event_count BIGINT NOT NULL,
  gap_epoch_id VARCHAR,
  content_hash VARCHAR NOT NULL,
  UNIQUE(zone_id, source_bucket_time)
)
"""

BIG_TRADE_USER_ASSESSMENTS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_user_assessments (
  assessment_id VARCHAR PRIMARY KEY,
  zone_id VARCHAR NOT NULL,
  assessment VARCHAR NOT NULL,
  assessed_at_utc TIMESTAMP NOT NULL,
  assessed_against_source_time TIMESTAMP NOT NULL,
  user_note VARCHAR,
  supersedes_assessment_id VARCHAR,
  content_hash VARCHAR NOT NULL
)
"""

BIG_TRADE_SESSION_STATS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_session_stats (
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  session_start TIMESTAMP NOT NULL,
  session_end TIMESTAMP NOT NULL,
  completion_status VARCHAR NOT NULL,
  completion_trigger VARCHAR NOT NULL,
  confirmed_by_session_id VARCHAR NOT NULL,
  confirmed_by_event_time TIMESTAMP NOT NULL,
  confirmed_by_trade_id BIGINT NOT NULL,
  cluster_count BIGINT NOT NULL,
  rank_2_quantity DECIMAL(38,16),
  rank_9_quantity DECIMAL(38,16),
  rank_20_quantity DECIMAL(38,16),
  top_quantities_json VARCHAR NOT NULL,
  valid_1m_bars INTEGER NOT NULL,
  invalid_1m_bars INTEGER NOT NULL,
  invalid_trades BIGINT NOT NULL,
  source_gap_count BIGINT NOT NULL,
  session_ntr_median DECIMAL(38,24),
  source_first_time TIMESTAMP NOT NULL,
  source_last_time TIMESTAMP NOT NULL,
  content_hash VARCHAR NOT NULL,
  PRIMARY KEY(logic_version, symbol, venue, input_mode, session_id)
)
"""

BIG_TRADE_CALIBRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_calibrations (
  calibration_id VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  session_template VARCHAR NOT NULL,
  quantity_unit VARCHAR NOT NULL,
  quantity_step DECIMAL(38,16) NOT NULL,
  history_start_session VARCHAR NOT NULL,
  history_end_session VARCHAR NOT NULL,
  valid_sessions_low INTEGER NOT NULL,
  valid_sessions_medium INTEGER NOT NULL,
  valid_sessions_strong INTEGER NOT NULL,
  base_low DECIMAL(38,16) NOT NULL,
  base_medium DECIMAL(38,16) NOT NULL,
  base_strong DECIMAL(38,16) NOT NULL,
  baseline_volatility DECIMAL(38,24),
  recent_volatility DECIMAL(38,24),
  volatility_factor DECIMAL(38,16) NOT NULL,
  volatility_status VARCHAR NOT NULL,
  auto_low DECIMAL(38,16) NOT NULL,
  auto_medium DECIMAL(38,16) NOT NULL,
  auto_strong DECIMAL(38,16) NOT NULL,
  aggregation_window_ms INTEGER NOT NULL,
  aggregation_candle_timeframe VARCHAR NOT NULL,
  target_events_json VARCHAR NOT NULL,
  source_manifest_sha256 VARCHAR NOT NULL,
  created_at_utc TIMESTAMP NOT NULL,
  content_sha256 VARCHAR NOT NULL
)
"""

BIG_TRADE_SETTINGS_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_settings_history (
  request_id VARCHAR PRIMARY KEY,
  settings_id VARCHAR NOT NULL,
  requested_at_utc TIMESTAMP NOT NULL,
  previous_settings_id VARCHAR,
  request_source VARCHAR NOT NULL,
  request_status VARCHAR NOT NULL,
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  filter_mode VARCHAR NOT NULL,
  manual_min_quantity DECIMAL(38,16) NOT NULL,
  manual_max_quantity DECIMAL(38,16) NOT NULL,
  automatic_intensity VARCHAR NOT NULL,
  side_filter VARCHAR NOT NULL,
  marker_price_mode VARCHAR NOT NULL,
  calibration_id VARCHAR,
  content_hash VARCHAR NOT NULL
)
"""

BIG_TRADE_ACTIVATION_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS big_trade_activation_history (
  activation_id VARCHAR PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  logic_version VARCHAR NOT NULL,
  symbol VARCHAR NOT NULL,
  venue VARCHAR NOT NULL,
  input_mode VARCHAR NOT NULL,
  effective_session_id VARCHAR NOT NULL,
  effective_from_event_time TIMESTAMP NOT NULL,
  effective_from_trade_id BIGINT NOT NULL,
  settings_id VARCHAR NOT NULL,
  calibration_id VARCHAR,
  activation_reason VARCHAR NOT NULL,
  activation_policy VARCHAR NOT NULL,
  requested_at_utc TIMESTAMP NOT NULL,
  content_hash VARCHAR NOT NULL,
  UNIQUE(logic_version, symbol, venue, input_mode, effective_from_event_time, effective_from_trade_id)
)
"""

BIG_TRADES_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_bt_events_session ON big_trade_events(symbol, venue, session_id, last_time)",
    "CREATE INDEX IF NOT EXISTS idx_bt_zones_session ON big_trade_reaction_zones(symbol, venue, session_id, zone_source_start)",
    "CREATE INDEX IF NOT EXISTS idx_bt_interactions_zone_time ON big_trade_zone_interactions(zone_id, source_event_time)",
    "CREATE INDEX IF NOT EXISTS idx_bt_links_zone_time ON big_trade_zone_event_links(zone_id, linked_time)",
    "CREATE INDEX IF NOT EXISTS idx_bt_snapshots_zone_target ON big_trade_result_snapshots(zone_id, target_time)",
    "CREATE INDEX IF NOT EXISTS idx_bt_candles_zone_time ON big_trade_zone_candle_observations(zone_id, candle_id)",
    "CREATE INDEX IF NOT EXISTS idx_bt_activation_effective ON big_trade_activation_history(symbol, venue, input_mode, effective_from_event_time, effective_from_trade_id)",
)

BIG_TRADES_TABLE_DDLS = (
    BIG_TRADES_SCHEMA_META_DDL,
    BIG_TRADE_EVENTS_DDL,
    BIG_TRADE_EVENT_FILLS_DDL,
    BIG_TRADE_REACTION_ZONES_DDL,
    BIG_TRADE_ZONE_INTERACTIONS_DDL,
    BIG_TRADE_ZONE_EVENT_LINKS_DDL,
    BIG_TRADE_RESULT_SNAPSHOTS_DDL,
    BIG_TRADE_ZONE_CANDLES_DDL,
    BIG_TRADE_ZONE_CHECKPOINTS_DDL,
    BIG_TRADE_USER_ASSESSMENTS_DDL,
    BIG_TRADE_SESSION_STATS_DDL,
    BIG_TRADE_CALIBRATIONS_DDL,
    BIG_TRADE_SETTINGS_HISTORY_DDL,
    BIG_TRADE_ACTIVATION_HISTORY_DDL,
)


UTC_TS = pa.timestamp("us", tz="UTC")
DECIMAL_20_8 = pa.decimal128(20, 8)
DECIMAL_38_8 = pa.decimal128(38, 8)
DECIMAL_38_16 = pa.decimal128(38, 16)
DECIMAL_38_24 = pa.decimal128(38, 24)


def _schema(fields: Iterable[tuple[str, pa.DataType, bool]]) -> pa.Schema:
    return pa.schema([pa.field(name, type_, nullable=nullable) for name, type_, nullable in fields])


BIG_TRADE_EVENTS_SCHEMA = _schema(
    (
        ("event_id", pa.string(), False), ("schema_version", pa.int32(), False),
        ("logic_version", pa.string(), False), ("symbol", pa.string(), False),
        ("venue", pa.string(), False), ("side", pa.string(), False),
        ("input_mode", pa.string(), False), ("first_trade_id", pa.int64(), False),
        ("last_trade_id", pa.int64(), False), ("first_time", UTC_TS, False),
        ("last_time", UTC_TS, False), ("marker_time", UTC_TS, False),
        ("first_price", DECIMAL_20_8, False), ("last_price", DECIMAL_20_8, False),
        ("marker_price", DECIMAL_20_8, False), ("low_price", DECIMAL_20_8, False),
        ("high_price", DECIMAL_20_8, False), ("vwap", DECIMAL_38_16, False),
        ("aggregate_quantity", DECIMAL_38_16, False),
        ("aggregate_notional", DECIMAL_38_8, False), ("fill_count", pa.int32(), False),
        ("price_level_count", pa.int32(), False), ("duration_ms", pa.int64(), False),
        ("close_reason", pa.string(), False), ("filter_mode", pa.string(), False),
        ("intensity", pa.string(), True), ("threshold_used", DECIMAL_38_16, False),
        ("max_threshold_used", DECIMAL_38_16, False), ("side_filter", pa.string(), False),
        ("marker_price_mode", pa.string(), False), ("settings_id", pa.string(), False),
        ("calibration_id", pa.string(), True), ("activation_id", pa.string(), False),
        ("session_id", pa.string(), False), ("candle_id", UTC_TS, False),
        ("content_hash", pa.string(), False),
    )
)

BIG_TRADE_EVENT_FILLS_SCHEMA = _schema(
    (("event_id", pa.string(), False), ("fill_ordinal", pa.int32(), False),
     ("trade_id", pa.int64(), False), ("event_time", UTC_TS, False),
     ("price", DECIMAL_20_8, False), ("quantity", DECIMAL_20_8, False),
     ("side", pa.string(), False))
)

BIG_TRADE_REACTION_ZONES_SCHEMA = _schema(
    (("zone_id", pa.string(), False), ("zone_schema_version", pa.int32(), False),
     ("logic_version", pa.string(), False), ("origin_event_id", pa.string(), False),
     ("symbol", pa.string(), False), ("venue", pa.string(), False),
     ("origin_side", pa.string(), False), ("zone_low", DECIMAL_20_8, False),
     ("zone_high", DECIMAL_20_8, False), ("zone_anchor", DECIMAL_38_16, False),
     ("zone_visual_start", UTC_TS, False), ("zone_source_start", UTC_TS, False),
     ("session_id", pa.string(), False), ("settings_id", pa.string(), False),
     ("calibration_id", pa.string(), True), ("activation_id", pa.string(), False),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_ZONE_INTERACTIONS_SCHEMA = _schema(
    (("interaction_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("interaction_type", pa.string(), False), ("source_event_time", UTC_TS, False),
     ("source_trade_id", pa.int64(), True), ("source_candle_id", UTC_TS, True),
     ("price", DECIMAL_20_8, True), ("previous_relation", pa.string(), True),
     ("current_relation", pa.string(), True), ("direction", pa.string(), True),
     ("ordinal", pa.int64(), False), ("gap_epoch_id", pa.string(), True),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_ZONE_EVENT_LINKS_SCHEMA = _schema(
    (("link_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("origin_event_id", pa.string(), False), ("linked_event_id", pa.string(), False),
     ("linked_side", pa.string(), False), ("linked_quantity", DECIMAL_38_16, False),
     ("linked_low", DECIMAL_20_8, False), ("linked_high", DECIMAL_20_8, False),
     ("linked_time", UTC_TS, False), ("interval_gap_ticks", DECIMAL_38_16, False),
     ("same_as_origin_side", pa.bool_(), False), ("ordinal_for_zone", pa.int64(), False),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_RESULT_SNAPSHOTS_SCHEMA = _schema(
    (("snapshot_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("horizon_seconds", pa.int32(), False), ("target_time", UTC_TS, False),
     ("snapshot_trade_id", pa.int64(), True), ("snapshot_trade_time", UTC_TS, True),
     ("source_age_ms", pa.int64(), True), ("snapshot_price", DECIMAL_20_8, True),
     ("relation", pa.string(), True), ("return_last_bps", DECIMAL_38_16, True),
     ("return_vwap_bps", DECIMAL_38_16, True),
     ("origin_side_signed_return_bps", DECIMAL_38_16, True),
     ("max_above_ticks", DECIMAL_38_16, False), ("max_below_ticks", DECIMAL_38_16, False),
     ("touch_count", pa.int64(), False), ("cross_count", pa.int64(), False),
     ("linked_event_count", pa.int64(), False),
     ("inside_buy_quantity", DECIMAL_38_16, False),
     ("inside_sell_quantity", DECIMAL_38_16, False),
     ("validity", pa.string(), False), ("content_hash", pa.string(), False))
)

BIG_TRADE_ZONE_CANDLES_SCHEMA = _schema(
    (("candle_observation_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("candle_id", UTC_TS, False), ("open_price", DECIMAL_20_8, False),
     ("high_price", DECIMAL_20_8, False), ("low_price", DECIMAL_20_8, False),
     ("close_price", DECIMAL_20_8, False), ("open_relation", pa.string(), False),
     ("close_relation", pa.string(), False), ("high_above_ticks", DECIMAL_38_16, False),
     ("low_below_ticks", DECIMAL_38_16, False), ("body_overlaps_zone", pa.bool_(), False),
     ("wick_overlaps_zone", pa.bool_(), False), ("closed_above", pa.bool_(), False),
     ("closed_below", pa.bool_(), False), ("upper_wick_return", pa.bool_(), False),
     ("lower_wick_return", pa.bool_(), False), ("content_hash", pa.string(), False))
)

BIG_TRADE_ZONE_CHECKPOINTS_SCHEMA = _schema(
    (("checkpoint_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("source_bucket_time", UTC_TS, False), ("current_relation", pa.string(), False),
     ("first_exit_direction", pa.string(), True), ("first_exit_time", UTC_TS, True),
     ("touch_count", pa.int64(), False), ("cross_count", pa.int64(), False),
     ("inside_buy_quantity", DECIMAL_38_16, False),
     ("inside_sell_quantity", DECIMAL_38_16, False),
     ("linked_event_count", pa.int64(), False), ("gap_epoch_id", pa.string(), True),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_USER_ASSESSMENTS_SCHEMA = _schema(
    (("assessment_id", pa.string(), False), ("zone_id", pa.string(), False),
     ("assessment", pa.string(), False), ("assessed_at_utc", UTC_TS, False),
     ("assessed_against_source_time", UTC_TS, False), ("user_note", pa.string(), True),
     ("supersedes_assessment_id", pa.string(), True), ("content_hash", pa.string(), False))
)

BIG_TRADE_SESSION_STATS_SCHEMA = _schema(
    (("logic_version", pa.string(), False), ("symbol", pa.string(), False),
     ("venue", pa.string(), False), ("input_mode", pa.string(), False),
     ("session_id", pa.string(), False), ("session_start", UTC_TS, False),
     ("session_end", UTC_TS, False), ("completion_status", pa.string(), False),
     ("completion_trigger", pa.string(), False), ("confirmed_by_session_id", pa.string(), False),
     ("confirmed_by_event_time", UTC_TS, False), ("confirmed_by_trade_id", pa.int64(), False),
     ("cluster_count", pa.int64(), False), ("rank_2_quantity", DECIMAL_38_16, True),
     ("rank_9_quantity", DECIMAL_38_16, True), ("rank_20_quantity", DECIMAL_38_16, True),
     ("top_quantities_json", pa.string(), False), ("valid_1m_bars", pa.int32(), False),
     ("invalid_1m_bars", pa.int32(), False), ("invalid_trades", pa.int64(), False),
     ("source_gap_count", pa.int64(), False), ("session_ntr_median", DECIMAL_38_24, True),
     ("source_first_time", UTC_TS, False), ("source_last_time", UTC_TS, False),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_CALIBRATIONS_SCHEMA = _schema(
    (("calibration_id", pa.string(), False), ("schema_version", pa.int32(), False),
     ("logic_version", pa.string(), False), ("symbol", pa.string(), False),
     ("venue", pa.string(), False), ("input_mode", pa.string(), False),
     ("session_template", pa.string(), False), ("quantity_unit", pa.string(), False),
     ("quantity_step", DECIMAL_38_16, False), ("history_start_session", pa.string(), False),
     ("history_end_session", pa.string(), False), ("valid_sessions_low", pa.int32(), False),
     ("valid_sessions_medium", pa.int32(), False), ("valid_sessions_strong", pa.int32(), False),
     ("base_low", DECIMAL_38_16, False), ("base_medium", DECIMAL_38_16, False),
     ("base_strong", DECIMAL_38_16, False), ("baseline_volatility", DECIMAL_38_24, True),
     ("recent_volatility", DECIMAL_38_24, True), ("volatility_factor", DECIMAL_38_16, False),
     ("volatility_status", pa.string(), False), ("auto_low", DECIMAL_38_16, False),
     ("auto_medium", DECIMAL_38_16, False), ("auto_strong", DECIMAL_38_16, False),
     ("aggregation_window_ms", pa.int32(), False),
     ("aggregation_candle_timeframe", pa.string(), False),
     ("target_events_json", pa.string(), False), ("source_manifest_sha256", pa.string(), False),
     ("created_at_utc", UTC_TS, False), ("content_sha256", pa.string(), False))
)

BIG_TRADE_SETTINGS_HISTORY_SCHEMA = _schema(
    (("request_id", pa.string(), False), ("settings_id", pa.string(), False),
     ("requested_at_utc", UTC_TS, False), ("previous_settings_id", pa.string(), True),
     ("request_source", pa.string(), False), ("request_status", pa.string(), False),
     ("logic_version", pa.string(), False), ("symbol", pa.string(), False),
     ("venue", pa.string(), False), ("input_mode", pa.string(), False),
     ("filter_mode", pa.string(), False), ("manual_min_quantity", DECIMAL_38_16, False),
     ("manual_max_quantity", DECIMAL_38_16, False),
     ("automatic_intensity", pa.string(), False), ("side_filter", pa.string(), False),
     ("marker_price_mode", pa.string(), False), ("calibration_id", pa.string(), True),
     ("content_hash", pa.string(), False))
)

BIG_TRADE_ACTIVATION_HISTORY_SCHEMA = _schema(
    (("activation_id", pa.string(), False), ("schema_version", pa.int32(), False),
     ("logic_version", pa.string(), False), ("symbol", pa.string(), False),
     ("venue", pa.string(), False), ("input_mode", pa.string(), False),
     ("effective_session_id", pa.string(), False),
     ("effective_from_event_time", UTC_TS, False),
     ("effective_from_trade_id", pa.int64(), False), ("settings_id", pa.string(), False),
     ("calibration_id", pa.string(), True), ("activation_reason", pa.string(), False),
     ("activation_policy", pa.string(), False), ("requested_at_utc", UTC_TS, False),
     ("content_hash", pa.string(), False))
)

BIG_TRADES_ARROW_SCHEMAS: Mapping[str, pa.Schema] = {
    "big_trade_events": BIG_TRADE_EVENTS_SCHEMA,
    "big_trade_event_fills": BIG_TRADE_EVENT_FILLS_SCHEMA,
    "big_trade_reaction_zones": BIG_TRADE_REACTION_ZONES_SCHEMA,
    "big_trade_zone_interactions": BIG_TRADE_ZONE_INTERACTIONS_SCHEMA,
    "big_trade_zone_event_links": BIG_TRADE_ZONE_EVENT_LINKS_SCHEMA,
    "big_trade_result_snapshots": BIG_TRADE_RESULT_SNAPSHOTS_SCHEMA,
    "big_trade_zone_candle_observations": BIG_TRADE_ZONE_CANDLES_SCHEMA,
    "big_trade_zone_state_checkpoints": BIG_TRADE_ZONE_CHECKPOINTS_SCHEMA,
    "big_trade_user_assessments": BIG_TRADE_USER_ASSESSMENTS_SCHEMA,
    "big_trade_session_stats": BIG_TRADE_SESSION_STATS_SCHEMA,
    "big_trade_calibrations": BIG_TRADE_CALIBRATIONS_SCHEMA,
    "big_trade_settings_history": BIG_TRADE_SETTINGS_HISTORY_SCHEMA,
    "big_trade_activation_history": BIG_TRADE_ACTIVATION_HISTORY_SCHEMA,
}


def decimal_for_storage(value: Decimal | str | int, precision: int, scale: int, name: str) -> Decimal:
    """Convert to the declared fixed-point type with deterministic half-even rounding.

    Exchange prices/quantities already fit their eight-place schema.  Derived
    values such as raw VWAP and bps can have an unbounded Decimal expansion, so
    the storage projection (not the core value or its content identity) is
    quantized at the authoritative DDL boundary.
    """
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    quantum = Decimal(1).scaleb(-scale)
    try:
        with localcontext() as context:
            context.prec = max(precision + scale + 4, len(parsed.as_tuple().digits) + scale + 4)
            quantized = parsed.quantize(quantum, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise ValueError(f"{name} exceeds DECIMAL({precision},{scale})") from exc
    integer_digits = max(quantized.adjusted() + 1, 0) if quantized else 0
    if integer_digits > precision - scale:
        raise ValueError(f"{name} exceeds DECIMAL({precision},{scale}) precision")
    return quantized


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def event_to_row(event: BigTradeEvent) -> dict[str, Any]:
    if not event.activation_id:
        raise ValueError("event activation_id is required for durable storage")
    return {
        "event_id": event.event_id, "schema_version": event.schema_version,
        "logic_version": event.logic_version, "symbol": event.symbol, "venue": event.venue,
        "side": event.side, "input_mode": event.input_mode,
        "first_trade_id": event.first_trade_id, "last_trade_id": event.last_trade_id,
        "first_time": require_aware_utc(event.first_time), "last_time": require_aware_utc(event.last_time),
        "marker_time": require_aware_utc(event.marker_time),
        "first_price": decimal_for_storage(event.first_price, 20, 8, "first_price"),
        "last_price": decimal_for_storage(event.last_price, 20, 8, "last_price"),
        "marker_price": decimal_for_storage(event.marker_price, 20, 8, "marker_price"),
        "low_price": decimal_for_storage(event.low_price, 20, 8, "low_price"),
        "high_price": decimal_for_storage(event.high_price, 20, 8, "high_price"),
        "vwap": decimal_for_storage(event.vwap, 38, 16, "vwap"),
        "aggregate_quantity": decimal_for_storage(event.aggregate_quantity, 38, 16, "aggregate_quantity"),
        "aggregate_notional": decimal_for_storage(event.aggregate_notional, 38, 8, "aggregate_notional"),
        "fill_count": event.fill_count, "price_level_count": event.price_level_count,
        "duration_ms": event.duration_ms, "close_reason": _enum(event.close_reason),
        "filter_mode": _enum(event.filter_mode), "intensity": _enum(event.intensity),
        "threshold_used": decimal_for_storage(event.threshold_used, 38, 16, "threshold_used"),
        "max_threshold_used": decimal_for_storage(event.max_threshold_used, 38, 16, "max_threshold_used"),
        "side_filter": _enum(event.side_filter), "marker_price_mode": _enum(event.marker_price_mode),
        "settings_id": event.settings_id, "calibration_id": event.calibration_id,
        "activation_id": event.activation_id, "session_id": event.session_id,
        "candle_id": candle_start(event.candle_id), "content_hash": event.content_hash,
    }


def fills_to_rows(event_id: str, fills: Iterable[BigTradeFill]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "event_id": event_id, "fill_ordinal": ordinal, "trade_id": fill.trade_id,
            "event_time": require_aware_utc(fill.event_time),
            "price": decimal_for_storage(fill.price, 20, 8, "fill.price"),
            "quantity": decimal_for_storage(fill.quantity, 20, 8, "fill.quantity"),
            "side": fill.side,
        }
        for ordinal, fill in enumerate(fills, start=1)
    )


def zone_to_row(zone: ReactionZone) -> dict[str, Any]:
    if not zone.activation_id:
        raise ValueError("zone activation_id is required for durable storage")
    return {
        "zone_id": zone.zone_id, "zone_schema_version": zone.zone_schema_version,
        "logic_version": zone.logic_version, "origin_event_id": zone.origin_event_id,
        "symbol": zone.symbol, "venue": zone.venue, "origin_side": zone.origin_side,
        "zone_low": decimal_for_storage(zone.zone_low, 20, 8, "zone_low"),
        "zone_high": decimal_for_storage(zone.zone_high, 20, 8, "zone_high"),
        "zone_anchor": decimal_for_storage(zone.zone_anchor, 38, 16, "zone_anchor"),
        "zone_visual_start": require_aware_utc(zone.zone_visual_start),
        "zone_source_start": require_aware_utc(zone.zone_source_start),
        "session_id": zone.session_id, "settings_id": zone.settings_id,
        "calibration_id": zone.calibration_id, "activation_id": zone.activation_id,
        "content_hash": zone.content_hash,
    }


def interaction_to_row(item: ZoneInteraction) -> dict[str, Any]:
    return {
        "interaction_id": item.interaction_id, "zone_id": item.zone_id,
        "interaction_type": _enum(item.interaction_type),
        "source_event_time": require_aware_utc(item.source_event_time),
        "source_trade_id": item.source_trade_id,
        "source_candle_id": candle_start(item.source_candle_id) if item.source_candle_id is not None else None,
        "price": decimal_for_storage(item.price, 20, 8, "interaction.price") if item.price is not None else None,
        "previous_relation": _enum(item.previous_relation), "current_relation": _enum(item.current_relation),
        "direction": item.direction, "ordinal": item.ordinal, "gap_epoch_id": item.gap_epoch_id,
        "content_hash": item.content_hash,
    }


def link_to_row(item: ZoneEventLink) -> dict[str, Any]:
    return {
        "link_id": item.link_id, "zone_id": item.zone_id,
        "origin_event_id": item.origin_event_id, "linked_event_id": item.linked_event_id,
        "linked_side": item.linked_side,
        "linked_quantity": decimal_for_storage(item.linked_quantity, 38, 16, "linked_quantity"),
        "linked_low": decimal_for_storage(item.linked_low, 20, 8, "linked_low"),
        "linked_high": decimal_for_storage(item.linked_high, 20, 8, "linked_high"),
        "linked_time": require_aware_utc(item.linked_time),
        "interval_gap_ticks": decimal_for_storage(item.interval_gap_ticks, 38, 16, "interval_gap_ticks"),
        "same_as_origin_side": item.same_as_origin_side,
        "ordinal_for_zone": item.ordinal_for_zone, "content_hash": item.content_hash,
    }


def snapshot_to_row(item: ResultSnapshot) -> dict[str, Any]:
    optional_decimal = lambda value, name: (
        decimal_for_storage(value, 38, 16, name) if value is not None else None
    )
    return {
        "snapshot_id": item.snapshot_id, "zone_id": item.zone_id,
        "horizon_seconds": item.horizon_seconds, "target_time": require_aware_utc(item.target_time),
        "snapshot_trade_id": item.snapshot_trade_id,
        "snapshot_trade_time": (
            require_aware_utc(item.snapshot_trade_time)
            if item.snapshot_trade_time is not None
            else None
        ),
        "source_age_ms": item.snapshot_source_age_ms,
        "snapshot_price": decimal_for_storage(item.snapshot_price, 20, 8, "snapshot_price") if item.snapshot_price is not None else None,
        "relation": _enum(item.relation),
        "return_last_bps": optional_decimal(item.return_from_last_price_bps, "return_last_bps"),
        "return_vwap_bps": optional_decimal(item.return_from_vwap_bps, "return_vwap_bps"),
        "origin_side_signed_return_bps": optional_decimal(item.origin_side_signed_return_bps, "signed_return"),
        "max_above_ticks": optional_decimal(item.max_above_ticks_to_horizon, "max_above_ticks"),
        "max_below_ticks": optional_decimal(item.max_below_ticks_to_horizon, "max_below_ticks"),
        "touch_count": item.touch_count_to_horizon, "cross_count": item.cross_count_to_horizon,
        "linked_event_count": item.linked_big_trade_count_to_horizon,
        "inside_buy_quantity": decimal_for_storage(item.inside_buy_quantity_to_horizon, 38, 16, "inside_buy_quantity"),
        "inside_sell_quantity": decimal_for_storage(item.inside_sell_quantity_to_horizon, 38, 16, "inside_sell_quantity"),
        "validity": _enum(item.validity), "content_hash": item.content_hash,
    }


def candle_observation_to_row(item: ZoneCandleObservation) -> dict[str, Any]:
    return {
        "candle_observation_id": item.candle_observation_id, "zone_id": item.zone_id,
        "candle_id": candle_start(item.candle_id),
        "open_price": decimal_for_storage(item.open_price, 20, 8, "open_price"),
        "high_price": decimal_for_storage(item.high_price, 20, 8, "high_price"),
        "low_price": decimal_for_storage(item.low_price, 20, 8, "low_price"),
        "close_price": decimal_for_storage(item.close_price, 20, 8, "close_price"),
        "open_relation": _enum(item.candle_open_relation), "close_relation": _enum(item.candle_close_relation),
        "high_above_ticks": decimal_for_storage(item.candle_high_above_ticks, 38, 16, "high_above_ticks"),
        "low_below_ticks": decimal_for_storage(item.candle_low_below_ticks, 38, 16, "low_below_ticks"),
        "body_overlaps_zone": item.body_overlaps_zone, "wick_overlaps_zone": item.wick_overlaps_zone,
        "closed_above": item.closed_above_zone, "closed_below": item.closed_below_zone,
        "upper_wick_return": item.returned_inside_after_upper_excursion,
        "lower_wick_return": item.returned_inside_after_lower_excursion,
        "content_hash": item.content_hash,
    }


def checkpoint_to_row(item: ZoneStateCheckpoint) -> dict[str, Any]:
    return {
        "checkpoint_id": item.checkpoint_id, "zone_id": item.zone_id,
        "source_bucket_time": require_aware_utc(item.source_bucket_time),
        "current_relation": _enum(item.current_relation),
        "first_exit_direction": item.first_exit_direction,
        "first_exit_time": (
            require_aware_utc(item.first_exit_time)
            if item.first_exit_time is not None
            else None
        ),
        "touch_count": item.touch_count, "cross_count": item.cross_count,
        "inside_buy_quantity": decimal_for_storage(item.inside_buy_quantity, 38, 16, "inside_buy_quantity"),
        "inside_sell_quantity": decimal_for_storage(item.inside_sell_quantity, 38, 16, "inside_sell_quantity"),
        "linked_event_count": item.linked_event_count, "gap_epoch_id": item.gap_epoch_id,
        "content_hash": item.content_hash,
    }


def assessment_to_row(item: UserAssessment) -> dict[str, Any]:
    return {
        "assessment_id": item.assessment_id, "zone_id": item.zone_id,
        "assessment": item.assessment, "assessed_at_utc": require_aware_utc(item.assessed_at_utc),
        "assessed_against_source_time": require_aware_utc(item.assessed_against_source_time),
        "user_note": item.user_note, "supersedes_assessment_id": item.supersedes_assessment_id,
        "content_hash": item.content_hash,
    }


def session_stats_to_row(item: SessionStatsArtifact) -> dict[str, Any]:
    return {
        "logic_version": item.logic_version, "symbol": item.symbol, "venue": item.venue,
        "input_mode": item.input_mode, "session_id": item.session_id,
        "session_start": require_aware_utc(item.session_start),
        "session_end": require_aware_utc(item.session_end),
        "completion_status": _enum(item.completion_status), "completion_trigger": item.completion_trigger,
        "confirmed_by_session_id": item.confirmed_by_session_id,
        "confirmed_by_event_time": require_aware_utc(item.confirmed_by_event_time),
        "confirmed_by_trade_id": item.confirmed_by_trade_id, "cluster_count": item.cluster_count,
        "rank_2_quantity": (
            decimal_for_storage(item.rank_2_quantity, 38, 16, "rank_2_quantity")
            if item.rank_2_quantity is not None else None
        ),
        "rank_9_quantity": (
            decimal_for_storage(item.rank_9_quantity, 38, 16, "rank_9_quantity")
            if item.rank_9_quantity is not None else None
        ),
        "rank_20_quantity": (
            decimal_for_storage(item.rank_20_quantity, 38, 16, "rank_20_quantity")
            if item.rank_20_quantity is not None else None
        ),
        "top_quantities_json": canonical_json(item.top_quantities),
        "valid_1m_bars": item.valid_1m_bars, "invalid_1m_bars": item.invalid_1m_bars,
        "invalid_trades": item.invalid_trades, "source_gap_count": item.source_gap_count,
        "session_ntr_median": (
            decimal_for_storage(item.session_ntr_median, 38, 24, "session_ntr_median")
            if item.session_ntr_median is not None else None
        ),
        "source_first_time": require_aware_utc(item.source_first_time),
        "source_last_time": require_aware_utc(item.source_last_time),
        "content_hash": item.content_hash,
    }


def calibration_to_row(item: CalibrationArtifact) -> dict[str, Any]:
    raw = item.to_artifact()
    return {
        "calibration_id": item.calibration_id, "schema_version": item.schema_version,
        "logic_version": item.logic_version, "symbol": item.symbol, "venue": item.venue,
        "input_mode": item.input_mode, "session_template": item.session_template,
        "quantity_unit": item.quantity_unit,
        "quantity_step": decimal_for_storage(item.quantity_step, 38, 16, "quantity_step"),
        "history_start_session": item.history_start_session,
        "history_end_session": item.history_end_session,
        "valid_sessions_low": item.valid_sessions_low,
        "valid_sessions_medium": item.valid_sessions_medium,
        "valid_sessions_strong": item.valid_sessions_strong,
        "base_low": decimal_for_storage(item.base_low, 38, 16, "base_low"),
        "base_medium": decimal_for_storage(item.base_medium, 38, 16, "base_medium"),
        "base_strong": decimal_for_storage(item.base_strong, 38, 16, "base_strong"),
        "baseline_volatility": (
            decimal_for_storage(item.baseline_volatility, 38, 24, "baseline_volatility")
            if item.baseline_volatility is not None else None
        ),
        "recent_volatility": (
            decimal_for_storage(item.recent_volatility, 38, 24, "recent_volatility")
            if item.recent_volatility is not None else None
        ),
        "volatility_factor": decimal_for_storage(
            item.volatility_factor, 38, 16, "volatility_factor"
        ),
        "volatility_status": _enum(item.volatility_status),
        "auto_low": decimal_for_storage(item.auto_low, 38, 16, "auto_low"),
        "auto_medium": decimal_for_storage(item.auto_medium, 38, 16, "auto_medium"),
        "auto_strong": decimal_for_storage(item.auto_strong, 38, 16, "auto_strong"),
        "aggregation_window_ms": item.aggregation_window_ms,
        "aggregation_candle_timeframe": item.aggregation_candle_timeframe,
        "target_events_json": canonical_json(raw["target_events"]),
        "source_manifest_sha256": item.source_manifest_sha256,
        "created_at_utc": require_aware_utc(item.created_at_utc),
        "content_sha256": item.content_sha256,
    }


def settings_history_to_row(request: SettingsRequest, version: SettingsVersion) -> dict[str, Any]:
    if request.settings_id != version.settings_id:
        raise ValueError("settings request/version mismatch")
    return {
        "request_id": request.request_id, "settings_id": request.settings_id,
        "requested_at_utc": require_aware_utc(request.requested_at_utc),
        "previous_settings_id": request.previous_settings_id,
        "request_source": _enum(request.request_source), "request_status": _enum(request.request_status),
        "logic_version": version.logic_version, "symbol": version.symbol, "venue": version.venue,
        "input_mode": version.input_mode, "filter_mode": _enum(version.filter_mode),
        "manual_min_quantity": decimal_for_storage(
            version.manual_min_quantity, 38, 16, "manual_min_quantity"
        ),
        "manual_max_quantity": decimal_for_storage(
            version.manual_max_quantity, 38, 16, "manual_max_quantity"
        ),
        "automatic_intensity": _enum(version.automatic_intensity),
        "side_filter": _enum(version.side_filter), "marker_price_mode": _enum(version.marker_price_mode),
        "calibration_id": version.calibration_id, "content_hash": request.content_hash,
    }


def activation_to_row(item: ActivationArtifact) -> dict[str, Any]:
    return {
        "activation_id": item.activation_id, "schema_version": item.schema_version,
        "logic_version": item.logic_version, "symbol": item.symbol, "venue": item.venue,
        "input_mode": item.input_mode, "effective_session_id": item.effective_session_id,
        "effective_from_event_time": require_aware_utc(item.effective_from_event_time),
        "effective_from_trade_id": item.effective_from_trade_id,
        "settings_id": item.settings_id, "calibration_id": item.calibration_id,
        "activation_reason": _enum(item.activation_reason),
        "activation_policy": _enum(item.activation_policy),
        "requested_at_utc": require_aware_utc(item.requested_at_utc),
        "content_hash": item.content_hash,
    }


def event_from_row(
    row: Mapping[str, Any],
    fill_rows: Iterable[Mapping[str, Any]] = (),
) -> BigTradeEvent:
    fills = tuple(sorted(fill_rows, key=lambda item: int(item["fill_ordinal"])))
    if fills:
        if len(fills) != int(row["fill_count"]):
            raise ValueError("event recovery fill count mismatch")
        if tuple(int(item["fill_ordinal"]) for item in fills) != tuple(
            range(1, len(fills) + 1)
        ):
            raise ValueError("event recovery fill ordinals are not contiguous")
        aggregate_quantity = sum((Decimal(item["quantity"]) for item in fills), Decimal("0"))
        aggregate_notional = sum(
            (Decimal(item["price"]) * Decimal(item["quantity"]) for item in fills),
            Decimal("0"),
        )
        raw_vwap = aggregate_notional / aggregate_quantity
    else:
        aggregate_quantity = Decimal(row["aggregate_quantity"])
        aggregate_notional = Decimal(row["aggregate_notional"])
        raw_vwap = Decimal(row["vwap"])
    candle_value = row["candle_id"]
    return BigTradeEvent(
        event_id=str(row["event_id"]),
        content_hash=str(row["content_hash"]),
        schema_version=int(row["schema_version"]),
        logic_version=str(row["logic_version"]),
        symbol=str(row["symbol"]),
        venue=str(row["venue"]),
        side=str(row["side"]),
        input_mode=str(row["input_mode"]),
        first_trade_id=int(row["first_trade_id"]),
        last_trade_id=int(row["last_trade_id"]),
        first_time=require_aware_utc(row["first_time"]),
        last_time=require_aware_utc(row["last_time"]),
        event_time=require_aware_utc(row["last_time"]),
        marker_time=require_aware_utc(row["marker_time"]),
        first_price=Decimal(row["first_price"]),
        last_price=Decimal(row["last_price"]),
        marker_price=Decimal(row["marker_price"]),
        low_price=Decimal(row["low_price"]),
        high_price=Decimal(row["high_price"]),
        vwap=raw_vwap,
        aggregate_quantity=aggregate_quantity,
        aggregate_notional=aggregate_notional,
        fill_count=int(row["fill_count"]),
        price_level_count=int(row["price_level_count"]),
        duration_ms=int(row["duration_ms"]),
        close_reason=ClusterCloseReason(row["close_reason"]),
        filter_mode=FilterMode(row["filter_mode"]),
        intensity=(
            AutomaticIntensity(row["intensity"]) if row.get("intensity") is not None else None
        ),
        threshold_used=Decimal(row["threshold_used"]),
        max_threshold_used=Decimal(row["max_threshold_used"]),
        side_filter=SideFilter(row["side_filter"]),
        marker_price_mode=MarkerPriceMode(row["marker_price_mode"]),
        settings_id=str(row["settings_id"]),
        calibration_id=row.get("calibration_id"),
        activation_id=str(row["activation_id"]),
        session_id=str(row["session_id"]),
        candle_id=(
            candle_identifier(candle_value)
            if isinstance(candle_value, datetime)
            else int(candle_value)
        ),
    )


def zone_from_row(row: Mapping[str, Any], event: BigTradeEvent) -> ReactionZone:
    if row["origin_event_id"] != event.event_id:
        raise ValueError("zone/origin event mismatch")
    return ReactionZone(
        zone_id=str(row["zone_id"]),
        content_hash=str(row["content_hash"]),
        zone_schema_version=int(row["zone_schema_version"]),
        origin_event_id=str(row["origin_event_id"]),
        zone_low=Decimal(row["zone_low"]),
        zone_high=Decimal(row["zone_high"]),
        # The immutable fills reconstruct the unbounded raw VWAP exactly; the
        # DECIMAL(38,16) column is only its storage projection.
        zone_anchor=event.vwap,
        zone_visual_start=require_aware_utc(row["zone_visual_start"]),
        zone_source_start=require_aware_utc(row["zone_source_start"]),
        origin_last_trade_id=event.last_trade_id,
        origin_last_price=event.last_price,
        origin_side=str(row["origin_side"]),
        symbol=str(row["symbol"]),
        venue=str(row["venue"]),
        session_id=str(row["session_id"]),
        logic_version=str(row["logic_version"]),
        settings_id=str(row["settings_id"]),
        calibration_id=row.get("calibration_id"),
        activation_id=str(row["activation_id"]),
        lifecycle=ZoneLifecycle.ACTIVE,
    )


def interaction_from_row(row: Mapping[str, Any]) -> ZoneInteraction:
    candle_value = row.get("source_candle_id")
    return ZoneInteraction(
        interaction_id=str(row["interaction_id"]),
        content_hash=str(row["content_hash"]),
        zone_id=str(row["zone_id"]),
        interaction_type=InteractionType(row["interaction_type"]),
        source_event_time=require_aware_utc(row["source_event_time"]),
        source_trade_id=(int(row["source_trade_id"]) if row.get("source_trade_id") is not None else None),
        source_candle_id=(
            candle_identifier(candle_value)
            if isinstance(candle_value, datetime)
            else int(candle_value)
            if candle_value is not None
            else None
        ),
        price=Decimal(row["price"]) if row.get("price") is not None else None,
        previous_relation=(
            PriceRelation(row["previous_relation"])
            if row.get("previous_relation") is not None
            else None
        ),
        current_relation=(
            PriceRelation(row["current_relation"])
            if row.get("current_relation") is not None
            else None
        ),
        direction=row.get("direction"),
        ordinal=int(row["ordinal"]),
        gap_epoch_id=row.get("gap_epoch_id"),
    )


def link_from_row(row: Mapping[str, Any]) -> ZoneEventLink:
    return ZoneEventLink(
        link_id=str(row["link_id"]),
        content_hash=str(row["content_hash"]),
        zone_id=str(row["zone_id"]),
        origin_event_id=str(row["origin_event_id"]),
        linked_event_id=str(row["linked_event_id"]),
        linked_side=str(row["linked_side"]),
        linked_quantity=Decimal(row["linked_quantity"]),
        linked_low=Decimal(row["linked_low"]),
        linked_high=Decimal(row["linked_high"]),
        linked_time=require_aware_utc(row["linked_time"]),
        interval_gap_ticks=Decimal(row["interval_gap_ticks"]),
        same_as_origin_side=bool(row["same_as_origin_side"]),
        ordinal_for_zone=int(row["ordinal_for_zone"]),
    )


def checkpoint_from_row(row: Mapping[str, Any]) -> ZoneStateCheckpoint:
    return ZoneStateCheckpoint(
        checkpoint_id=str(row["checkpoint_id"]),
        zone_id=str(row["zone_id"]),
        source_bucket_time=require_aware_utc(row["source_bucket_time"]),
        current_relation=PriceRelation(row["current_relation"]),
        first_exit_direction=row.get("first_exit_direction"),
        first_exit_time=(
            require_aware_utc(row["first_exit_time"])
            if row.get("first_exit_time") is not None
            else None
        ),
        touch_count=int(row["touch_count"]),
        cross_count=int(row["cross_count"]),
        inside_buy_quantity=Decimal(row["inside_buy_quantity"]),
        inside_sell_quantity=Decimal(row["inside_sell_quantity"]),
        linked_event_count=int(row["linked_event_count"]),
        gap_epoch_id=row.get("gap_epoch_id"),
        content_hash=str(row["content_hash"]),
    )


def snapshot_from_row(row: Mapping[str, Any]) -> ResultSnapshot:
    return ResultSnapshot(
        snapshot_id=str(row["snapshot_id"]),
        content_hash=str(row["content_hash"]),
        zone_id=str(row["zone_id"]),
        horizon_seconds=int(row["horizon_seconds"]),
        target_time=require_aware_utc(row["target_time"]),
        snapshot_trade_id=(
            int(row["snapshot_trade_id"]) if row.get("snapshot_trade_id") is not None else None
        ),
        snapshot_trade_time=(
            require_aware_utc(row["snapshot_trade_time"])
            if row.get("snapshot_trade_time") is not None
            else None
        ),
        snapshot_source_age_ms=(
            int(row["source_age_ms"]) if row.get("source_age_ms") is not None else None
        ),
        snapshot_price=(
            Decimal(row["snapshot_price"]) if row.get("snapshot_price") is not None else None
        ),
        relation=(PriceRelation(row["relation"]) if row.get("relation") is not None else None),
        return_from_last_price_bps=(
            Decimal(row["return_last_bps"]) if row.get("return_last_bps") is not None else None
        ),
        return_from_vwap_bps=(
            Decimal(row["return_vwap_bps"]) if row.get("return_vwap_bps") is not None else None
        ),
        origin_side_signed_return_bps=(
            Decimal(row["origin_side_signed_return_bps"])
            if row.get("origin_side_signed_return_bps") is not None
            else None
        ),
        max_above_ticks_to_horizon=Decimal(row["max_above_ticks"]),
        max_below_ticks_to_horizon=Decimal(row["max_below_ticks"]),
        touch_count_to_horizon=int(row["touch_count"]),
        cross_count_to_horizon=int(row["cross_count"]),
        linked_big_trade_count_to_horizon=int(row["linked_event_count"]),
        inside_buy_quantity_to_horizon=Decimal(row["inside_buy_quantity"]),
        inside_sell_quantity_to_horizon=Decimal(row["inside_sell_quantity"]),
        validity=SnapshotValidity(row["validity"]),
    )


@dataclass(frozen=True)
class BigTradeOriginStorageBatch:
    batch_id: str
    event: Mapping[str, Any]
    fills: tuple[Mapping[str, Any], ...]
    zone: Mapping[str, Any]
    created_interaction: Mapping[str, Any]
    prior_zone_links: tuple[Mapping[str, Any], ...]

    @classmethod
    def create(
        cls,
        event: BigTradeEvent,
        fills: Iterable[BigTradeFill],
        zone: ReactionZone,
        created_interaction: ZoneInteraction,
        prior_zone_links: Iterable[ZoneEventLink] = (),
    ) -> "BigTradeOriginStorageBatch":
        fill_rows = fills_to_rows(event.event_id, fills)
        if len(fill_rows) != event.fill_count:
            raise ValueError("origin batch fill count mismatch")
        if not fill_rows:
            raise ValueError("origin batch must contain at least one fill")
        if fill_rows[0]["trade_id"] != event.first_trade_id:
            raise ValueError("origin batch first fill mismatch")
        if fill_rows[-1]["trade_id"] != event.last_trade_id:
            raise ValueError("origin batch last fill mismatch")
        if any(row["side"] != event.side for row in fill_rows):
            raise ValueError("origin batch fill side mismatch")
        if zone.origin_event_id != event.event_id or created_interaction.zone_id != zone.zone_id:
            raise ValueError("origin batch identity mismatch")
        if _enum(created_interaction.interaction_type) != "ZONE_CREATED":
            raise ValueError("origin batch requires ZONE_CREATED interaction")
        if zone.activation_id != event.activation_id:
            raise ValueError("origin batch activation mismatch")
        link_rows = tuple(link_to_row(item) for item in prior_zone_links)
        if any(row["linked_event_id"] != event.event_id for row in link_rows):
            raise ValueError("origin batch prior-zone link mismatch")
        payload_hash = content_hash(
            {
                "event": event.content_hash,
                "fills": content_hash(fill_rows),
                "zone": zone.content_hash,
                "created_interaction": created_interaction.content_hash,
                "links": [row["content_hash"] for row in link_rows],
            }
        )
        return cls(
            batch_id="btbatch2_" + sha256_hex(event.event_id + "|" + payload_hash),
            event=event_to_row(event),
            fills=fill_rows,
            zone=zone_to_row(zone),
            created_interaction=interaction_to_row(created_interaction),
            prior_zone_links=link_rows,
        )


def table_from_rows(table_name: str, rows: Iterable[Mapping[str, Any]]) -> pa.Table:
    return pa.Table.from_pylist([dict(row) for row in rows], schema=BIG_TRADES_ARROW_SCHEMAS[table_name])
