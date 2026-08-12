"""Deterministic replay driver for contract tests.

Two input paths are supported so both synthetic and real-data-derived tests can be
written against the same enforcer:

- ``replay_synthetic`` feeds a fully controlled ContractEvent sequence.
- ``events_from_journal_records`` maps integrity-checked journal records
  (``src.observation.hook_replay.JournalRecord`` shape) into ContractEvents via a
  caller-supplied mapper, without touching or modifying any recorded session.

The driver never produces an order. ``ReplayReport.order_intents`` is structurally
zero: the enforcer has no order path, and TERMINAL yields only gate handoffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from .enforcer import ContractEnforcer, OrderReadyHandoff, StepResult
from .events import ContractEvent


@dataclass
class ReplayReport:
    steps: list[StepResult] = field(default_factory=list)
    handoffs: list[OrderReadyHandoff] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return sum(1 for s in self.steps if s.accepted)

    @property
    def rejected(self) -> int:
        return sum(1 for s in self.steps if s.rejected)

    @property
    def order_intents(self) -> int:
        # Invariant: no order path exists. Terminal outputs are gate handoffs,
        # never orders. This is always zero by construction (direct authority 0).
        return 0


def replay_synthetic(
    enforcer: ContractEnforcer, events: Iterable[ContractEvent]
) -> ReplayReport:
    report = ReplayReport()
    for event in events:
        result = enforcer.submit(event)
        report.steps.append(result)
        if result.handoff is not None:
            report.handoffs.append(result.handoff)
    return report


def events_from_journal_records(
    records: Iterable[Any],
    mapper: Callable[[Any], ContractEvent | None],
) -> Iterator[ContractEvent]:
    """Map integrity-checked journal records into ContractEvents (read-only).

    ``mapper`` returns None to skip a record. The recorded session is never
    modified; this only reads the records yielded by JournalReplay.
    """
    for record in records:
        event = mapper(record)
        if event is not None:
            yield event
