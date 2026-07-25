from __future__ import annotations

import pytest

from tools.snapshot_mt5_hfm_ticks import calibrate_clock


def test_clock_calibration_requires_paired_and_live_agreement() -> None:
    result = calibrate_clock(
        [10800.10, 10799.80, 10800.25] * 10,
        [10800100.0, 10800300.0, 10799800.0],
    )
    assert result.offset_sec == 10800
    assert result.anchor_count == 30
    assert result.live_sample_count == 3


def test_clock_calibration_rejects_live_offset_mismatch() -> None:
    with pytest.raises(ValueError, match="disagrees"):
        calibrate_clock(
            [10800.10] * 20,
            [7200000.0],
        )

