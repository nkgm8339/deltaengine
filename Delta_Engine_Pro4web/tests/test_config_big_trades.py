from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import ConfigValidationError, load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def _config() -> dict:
    return yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))


def _load(tmp_path: Path, data: dict):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(path)


def test_shipped_big_trades_config_is_valid_and_disabled() -> None:
    section = load_config(SHIPPED_CONFIG).big_trades
    assert section.enabled is False
    assert section.input_mode == "AGGREGATE_TRADES"
    assert section.manual_min_quantity == "5.000"
    assert section.manual_max_quantity == "0"
    assert list(section.result_horizons_seconds) == [1, 5, 15, 30, 60, 180, 300, 600]


def test_big_trades_unknown_key_is_startup_error(tmp_path: Path) -> None:
    data = _config()
    data["big_trades"]["unknown"] = True
    with pytest.raises(ConfigValidationError, match="big_trades.unknown"):
        _load(tmp_path, data)


@pytest.mark.parametrize("value", [5, -1, "NaN", "Infinity", "-0.001"])
def test_big_trades_manual_quantity_requires_nonnegative_finite_decimal_string(
    tmp_path: Path, value: object
) -> None:
    data = _config()
    data["big_trades"]["manual_min_quantity"] = value
    with pytest.raises(ConfigValidationError):
        _load(tmp_path, data)


def test_big_trades_max_must_be_zero_or_at_least_min(tmp_path: Path) -> None:
    data = _config()
    data["big_trades"]["manual_min_quantity"] = "5"
    data["big_trades"]["manual_max_quantity"] = "4.999"
    with pytest.raises(ConfigValidationError, match="manual_max_quantity"):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("input_mode", "ORDER"),
        ("filter_mode", "AUTO"),
        ("automatic_intensity", "EXTREME"),
        ("side_filter", "NONE"),
        ("marker_price_mode", "MID"),
        ("calibration_schedule", "DAILY"),
        ("calibration_activation_policy", "AUTO"),
        ("replay_calibration_mode", "LATEST"),
        ("reaction_observation_mode", "LOCAL_DAY"),
    ),
)
def test_big_trades_closed_enums_reject_unknown_values(
    tmp_path: Path, key: str, value: str
) -> None:
    data = _config()
    data["big_trades"][key] = value
    with pytest.raises(ConfigValidationError):
        _load(tmp_path, data)


@pytest.mark.parametrize("value", [[], [1, 1], [5, 1], [1, 601], [True, 5]])
def test_big_trades_horizons_are_positive_unique_ascending_and_bounded(
    tmp_path: Path, value: list[object]
) -> None:
    data = _config()
    data["big_trades"]["result_horizons_seconds"] = value
    with pytest.raises(ConfigValidationError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    "key",
    (
        "reaction_zone_match_tolerance_ticks",
        "active_zone_capacity",
        "recent_event_capacity",
        "recent_interaction_capacity",
        "history_api_max_limit",
        "batch_interval_ms",
        "batch_max_records",
        "batch_pending_capacity",
        "max_fills_per_cluster",
    ),
)
@pytest.mark.parametrize("value", [0, -1, True])
def test_big_trades_integer_limits_are_strictly_positive(
    tmp_path: Path, key: str, value: object
) -> None:
    data = _config()
    data["big_trades"][key] = value
    with pytest.raises(ConfigValidationError):
        _load(tmp_path, data)
