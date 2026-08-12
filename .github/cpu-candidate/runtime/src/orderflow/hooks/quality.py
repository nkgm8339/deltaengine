"""Independent DOM data-quality gate for research Hook eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import HookQualityStatus


class DomSyncState(str, Enum):
    EMPTY = "EMPTY"
    WAITING_FIRST_DIFF = "WAITING_FIRST_DIFF"
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True)
class DomQualitySnapshot:
    state: DomSyncState
    status: HookQualityStatus
    last_update_id: int | None
    reason: str | None
    valid_diffs: int
    rejected_diffs: int
    gaps: int


class DomDataQualityGate:
    """Stricter research gate without changing live OrderBookStateManager."""

    def __init__(self) -> None:
        self.state = DomSyncState.EMPTY
        self.last_update_id: int | None = None
        self.reason: str | None = "NO_SNAPSHOT"
        self.valid_diffs = 0
        self.rejected_diffs = 0
        self.gaps = 0

    @property
    def is_valid(self) -> bool:
        return self.state is DomSyncState.VALID

    def observe(self, update: Any, apply_result: Any) -> DomQualitySnapshot:
        if getattr(apply_result, "gap_detected", False):
            self.state = DomSyncState.INVALID
            self.last_update_id = None
            self.reason = "SEQUENCE_GAP"
            self.gaps += 1
            return self.snapshot()

        if update.update_type == "SNAPSHOT" and getattr(apply_result, "applied", False):
            self.state = DomSyncState.WAITING_FIRST_DIFF
            self.last_update_id = int(update.final_update_id)
            self.reason = "WAITING_FIRST_DIFF"
            return self.snapshot()

        if update.update_type != "DIFF" or not getattr(apply_result, "applied", False):
            return self.snapshot()

        if self.state is DomSyncState.WAITING_FIRST_DIFF:
            assert self.last_update_id is not None
            target = self.last_update_id + 1
            first_id = update.first_update_id
            aligned = (
                first_id is not None
                and int(first_id) <= target <= int(update.final_update_id)
            )
            if not aligned:
                self.state = DomSyncState.INVALID
                self.reason = "INITIAL_DIFF_MISALIGNED"
                self.rejected_diffs += 1
                return self.snapshot()
            self.state = DomSyncState.VALID
            self.last_update_id = int(update.final_update_id)
            self.reason = None
            self.valid_diffs += 1
            return self.snapshot()

        if self.state is not DomSyncState.VALID or self.last_update_id is None:
            self.rejected_diffs += 1
            return self.snapshot()

        if update.previous_final_update_id is not None:
            continuous = int(update.previous_final_update_id) == self.last_update_id
        else:
            first_id = update.first_update_id
            continuous = (
                first_id is not None
                and int(first_id) <= self.last_update_id + 1 <= int(update.final_update_id)
            )
        if not continuous:
            self.state = DomSyncState.INVALID
            self.last_update_id = None
            self.reason = "SEQUENCE_GAP"
            self.rejected_diffs += 1
            self.gaps += 1
            return self.snapshot()

        self.last_update_id = int(update.final_update_id)
        self.valid_diffs += 1
        return self.snapshot()

    def snapshot(self) -> DomQualitySnapshot:
        status = (
            HookQualityStatus.VALID
            if self.state is DomSyncState.VALID
            else HookQualityStatus.INVALID
        )
        return DomQualitySnapshot(
            state=self.state,
            status=status,
            last_update_id=self.last_update_id,
            reason=self.reason,
            valid_diffs=self.valid_diffs,
            rejected_diffs=self.rejected_diffs,
            gaps=self.gaps,
        )
