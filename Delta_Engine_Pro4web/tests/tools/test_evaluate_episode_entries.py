from datetime import datetime, timezone

import pytest

from tools.evaluate_episode_entries import _parse_datetime, _rate, _session_id

UTC = timezone.utc


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "ASIA"),
        (7, "ASIA"),
        (8, "EUROPE"),
        (12, "EUROPE"),
        (13, "EUROPE_NY_OVERLAP"),
        (16, "EUROPE_NY_OVERLAP"),
        (17, "NEW_YORK"),
        (21, "NEW_YORK"),
        (22, "LATE"),
        (23, "LATE"),
    ],
)
def test_fixed_utc_session_boundaries(hour, expected):
    assert _session_id(datetime(2026, 7, 25, hour, tzinfo=UTC)) == expected


def test_rate_does_not_turn_empty_groups_into_zero():
    assert _rate(0, 0) is None
    assert _rate(1, 4) == pytest.approx(0.25)


def test_entry_cutoff_requires_an_explicit_timezone():
    assert _parse_datetime("2026-07-25T06:40:00Z").tzinfo is not None
    with pytest.raises(ValueError, match="timezone-aware"):
        _parse_datetime("2026-07-25T06:40:00")
