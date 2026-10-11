"""Measured model quality, as a calibration prior for the router.

The router ranks models by a heuristic over their names (catalog.py) and then
calibrates with measured success rates per ``(provider, model, task)``
(router._calibrated_score). Until 2026-10-11 the only measured source was live
verified turns, which on this machine were too few to calibrate anything -- so
"best" meant "best-sounding name", unchecked.

First measurement (2026-10-11, 50 tasks, release/intelligence/): the heuristic's
top picks held up -- Qwen3-Coder-480B for coding (25/25), Kimi K2-thinking for
reasoning (24/25; it is weak at coding, 15/25, and slow), Mistral Large 3 for
general work (50/50, fastest). What the prior changes is the rest of the order:
a model measured weak at a task is demoted for it. (An earlier note here said
K2-thinking was the weakest model for reasoning; that read its OVERALL score.
On reasoning alone it is near the top.)

This module serves the operator's own benchmark results
(tools/intelligence_benchmark.py, on HIS account and machine) as a prior:

* ``aios/core/benchmark_rates.json`` is produced by
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

RATES_PATH = Path(__file__).resolve().parent / "benchmark_rates.json"


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
