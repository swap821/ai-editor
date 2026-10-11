"""Measured model quality, as a calibration prior for the router.

The router ranks models by a heuristic over their names (catalog.py) and then
calibrates with measured success rates per ``(provider, model, task)``
(router._calibrated_score). Until 2026-10-11 the only measured source was live
verified turns, which on this machine were too few to calibrate anything -- so
"best" meant "best-sounding name". The heuristic put Kimi K2-thinking first for
reasoning; measured, it was the weakest cloud model of eleven.

This module serves the operator's own benchmark results
(tools/intelligence_benchmark.py, on HIS account and machine) as a prior:

* ``aios/core/data/benchmark_rates.json`` is produced by
  ``python tools/intelligence_benchmark.py --emit-rates ...`` and committed;
* live verified evidence OVERRIDES a benchmark rate for the same
  ``(provider, model, task)`` -- real work outranks a test;
* errored calls never count; a model needs enough answered tasks to be rated.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RATES_PATH = Path(__file__).resolve().parent / "data" / "benchmark_rates.json"


@lru_cache(maxsize=1)
def _load(path: str) -> dict[tuple[str, str, str], float]:
    try:
        data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rates: dict[tuple[str, str, str], float] = {}
    for row in data.get("rates") or []:
        try:
            key = (str(row["provider"]), str(row["model"]), str(row["task"]))
            rates[key] = max(0.0, min(1.0, float(row["rate"])))
        except (KeyError, TypeError, ValueError):
            continue
    return rates


def benchmark_rates(path: Path | None = None) -> dict[tuple[str, str, str], float]:
    """``(provider, model, task) -> measured success rate`` from the benchmark."""
    return dict(_load(str(path or RATES_PATH)))


def merged_rates(
    live: dict[tuple[str, str, str], float], path: Path | None = None
) -> dict[tuple[str, str, str], float]:
    """The benchmark prior, with live verified evidence overriding it."""
    rates = benchmark_rates(path)
    rates.update(live or {})
    return rates


__all__ = ["RATES_PATH", "benchmark_rates", "merged_rates"]
