"""Unit tests for VolumeRefTracker (B-2).

6 tests covering: empty state, single-bar average, window slide,
Decimal purity, determinism, and invalid-bars guard.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.orderflow.volume_ref import VolumeRefTracker

D = Decimal


# ── 1. empty returns None ────────────────────────────────────────────────────

def test_volume_ref_empty_returns_none() -> None:
    tracker = VolumeRefTracker(bars=3)
    assert tracker.current() is None
    assert tracker.observations == 0


# ── 2. single bar: level-weighted average ────────────────────────────────────

def test_volume_ref_single_bar() -> None:
    tracker = VolumeRefTracker(bars=5)
    # One bar with 3 levels: volumes 10, 20, 30
    tracker.observe_bar([D("10"), D("20"), D("30")])
    result = tracker.current()
    assert result is not None
    # level-weighted: (10+20+30) / 3 levels = 20
    assert result == D("20")
    assert tracker.observations == 1


# ── 3. window slide: old bars fall off ───────────────────────────────────────

def test_volume_ref_window_slide() -> None:
    tracker = VolumeRefTracker(bars=2)
    # Bar 0: single level with volume 10
    tracker.observe_bar([D("10")])
    # Bar 1: single level with volume 30
    tracker.observe_bar([D("30")])
    # Window has bars 0 and 1 → avg = (10+30)/(1+1) = 20
    assert tracker.current() == D("20")

    # Bar 2: single level with volume 50 → bar 0 falls off
    tracker.observe_bar([D("50")])
    # Window has bars 1 and 2 → avg = (30+50)/(1+1) = 40
    assert tracker.current() == D("40")
    assert tracker.observations == 3


# ── 4. Decimal purity ────────────────────────────────────────────────────────

def test_volume_ref_all_decimal() -> None:
    tracker = VolumeRefTracker(bars=1)
    tracker.observe_bar([D("7"), D("13")])
    result = tracker.current()
    assert result is not None
    assert isinstance(result, Decimal)
    # (7+13) / 2 levels = 10
    assert result == D("10")


# ── 5. deterministic ─────────────────────────────────────────────────────────

def test_volume_ref_deterministic() -> None:
    def run():
        t = VolumeRefTracker(bars=3)
        t.observe_bar([D("5"), D("15")])
        t.observe_bar([D("10")])
        t.observe_bar([D("20"), D("30"), D("10")])
        return t.current()

    assert run() == run()


# ── 6. invalid bars raises ───────────────────────────────────────────────────

def test_volume_ref_invalid_bars_raises() -> None:
    with pytest.raises(ValueError):
        VolumeRefTracker(bars=0)
    with pytest.raises(ValueError):
        VolumeRefTracker(bars=-1)
