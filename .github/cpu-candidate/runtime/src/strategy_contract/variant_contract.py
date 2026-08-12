"""Read-only loader for a single named-variant FSM contract from the canon.

The FSM edge structure comes from the canonical CSVs (read-only):

- ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANT_FSM_V0_1_20260727.csv  (edge structure)
- ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv    (predicate classes)

This loader NEVER writes to the canon. It exposes only the structural information
the enforcer needs: ordered states, edge types, terminal direction, and which
edges depend on a hard source (OI) so 判定契約9 can be enforced.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# .../Delta_Engine_Pro4web/src/strategy_contract/variant_contract.py
# parents[3] == repository root that also contains ArchitectureRepository/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANON_DIR = (
    _REPO_ROOT
    / "ArchitectureRepository"
    / "00_Master"
    / "トリガー作成指示書群"
)
_FSM_CSV = "ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANT_FSM_V0_1_20260727.csv"
_BINDINGS_CSV = "ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv"

# Predicate classes that require a hard source snapshot; OI is 10s-poll-limited and
# must not be substituted when UNKNOWN/STALE (判定契約9).
_HARD_SOURCE_PREDICATE_CLASSES = frozenset({"OPEN_INTEREST_CHANGE"})

_EDGE_LOCATION_ARM = "LOCATION_ARM"
_EDGE_ADVANCE = "ADVANCE"
_EDGE_TERMINAL = "TERMINAL"
_EDGE_INVALIDATE = "INVALIDATE"
_EDGE_EXPIRE = "EXPIRE"


class VariantContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContractEdge:
    edge_id: str
    edge_type: str
    from_state: str
    to_state: str
    predicate_classes: tuple[str, ...]
    hard_source_required: bool


@dataclass(frozen=True)
class VariantContract:
    variant_id: str
    terminal_direction: str  # LONG / SHORT
    edges: Mapping[str, ContractEdge]
    location_arm_edge_id: str
    ordered_advance_edge_ids: tuple[str, ...]
    terminal_edge_id: str
    invalidate_edge_id: str
    expire_edge_id: str
    armed_from_state: str
    location_state: str

    @classmethod
    def load(
        cls,
        variant_id: str,
        *,
        canon_dir: Path | None = None,
    ) -> "VariantContract":
        base = canon_dir or _CANON_DIR
        fsm_rows = _read_variant_rows(base / _FSM_CSV, "variant_id", variant_id)
        if not fsm_rows:
            raise VariantContractError(f"variant not found in FSM canon: {variant_id}")
        binding_classes = _binding_predicate_classes(base / _BINDINGS_CSV, variant_id)

        edges: dict[str, ContractEdge] = {}
        for row in fsm_rows:
            edge_id = row["variant_edge_id"]
            classes = binding_classes.get(edge_id, ())
            edges[edge_id] = ContractEdge(
                edge_id=edge_id,
                edge_type=row["edge_type"],
                from_state=row["from_state_id"],
                to_state=row["to_state_id"],
                predicate_classes=classes,
                hard_source_required=bool(
                    _HARD_SOURCE_PREDICATE_CLASSES.intersection(classes)
                ),
            )

        location_arm = _single(edges, _EDGE_LOCATION_ARM, variant_id)
        terminal = _single(edges, _EDGE_TERMINAL, variant_id)
        invalidate = _single(edges, _EDGE_INVALIDATE, variant_id)
        expire = _single(edges, _EDGE_EXPIRE, variant_id)
        advance_ids = tuple(
            sorted(
                edge_id
                for edge_id, edge in edges.items()
                if edge.edge_type == _EDGE_ADVANCE
            )
        )
        if not advance_ids:
            raise VariantContractError(f"variant has no ADVANCE edge: {variant_id}")

        terminal_direction = fsm_rows[0]["terminal_direction"]
        if terminal_direction not in ("LONG", "SHORT"):
            raise VariantContractError(
                f"unexpected terminal_direction: {terminal_direction}"
            )

        return cls(
            variant_id=variant_id,
            terminal_direction=terminal_direction,
            edges=edges,
            location_arm_edge_id=location_arm.edge_id,
            ordered_advance_edge_ids=advance_ids,
            terminal_edge_id=terminal.edge_id,
            invalidate_edge_id=invalidate.edge_id,
            expire_edge_id=expire.edge_id,
            armed_from_state=location_arm.from_state,
            location_state=location_arm.to_state,
        )


def _read_variant_rows(path: Path, key: str, variant_id: str) -> list[dict[str, str]]:
    if not path.is_file():
        raise VariantContractError(f"canonical CSV missing: {path.name}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if row.get(key) == variant_id]


def _binding_predicate_classes(
    path: Path, variant_id: str
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for row in _read_variant_rows(path, "variant_id", variant_id):
        classes = tuple(
            c for c in (row.get("predicate_classes") or "").split() if c
        )
        result[row["binding_id"]] = classes
    return result


def _single(
    edges: Mapping[str, ContractEdge], edge_type: str, variant_id: str
) -> ContractEdge:
    matches = [edge for edge in edges.values() if edge.edge_type == edge_type]
    if len(matches) != 1:
        raise VariantContractError(
            f"expected exactly one {edge_type} edge for {variant_id}, "
            f"found {len(matches)}"
        )
    return matches[0]
