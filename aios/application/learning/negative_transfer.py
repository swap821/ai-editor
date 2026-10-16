"""Negative-transfer quarantine (plan Phase 6d, threat T13).

A learned item can be fully provenanced -- signed, attributed, activated by
the operator -- and simply wrong: recalling it makes turns worse. No signature
catches that; only outcomes do. This module is the named rule that decides,
from outcomes alone, when a recalled item has stopped earning its place.

The rule (plan Phase 6, "negative-transfer quarantine, with a named rule"):

* **Reflexes:** first observed harm takes the reflex out of service. A replayed
  step that ran and failed is harm; it costs one model call to fall back, and
  only the operator's re-activation brings it back. (In ``Cerebellum``.)
* **Skills and lessons:** compare the outcomes of turns that recalled the item
  with the item's own baseline, by an exact one-sided binomial test. Auto-
  quarantine only after ``NTQ_MIN_OBSERVATIONS`` outcomes AND a lower-tail
  p-value below ``NTQ_ALPHA``. Below the count, an item doing worse than its
  baseline is FLAGGED for human review instead -- so the rule neither never
  fires (a high bar with no review) nor fires on noise (a test on three
  observations).

Pure: no I/O, no clock. The callers record outcomes and act on the verdict.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from aios import config

Action = Literal["none", "review", "quarantine"]

#: The rule's name, written into every journal entry it causes, so an
#: operator reading why an item went quiet can find this module.
RULE = "negative-transfer quarantine: exact one-sided binomial vs the item's baseline"


@dataclass(frozen=True)
class TransferVerdict:
    """What the rule decided for one item, with everything it decided from."""

    action: Action
    successes: int
    attempts: int
    baseline: Optional[float]
    p_value: Optional[float]
    min_observations: int
    alpha: float
    reason: str

    def as_detail(self) -> dict[str, Any]:
        return {"rule": RULE, **asdict(self)}


def binomial_lower_tail(successes: int, attempts: int, p: float) -> float:
    """P(X <= *successes*) for X ~ Binomial(*attempts*, *p*), exactly.

    Summed in log space so it stays exact-enough for every count a learned item
    can reach, with no SciPy dependency.
    """
    if attempts < 0 or not 0 <= successes:
        raise ValueError("counts must be non-negative")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be a probability, not {p!r}")
    if successes >= attempts:
        return 1.0
    if p == 0.0:
        return 1.0
    if p == 1.0:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(successes + 1):
        log_term = (
            math.lgamma(attempts + 1)
            - math.lgamma(i + 1)
            - math.lgamma(attempts - i + 1)
            + i * log_p
            + (attempts - i) * log_q
        )
        total += math.exp(log_term)
    return min(1.0, total)


def smoothed_rate(successes: int, attempts: int) -> float:
    """Laplace's rule of succession, (s + 1) / (n + 2).

    An item's baseline is estimated from its own short history; "3 of 3" is not
    evidence of certainty, and a baseline of exactly 1.0 would quarantine on the
    first failure at the minimum count. Never 0 or 1.
    """
    if attempts < 0 or successes < 0 or successes > attempts:
        raise ValueError("need 0 <= successes <= attempts")
    return (successes + 1) / (attempts + 2)


def assess(
    successes: int,
    attempts: int,
    baseline: Optional[float],
    *,
    min_observations: Optional[int] = None,
    alpha: Optional[float] = None,
) -> TransferVerdict:
    """Decide whether recalled outcomes show negative transfer.

    *successes* of *attempts* are outcomes of turns that recalled the item;
    *baseline* is the success rate the item is held to. No baseline, no
    outcomes, or outcomes at or above the baseline: nothing to do.
    """
    floor = int(
        config.NTQ_MIN_OBSERVATIONS if min_observations is None else min_observations
    )
    level = float(config.NTQ_ALPHA if alpha is None else alpha)
    if successes < 0 or attempts < 0 or successes > attempts:
        raise ValueError("need 0 <= successes <= attempts")

    def verdict(
        action: Action, p_value: Optional[float], reason: str
    ) -> TransferVerdict:
        return TransferVerdict(
            action, successes, attempts, baseline, p_value, floor, level, reason
        )

    if baseline is None:
        return verdict("none", None, "no baseline to compare against: not assessed")
    if not 0.0 < baseline < 1.0:
        raise ValueError(
            f"a baseline must be strictly between 0 and 1, not {baseline!r}"
        )
    if attempts == 0:
        return verdict("none", None, "no outcomes yet")
    if successes / attempts >= baseline:
        return verdict("none", None, "at or above its baseline")
    if attempts < floor:
        return verdict(
            "review",
            None,
            f"below its baseline ({successes}/{attempts} vs {baseline:.2f}) on "
            f"fewer than {floor} outcomes: flagged for human review",
        )
    p_value = binomial_lower_tail(successes, attempts, baseline)
    if p_value < level:
        return verdict(
            "quarantine",
            p_value,
            f"{successes}/{attempts} vs a baseline of {baseline:.2f}: "
            f"p = {p_value:.4g} < {level}",
        )
    return verdict(
        "none",
        p_value,
        f"below its baseline but within noise (p = {p_value:.4g} >= {level})",
    )


__all__ = [
    "RULE",
    "TransferVerdict",
    "assess",
    "binomial_lower_tail",
    "smoothed_rate",
]
