#!/usr/bin/env python3
"""Show which model the fleet WOULD pick for each task — without calling anything.

WHY THIS EXISTS
---------------
"Many cloud models, each on the work it was designed for" is the goal, and
until now the only way to check whether it actually happens was to enable cloud
routing and watch. That is backwards: turning on egress to find out whether the
routing is sane means the first real test is also the first real exposure.

This resolves the decision without making it. It builds the same
:class:`~aios.core.router.Provider` rows the live wiring builds, applies the
same policy and the same ranking, and prints the winner per task class. No
model is called, no request leaves the machine, and the process is read-only.

THE GATE IS NOT TOUCHED
-----------------------
``ROUTER_CLOUD_TASKS`` lives in the frozen core and is the operator's decision.
By default it is empty, so the honest preview is "local only, for every task" —
and that is what this will print. Pass ``--as-if`` to see what the fleet WOULD
do under a hypothetical policy; it changes this preview's arithmetic and
nothing else, and the output says so on every line.

    python tools/route_preview.py
    python tools/route_preview.py --as-if coding,reasoning,research,vision,long_context
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios.core import router  # noqa: E402
from aios.core.catalog import model_kind, task_affinity  # noqa: E402
from aios.core.model_selector import TASKS  # noqa: E402
from aios.security.limits import ROUTER_CLOUD_TASKS, _VALID_ROUTER_TASKS  # noqa: E402


def _live_providers() -> list[router.Provider]:
    """The provider rows the live wiring would build, or none if clients are absent.

    Imported lazily and failure-softly: this is a preview tool, and a machine
    with no cloud credentials should still be able to see its local routing
    rather than crash on an import it does not need.
    """
    try:
        from aios.api import deps
        from aios.core.router_wiring import _build_providers
    except Exception as exc:  # noqa: BLE001 - a preview must not require a live stack
        print(f"(could not load the live wiring: {exc})")
        return []
    try:
        return _build_providers(
            deps.get_ollama_client(),
            deps.get_bedrock_client(),
            deps.get_gemini_client(),
            openai=deps.get_openai_client(),
            anthropic=deps.get_anthropic_client(),
            vertex_maas=deps.get_vertex_maas_client(),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"(provider discovery failed: {exc})")
        return []


def _profile_cloud_tasks() -> tuple[str, ...] | None:
    """The active runtime profile's cloud tasks, or None if unreadable."""
    try:
        from aios.api.deps import get_policy_kernel

        return tuple(get_policy_kernel().active_runtime_profile().router_cloud_tasks)
    except Exception:  # noqa: BLE001 - a preview must not require a live stack
        return None


def _effective_cloud_tasks() -> tuple[str, ...]:
    """What the ROUTER will actually treat as cloud-eligible."""
    profile_tasks = _profile_cloud_tasks()
    return tuple(ROUTER_CLOUD_TASKS) if profile_tasks is None else profile_tasks


def _warn_if_the_two_gates_disagree() -> None:
    """Report a split between the two independent statements of cloud eligibility.

    There are two, and they are enforced by different code:

    * the active RUNTIME PROFILE (`profile.router_cloud_tasks`) decides which
      tasks the ROUTER will rank a cloud provider for;
    * ``AIOS_ROUTER_CLOUD_TASKS`` (`config.ROUTER_CLOUD_TASKS`) is what
      ``build_constitution`` hands the ``ConstitutionEnforcer``, which BLOCKS a
      cloud request whose task is not listed.

    Switching to the ``operator`` profile without also setting the env var
    therefore produces a half-enabled state: the router picks a cloud model and
    the constitution refuses the call. It fails closed, which is the right
    direction, but silently — the operator sees "cloud is on" in one place and
    local answers in practice.

    Collapsing the two into one source is a governance decision, not a cleanup,
    because a mismatch currently fails CLOSED and a single source would remove
    that second lock. So this reports rather than resolves.
    """
    profile = _profile_cloud_tasks()
    if profile is None:
        return
    profile_tasks = set(profile)
    env_tasks = set(ROUTER_CLOUD_TASKS)
    if profile_tasks == env_tasks:
        return
    print("WARNING: the two cloud gates disagree.")
    print(f"  runtime profile allows : {sorted(profile_tasks) or '(none)'}")
    print(f"  AIOS_ROUTER_CLOUD_TASKS: {sorted(env_tasks) or '(none)'}")
    print("  The router ranks cloud by the FIRST; the ConstitutionEnforcer blocks")
    print("  by the SECOND. Tasks in only one of them are routed and then refused.")
    print("  Set both to the same list.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-if",
        default=None,
        help=(
            "comma-separated task classes to treat as cloud-eligible FOR THIS "
            "PREVIEW ONLY. Does not change any configuration."
        ),
    )
    args = parser.parse_args(argv)

    hypothetical = args.as_if is not None
    if hypothetical:
        cloud_tasks = tuple(
            t.strip().lower()
            for t in args.as_if.split(",")
            if t.strip().lower() in _VALID_ROUTER_TASKS
        )
    else:
        # The ACTIVE PROFILE, not the env var. The profile is what
        # `_router_policy` hands to the ranker, so previewing the env var would
        # have shown a route the product does not take — a preview that is wrong
        # in exactly the situation it exists to diagnose. Falls back to the env
        # var only when the policy kernel cannot be reached at all.
        cloud_tasks = _effective_cloud_tasks()

    _warn_if_the_two_gates_disagree()

    providers = _live_providers()
    if not providers:
        print("no providers discovered — nothing to preview")
        return 1

    cloud = [p for p in providers if p.privacy == router.PRIVACY_CLOUD]
    local = [p for p in providers if p.privacy == router.PRIVACY_LOCAL]
    print(f"providers: {len(local)} local, {len(cloud)} cloud")
    print(
        "cloud-eligible tasks: "
        + (", ".join(cloud_tasks) if cloud_tasks else "(none — the default)")
        + ("   [HYPOTHETICAL, nothing was changed]" if hypothetical else "")
    )
    print()

    policy = router.Policy(
        cloud_tasks=cloud_tasks,
        max_cost=router.COST_HIGH,
        prefer_local=True,
    )
    for task in TASKS:
        routes = router.candidates(task, providers, policy=policy)
        if not routes:
            print(f"  {task:<14} (no eligible route)")
            continue
        best = routes[0]
        note = ""
        if best.privacy == router.PRIVACY_CLOUD:
            bonus = task_affinity(best.model, task)
            note = f"  kind={model_kind(best.model)}" + (
                f" +{bonus} affinity" if bonus else ""
            )
        runners_up = ", ".join(f"{r.provider}:{r.model}" for r in routes[1:3])
        print(f"  {task:<14} -> {best.provider}:{best.model}  [{best.privacy}]{note}")
        if runners_up:
            print(f"  {'':<14}    next: {runners_up}")

    if not hypothetical and not cloud_tasks:
        print()
        print(
            "Every task routed locally because no task class is cloud-eligible.\n"
            "That is the default and it is a deliberate one: ROUTER_CLOUD_TASKS\n"
            "lives in the frozen core because what may leave the machine is the\n"
            "operator's decision. Re-run with --as-if to see the fleet's picks\n"
            "without changing anything."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
