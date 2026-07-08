"""Resource ecology primitives for runtime budget decisions."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ResourceMode = Literal["normal", "conservation", "hibernation"]


@dataclass(frozen=True)
class ResourceSnapshot:
    mode: ResourceMode
    cloud_calls: int
    estimated_cost: float
    worker_count: int
    cpu_pressure: float | None
    memory_pressure: float | None
    cloud_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "cloud_calls": self.cloud_calls,
            "estimated_cost": self.estimated_cost,
            "worker_count": self.worker_count,
            "cpu_pressure": self.cpu_pressure,
            "memory_pressure": self.memory_pressure,
            "cloud_allowed": self.cloud_allowed,
            "reason": self.reason,
        }


def normalize_resource_mode(raw: str) -> ResourceMode:
    value = raw.strip().lower()
    if value in {"normal", "conservation", "hibernation"}:
        return value  # type: ignore[return-value]
    return "conservation"


def cpu_pressure() -> float | None:
    """Best-effort CPU pressure in [0, 1]; unavailable platforms return None."""

    getloadavg = getattr(os, "getloadavg", None)
    if getloadavg is None:
        return None
    try:
        load1, _, _ = getloadavg()
        cpus = os.cpu_count() or 1
        return max(0.0, min(1.0, float(load1) / float(cpus)))
    except OSError:
        return None


def memory_pressure() -> float | None:
    """Best-effort memory pressure.

    The standard library has no portable total-memory API. Return None rather
    than inventing a value; callers can still display that it is unavailable.
    """

    return None


__all__ = [
    "ResourceMode",
    "ResourceSnapshot",
    "cpu_pressure",
    "memory_pressure",
    "normalize_resource_mode",
]
