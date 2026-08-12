"""Read-only loader for observation predicate class specs from the canon.

Reads ``ORDER_FLOW_OBSERVATION_PREDICATE_CLASS_REGISTRY_V0_1_20260727.csv`` and
exposes, per predicate class, the candidate condition keys (material OR routes),
contradiction keys, and selector. The real evaluator uses these to know which
condition keys a class may reference. Nothing here is written back to the canon.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.strategy_contract.variant_contract import _CANON_DIR

_CLASS_REGISTRY_CSV = "ORDER_FLOW_OBSERVATION_PREDICATE_CLASS_REGISTRY_V0_1_20260727.csv"


@dataclass(frozen=True)
class PredicateClassSpec:
    predicate_class: str
    selector: str
    candidate_keys: tuple[str, ...]
    contradiction_keys: tuple[str, ...]
    observability: str
    implementation_status: str


def load_class_specs(canon_dir: Path | None = None) -> Mapping[str, PredicateClassSpec]:
    base = canon_dir or _CANON_DIR
    path = base / _CLASS_REGISTRY_CSV
    if not path.is_file():
        raise FileNotFoundError(f"canonical class registry missing: {path.name}")
    specs: dict[str, PredicateClassSpec] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["predicate_class"]
            specs[name] = PredicateClassSpec(
                predicate_class=name,
                selector=row.get("condition_selector", ""),
                candidate_keys=_split(row.get("condition_candidate_keys")),
                contradiction_keys=_split(row.get("contradiction_condition_keys")),
                observability=row.get("observability", ""),
                implementation_status=row.get("implementation_status", ""),
            )
    return specs


def allowed_keys(
    predicate_classes: tuple[str, ...], specs: Mapping[str, PredicateClassSpec]
) -> tuple[frozenset[str], frozenset[str]]:
    """Union of candidate / contradiction keys across a predicate's classes."""
    candidates: set[str] = set()
    contradictions: set[str] = set()
    for cls in predicate_classes:
        spec = specs.get(cls)
        if spec is None:
            continue
        candidates.update(spec.candidate_keys)
        contradictions.update(spec.contradiction_keys)
    return frozenset(candidates), frozenset(contradictions)


def _split(value: str | None) -> tuple[str, ...]:
    return tuple(part for part in (value or "").split() if part)
