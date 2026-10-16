"""What may leave the machine for a cloud model: ONE derivation.

Operator decision, 2026-10-11 ("one law"): the **constitution is the ceiling**.
The runtime profile the operator switches (aios/runtime/profiles.json) may only
NARROW what the constitution allows, never widen it:

* cloud tasks   = constitution's  ∩  profile's
* prefer local  = constitution's  OR profile's   (local-first wins)
* max cost      = the stricter of the two

Found by the sovereignty drills (H6): chat routing obeyed the profile alone,
while the constitution -- `AIOS_ROUTER_CLOUD_TASKS`, the documented opt-in --
was obeyed by nothing live. A persisted profile switch could open cloud egress
the constitution never allowed. Every caller now asks this function.
"""

from __future__ import annotations

from typing import Any

from aios.core import router

#: Cheapest first. An unknown value counts as the strictest -- fail closed.
_COST_RANK = {router.COST_FREE: 0, router.COST_LOW: 1, router.COST_HIGH: 2}


def stricter_cost(first: str, second: str) -> str:
    """The stricter of two cost ceilings; an unknown one is treated as free."""
    rank_a = _COST_RANK.get(str(first).strip().lower(), 0)
    rank_b = _COST_RANK.get(str(second).strip().lower(), 0)
    chosen = min(rank_a, rank_b)
    return next(name for name, rank in _COST_RANK.items() if rank == chosen)


def effective_router_policy(constitution: Any, profile: Any | None) -> router.Policy:
    """The routing policy in force: the constitution, narrowed by *profile*.

    With no profile (a caller that has none), the constitution alone."""
    law_tasks = frozenset(t.strip().lower() for t in constitution.router_cloud_tasks)
    if profile is None:
        return router.Policy(
            cloud_tasks=law_tasks,
            max_cost=stricter_cost(
                constitution.router_max_cost, constitution.router_max_cost
            ),
            prefer_local=bool(constitution.router_prefer_local),
        )
    profile_tasks = frozenset(t.strip().lower() for t in profile.router_cloud_tasks)
    return router.Policy(
        cloud_tasks=law_tasks & profile_tasks,
        max_cost=stricter_cost(constitution.router_max_cost, profile.router_max_cost),
        prefer_local=bool(
            constitution.router_prefer_local or profile.router_prefer_local
        ),
    )


__all__ = ["effective_router_policy", "stricter_cost"]
