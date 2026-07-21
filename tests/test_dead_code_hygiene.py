"""Regression guards for confirmed dead-code removals."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

REMOVED_PRODUCT_DEAD_CODE = (
    "aios/agents/swarm_adaptive.py",
    "aios/agents/swarm_conflict.py",
    "aios/agents/swarm_parallel.py",
    "aios/agents/swarm_scout.py",
    "aios/policy/policy_evolution.py",
    "aios/runtime/leases.py",
    # 2026-07-02: zero importers (K1 import graph) AND 0% coverage — the two
    # instruments agreed; operator-approved deletion.
    "aios/council/service_definitions.py",
)


def test_confirmed_orphaned_modules_stay_out_of_product_package() -> None:
    present = [rel for rel in REMOVED_PRODUCT_DEAD_CODE if (PROJECT_ROOT / rel).exists()]

    assert not present, (
        "Confirmed orphaned modules must not quietly re-enter the product package. "
        "Wire and test the feature, or keep it outside aios/: "
        + ", ".join(present)
    )
