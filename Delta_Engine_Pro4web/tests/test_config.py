"""Tests for src.config — YAMLReference_v3.1 loading and startup validation.

Verifies: the shipped v3.1 config loads; defaults fill omitted keys; required
keys (websocket.url / subscribe_streams) and every class of invalid value fail
startup with the correct ErrorCodes_v3.1 code.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from src.config import (
    ERROR_CONFIG_NOT_FOUND,
    ERROR_CONFIG_VALIDATION,
    ConfigFileNotFoundError,
    ConfigNode,
    ConfigValidationError,
    load_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def _base_dict() -> dict:
    """A full, valid v3.1 configuration as a plain dict (YAMLReference §2)."""
    return {
        "system": {"timezone": "UTC", "log_level": "INFO"},
        "market": {"symbol": "BTCUSDT", "exchange": "BINANCE", "bar_timeframe": "1m", "tick_size": "0.1"},
        "websocket": {
            "url": "wss://fstream.binance.com/ws",
            "reconnect": True,
            "reconnect_delay_sec": 5,
            "reconnect_max_retries": 0,
            "heartbeat_sec": 30,
            "connect_timeout_sec": 10,
            "subscribe_streams": ["btcusdt@aggTrade", "btcusdt@depth@100ms"],
        },
        "normalizer": {
            "exchange_profile": "binance",
            "dedup_window": 10000,
            "reorder_tolerance_ms": 500,
        },
        "queue": {"default_depth": 10000, "overflow_policy": "drop_oldest_log"},
        "database": {
            "parquet_path": "data/parquet",
            "duckdb_path": "data/duckdb/orderflow.duckdb",
            "batch_size": 1000,
            "flush_interval_sec": 5,
        },
        "signal": {
            "enabled": False,
            "weight": {"cvd": 1.0, "footprint": 1.0, "imbalance": 1.0},
            "confidence_threshold": 0.6,
            "cvd_slope_ref": None,
            "stack_ref": 3,
            "absorption_veto_threshold": 0.5,
            "evaluation_window": "1 bar",
        },
        "imbalance": {
            "ratio_threshold": 3.0,
            "min_volume": None,
            "ratio_cap": 10.0,
            "stack_count": 3,
        },
        "absorption": {
            "window_sec": 10,
            "price_stall_ticks": 1,
            "volume_multiplier": 2.0,
            "volume_ref_bars": 20,
        },
        "mt5": {
            "enabled": False,
            "bind_address": "127.0.0.1",
            "port": 5555,
            "max_clients": 3,
            "heartbeat_interval_sec": 5,
            "max_buffer_messages": 1000,
        },
        "ai": {"enabled": False, "confidence_threshold": 0.70},
        "replay": {"enabled": False, "data_path": None, "speed": 1.0},
        "calibration": {"cvd_slope_ref": None},
    }


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --- happy path ---------------------------------------------------------------
def test_shipped_config_is_valid() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert isinstance(config, ConfigNode)
    assert config.market.symbol == "BTCUSDT"
    assert config.market.bar_timeframe == "1m"
    assert config.websocket.url.startswith("wss://")
    assert list(config.websocket.subscribe_streams) == [
        "btcusdt@trade",
        "btcusdt@depth@100ms",
        "btcusdt@forceOrder",
    ]
    assert config.database.flush_interval_sec == 5
    assert config.normalizer.live_reorder_tolerance_ms == 0
    assert config.webapp.tick_push_interval_ms == 50
    assert config.webapp.bar_update_interval_sec == pytest.approx(0.2)
    assert config.signal.weight.cvd == pytest.approx(1.0)
    assert config.calibration.cvd_slope_ref is None
    assert config.replay.speed == pytest.approx(1.0)
    assert list(config.flow_response.windows_sec) == [30, 60, 180, 300, 900, 1800]
    assert list(config.flow_response.outcome_horizons_sec) == [60, 180, 300, 600]


def test_base_dict_loads(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, _base_dict()))
    assert config.system.log_level == "INFO"
    assert config.mt5.port == 5555
    assert config.ai.confidence_threshold == pytest.approx(0.70)


# --- defaults (sample values fill omitted keys) -------------------------------
def test_bar_timeframe_defaults_when_absent(tmp_path: Path) -> None:
    data = _base_dict()
    del data["market"]["bar_timeframe"]
    assert load_config(_write(tmp_path, data)).market.bar_timeframe == "1m"

def test_tick_size_zero_is_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["market"]["tick_size"] = "0"
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))

def test_tick_size_is_required_decimal_string(tmp_path: Path) -> None:
    data = _base_dict()
    del data["market"]["tick_size"]
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_optional_sections_default(tmp_path: Path) -> None:
    data = _base_dict()
    del data["signal"]
    del data["queue"]
    del data["calibration"]
    config = load_config(_write(tmp_path, data))
    assert config.signal.confidence_threshold == pytest.approx(0.6)
    assert config.queue.overflow_policy == "drop_oldest_log"
    assert config.calibration.cvd_slope_ref is None
    assert config.flow_response.enabled is True
    assert config.flow_response.baseline_window_sec == 1800


def test_flow_response_windows_must_be_positive_nonempty_list(tmp_path: Path) -> None:
    data = _base_dict()
    data["flow_response"] = {"windows_sec": []}
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))

    data["flow_response"] = {"windows_sec": [60, 0]}
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_calibration_accepts_number(tmp_path: Path) -> None:
    data = _base_dict()
    data["calibration"]["cvd_slope_ref"] = 1.5
    assert load_config(_write(tmp_path, data)).calibration.cvd_slope_ref == pytest.approx(1.5)


# --- required keys (WebSocket §6: url / subscribe_streams) ---------------------
def test_missing_url_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    del data["websocket"]["url"]
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_write(tmp_path, data))
    assert any("websocket.url" in p for p in exc.value.problems)


def test_empty_subscribe_streams_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["websocket"]["subscribe_streams"] = []
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


# --- file not found (E1001) ---------------------------------------------------
def test_missing_file_raises_e1001(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileNotFoundError) as exc:
        load_config(tmp_path / "nope.yaml")
    assert exc.value.code == ERROR_CONFIG_NOT_FOUND


# --- validation failures (E1002) ----------------------------------------------
def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigValidationError) as exc:
        load_config(path)
    assert exc.value.code == ERROR_CONFIG_VALIDATION


def test_unknown_top_level_section_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["bogus"] = {"x": 1}
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_write(tmp_path, data))
    assert any("bogus" in p for p in exc.value.problems)


def test_unknown_key_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["system"]["extra"] = "nope"
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_write(tmp_path, data))
    assert any("system.extra" in p for p in exc.value.problems)


def test_invalid_log_level_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["system"]["log_level"] = "VERBOSE"
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_invalid_bar_timeframe_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["market"]["bar_timeframe"] = "2m"  # not in EnumDefinitions Timeframe
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_bool_not_accepted_as_int(tmp_path: Path) -> None:
    data = _base_dict()
    data["database"]["batch_size"] = True
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_negative_flush_interval_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["database"]["flush_interval_sec"] = 0
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_confidence_threshold_out_of_range_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["ai"]["confidence_threshold"] = 1.5
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_port_out_of_range_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["mt5"]["port"] = 70000
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_signal_weight_unknown_key_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["signal"]["weight"]["bogus"] = 1.0
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_signal_weight_negative_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["signal"]["weight"]["cvd"] = -1.0
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_subscribe_streams_must_be_list(tmp_path: Path) -> None:
    data = _base_dict()
    data["websocket"]["subscribe_streams"] = "btcusdt@aggTrade"
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_replay_speed_negative_rejected(tmp_path: Path) -> None:
    data = _base_dict()
    data["replay"]["speed"] = -1.0
    with pytest.raises(ConfigValidationError):
        load_config(_write(tmp_path, data))


def test_min_volume_accepts_null_and_number(tmp_path: Path) -> None:
    data = _base_dict()
    data["imbalance"]["min_volume"] = 0.5
    assert load_config(_write(tmp_path, data)).imbalance.min_volume == pytest.approx(0.5)


def test_all_problems_aggregated(tmp_path: Path) -> None:
    data = _base_dict()
    data["system"]["log_level"] = "VERBOSE"
    data["websocket"]["heartbeat_sec"] = -1
    data["mt5"]["port"] = 0
    with pytest.raises(ConfigValidationError) as exc:
        load_config(_write(tmp_path, data))
    assert len(exc.value.problems) >= 3


def test_config_is_read_only(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, _base_dict()))
    with pytest.raises((AttributeError, TypeError)):
        config.market.symbol = "ETHUSDT"  # type: ignore[misc]


def test_base_dict_isolated() -> None:
    assert _base_dict() == copy.deepcopy(_base_dict())
