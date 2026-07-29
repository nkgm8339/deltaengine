"""PD3 sizing, soak, and disk-safety policy helpers; no production I/O."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sizing:
    frames: int
    elapsed_seconds: float
    bytes_written: int

    @property
    def frames_per_second(self) -> float:
        return self.frames / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0

    @property
    def bytes_per_hour(self) -> float:
        return self.bytes_written / self.elapsed_seconds * 3600 if self.elapsed_seconds > 0 else 0.0

    @property
    def bytes_per_day(self) -> float:
        return self.bytes_per_hour * 24


def project_capacity(sizing: Sizing, days: float, overhead_ratio: float = 0.0) -> int:
    if days < 0 or overhead_ratio < 0:
        raise ValueError("invalid capacity projection")
    return round(sizing.bytes_per_day * days * (1.0 + overhead_ratio))


def disk_write_decision(free_bytes: int, required_bytes: int, safety_reserve_bytes: int) -> str:
    if min(free_bytes, required_bytes, safety_reserve_bytes) < 0:
        raise ValueError("negative disk value")
    return "ALLOW" if free_bytes - required_bytes >= safety_reserve_bytes else "FAIL_CLOSED"


def validate_soak(samples: list[dict], max_errors: int = 0) -> dict:
    errors = sum(1 for sample in samples if sample.get("state") == "ERROR" or sample.get("writer_error"))
    return {"samples": len(samples), "errors": errors, "pass": errors <= max_errors}
