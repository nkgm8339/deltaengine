"""Validated audit records for manual HFM execution research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ManualExecutionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    QUOTE_STALE = "QUOTE_STALE"


@dataclass(frozen=True)
class ManualExecutionRecord:
    record_id: str
    episode_id: str
    symbol: str
    window_sec: int
    checkpoint_time: datetime
    checkpoint_stage: str
    pressure_side: str
    signal_displayed_time: datetime
    decision_time: datetime | None
    order_time: datetime | None
    fill_time: datetime | None
    status: ManualExecutionStatus
    entry_side: str | None
    entry_price: float | None
    entry_bid: float | None
    entry_ask: float | None
    exit_time: datetime | None
    exit_price: float | None
    skip_reason: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id or not self.episode_id or not self.symbol:
            raise ValueError("record_id, episode_id, and symbol are required")
        if self.window_sec < 1:
            raise ValueError("window_sec must be positive")
        for value in (
            self.checkpoint_time,
            self.signal_displayed_time,
            self.decision_time,
            self.order_time,
            self.fill_time,
            self.exit_time,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("all timestamps must be timezone-aware")
        local_times = [
            value for value in (
                self.signal_displayed_time,
                self.decision_time,
                self.order_time,
                self.fill_time,
                self.exit_time,
            ) if value is not None
        ]
        if local_times != sorted(local_times):
            raise ValueError("manual execution timestamps must be chronological")
        if self.entry_side is not None and self.entry_side not in {"LONG", "SHORT"}:
            raise ValueError("entry_side must be LONG or SHORT")
        if self.status is ManualExecutionStatus.EXECUTED:
            if self.entry_side is None or self.entry_price is None or self.fill_time is None:
                raise ValueError("EXECUTED records require side, entry price, and fill time")
            if self.exit_time is None or self.exit_price is None:
                raise ValueError("EXECUTED records require exit time and exit price")
        elif not self.skip_reason:
            raise ValueError("non-executed records require skip_reason")
        for name, value in (
            ("entry_price", self.entry_price),
            ("entry_bid", self.entry_bid),
            ("entry_ask", self.entry_ask),
            ("exit_price", self.exit_price),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.entry_bid is not None and self.entry_ask is not None:
            if self.entry_ask < self.entry_bid:
                raise ValueError("entry ask must be >= entry bid")

    @property
    def execution_delay_ms(self) -> int | None:
        if self.fill_time is None:
            return None
        return int((self.fill_time - self.signal_displayed_time).total_seconds() * 1000)

    def to_row(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "episode_id": self.episode_id,
            "symbol": self.symbol,
            "window_sec": self.window_sec,
            "checkpoint_time": self.checkpoint_time,
            "checkpoint_stage": self.checkpoint_stage,
            "pressure_side": self.pressure_side,
            "signal_displayed_time": self.signal_displayed_time,
            "decision_time": self.decision_time,
            "order_time": self.order_time,
            "fill_time": self.fill_time,
            "status": self.status.value,
            "entry_side": self.entry_side,
            "entry_price": self.entry_price,
            "entry_bid": self.entry_bid,
            "entry_ask": self.entry_ask,
            "exit_time": self.exit_time,
            "exit_price": self.exit_price,
            "execution_delay_ms": self.execution_delay_ms,
            "skip_reason": self.skip_reason,
            "notes": self.notes,
        }
