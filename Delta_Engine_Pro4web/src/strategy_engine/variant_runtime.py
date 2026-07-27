"""Read-only runtime view of the representative variant.

Reuses ``src.strategy_contract.variant_contract.VariantContract`` for the FSM
edge structure and additionally reads each edge's ``predicate_id`` from the
canonical binding CSV (read-only) so the Predicate Evaluator can be keyed per
edge. Nothing here writes to the canon.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.strategy_contract.variant_contract import (
    _CANON_DIR,
    ContractEdge,
    VariantContract,
)

# The representative variant used by the Replay contract golden path
# (judgement contract 4 example).
REPRESENTATIVE_VARIANT_ID = (
    "VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001"
)

_BINDINGS_CSV = "ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv"


@dataclass(frozen=True)
class EdgeSpec:
    edge_id: str
    edge_type: str
    predicate_id: str
    predicate_classes: tuple[str, ...]
    hard_source_required: bool


@dataclass(frozen=True)
class RepresentativeVariant:
    contract: VariantContract
    edge_specs: Mapping[str, EdgeSpec]

    @classmethod
    def load(
        cls,
        variant_id: str = REPRESENTATIVE_VARIANT_ID,
        *,
        canon_dir: Path | None = None,
    ) -> "RepresentativeVariant":
        base = canon_dir or _CANON_DIR
        contract = VariantContract.load(variant_id, canon_dir=base)
        predicate_ids = _binding_predicate_ids(base / _BINDINGS_CSV, variant_id)
        specs: dict[str, EdgeSpec] = {}
        for edge_id, edge in contract.edges.items():
            specs[edge_id] = _edge_spec(edge, predicate_ids.get(edge_id, ""))
        return cls(contract=contract, edge_specs=specs)

    def spec(self, edge_id: str) -> EdgeSpec | None:
        return self.edge_specs.get(edge_id)

    def predicate_ids(self) -> tuple[str, ...]:
        return tuple(sorted({s.predicate_id for s in self.edge_specs.values() if s.predicate_id}))


def _edge_spec(edge: ContractEdge, predicate_id: str) -> EdgeSpec:
    return EdgeSpec(
        edge_id=edge.edge_id,
        edge_type=edge.edge_type,
        predicate_id=predicate_id,
        predicate_classes=edge.predicate_classes,
        hard_source_required=edge.hard_source_required,
    )


def _binding_predicate_ids(path: Path, variant_id: str) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"canonical binding CSV missing: {path.name}")
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("variant_id") != variant_id:
                continue
            result[row["binding_id"]] = row.get("predicate_id", "")
    return result
