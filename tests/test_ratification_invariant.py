"""Organ 46's real invariant, proven exhaustively rather than by example.

Why this file exists
--------------------
Two adversarial campaigns (2026-08-08 and 2026-08-09, 49 agents) produced 24
confirmed bypasses of organ 46's textual screening. The realised impact of all
24 was identical: a false passing badge on the advisory `check-simulations`
report. Not one of them moved a proposal a single step toward activation.

That is not luck, and it should not be re-established by anecdote after every
campaign. The property that actually holds is structural:

    No machine-authored lesson can become an activated constitutional change
    without a real, already-consumed capability bound to a human operator.

The screening layer cannot be proven sound -- keyword screening over prose is
evadable by paraphrase, and two campaigns demonstrated it. This invariant CAN
be proven, and it is what organ 46's green claim should rest on.

How it is proven
----------------
By enumeration over the AST, not by calling the happy path. A test that
exercises the known-good route proves the known-good route works; it says
nothing about the route somebody adds next month. These tests instead find
*every* assignment of a ratifying status anywhere under `aios/` and require
each one to sit behind the capability gate.

A new unguarded path fails here at the moment it is written, which is the only
time the cost of fixing it is low.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AIOS = REPO_ROOT / "aios"

#: Statuses that mean "this amendment now has force". Reaching either without
#: a consumed human capability would be the failure this organ exists to
#: prevent.
RATIFYING_STATUSES = frozenset({"ratified", "activated"})

#: The two functions permitted to write those statuses, and why each is safe.
#:
#: `ratify_amendment` -- refuses unless `capability_proof.consumed_at` is set,
#:   the action_type is the exact ratify action, and the operator matches.
#: `activate_amendment` -- refuses unless `proposal.status == "ratified"`,
#:   which only `ratify_amendment` can produce.
SANCTIONED_WRITERS = {
    ("aios/application/governance/amendment_authority.py", "ratify_amendment"),
    ("aios/application/governance/amendment_authority.py", "activate_amendment"),
}


def _python_files() -> list[pathlib.Path]:
    return sorted(path for path in AIOS.rglob("*.py") if path.is_file())


def _enclosing_function(tree: ast.Module, target: ast.AST) -> str | None:
    """Name of the innermost function containing *target*, or None."""
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        if node.lineno <= target.lineno <= end:
            depth = node.lineno
            if best is None or depth > best[0]:
                best = (depth, node.name)
    return best[1] if best else None


def _status_writes() -> list[tuple[str, str | None, int, str]]:
    """Every place under aios/ that binds a ratifying status to `status`.

    Covers both spellings the codebase uses: a `status="activated"` keyword
    argument, and a `{"status": "ratified"}` entry in a `model_copy(update=...)`
    dict. Both are how a proposal's status is actually set here.
    """
    found: list[tuple[str, str | None, int, str]] = []
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - repo must parse
            pytest.fail(f"{rel} does not parse")

        for node in ast.walk(tree):
            # status="ratified" as a call keyword
            if isinstance(node, ast.keyword) and node.arg == "status":
                if (
                    isinstance(node.value, ast.Constant)
                    and node.value.value in RATIFYING_STATUSES
                ):
                    found.append(
                        (
                            rel,
                            _enclosing_function(tree, node.value),
                            node.value.lineno,
                            node.value.value,
                        )
                    )
            # {"status": "ratified"} inside an update dict
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "status"
                        and isinstance(value, ast.Constant)
                        and value.value in RATIFYING_STATUSES
                    ):
                        found.append(
                            (
                                rel,
                                _enclosing_function(tree, value),
                                value.lineno,
                                value.value,
                            )
                        )
    return found


def test_the_enumeration_actually_finds_something() -> None:
    """Guard against the whole file passing vacuously.

    If a refactor renames the status field or changes how it is written, every
    assertion below would pass by finding nothing at all. That failure mode is
    silent and total, so it gets its own test.
    """
    writes = _status_writes()
    assert writes, "found no ratifying status writes -- the AST scan is broken"
    sanctioned = {
        (rel, func) for rel, func, _, _ in writes if (rel, func) in SANCTIONED_WRITERS
    }
    assert sanctioned == SANCTIONED_WRITERS, (
        "the scan no longer sees the known-good writers, so it cannot be "
        f"trusted to see new ones; saw {sorted(sanctioned)}"
    )


def test_only_sanctioned_functions_can_write_a_ratifying_status() -> None:
    """The invariant itself.

    Any new code path that marks an amendment ratified or activated fails here
    the moment it is written. If a genuinely-needed writer is added, it must be
    added to SANCTIONED_WRITERS deliberately, with the reasoning that makes it
    safe -- which is the point: the decision becomes explicit and reviewable
    instead of implicit and invisible.
    """
    offenders = [
        f"{rel}::{func or '<module>'}:{line} sets status={value!r}"
        for rel, func, line, value in _status_writes()
        if (rel, func) not in SANCTIONED_WRITERS
        # The organ's own adversarial probe builds a synthetic ACTIVATED
        # proposal in memory to exercise rollback. It is never persisted and
        # never leaves the function; excluded by name rather than by pattern so
        # a second such exemption cannot appear silently.
        and (rel, func)
        != (
            "aios/application/governance/adversarial_simulations.py",
            "_probe_rollback_lifecycle",
        )
        # Unrelated domain: skills activation has nothing to do with the
        # constitution and shares only the English word.
        and rel != "aios/api/routes/skills.py"
    ]
    assert offenders == [], (
        "unsanctioned code can mark a constitutional amendment ratified or "
        f"activated: {offenders}"
    )


def test_ratify_amendment_refuses_every_capability_defect() -> None:
    """The gate the enumeration above funnels everything into.

    Enumerating writers is only worth something if the sanctioned writer is
    itself sound, so each refusal is exercised separately rather than trusting
    one happy-path assertion.
    """
    from types import SimpleNamespace

    from aios.application.governance.amendment_authority import (
        AmendmentError,
        propose_amendment,
        ratify_amendment,
    )
    from aios.domain.governance.amendments import (
        CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
    )

    proposal = propose_amendment(
        proposal_id="invariant-1",
        target_articles=("router_max_cost policy",),
        proposed_diff="raise router_max_cost for the batch task class",
        motivation="unblock a legitimate high-cost task class",
        migration_plan="no migration required",
        rollback_plan="revert router_max_cost",
        proposed_by="model:test",
        proposer_type="model",
    )

    def capability(**overrides: object) -> SimpleNamespace:
        fields: dict[str, object] = dict(
            action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
            operator_id="operator:abc",
            consumed_at=1234567890.0,
            token_digest="d" * 64,
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    defects = {
        "no capability at all": None,
        "never consumed": capability(consumed_at=None),
        "wrong action type": capability(action_type="some:other:action"),
        "different operator": capability(operator_id="operator:someone-else"),
    }
    for label, proof in defects.items():
        with pytest.raises(AmendmentError):
            ratify_amendment(
                proposal, capability_proof=proof, operator_id="operator:abc"
            )
            pytest.fail(f"ratified with {label}")


def test_activation_requires_a_ratified_predecessor() -> None:
    """The second sanctioned writer is safe only because of this check -- a
    proposal cannot be activated straight from `proposed`, so the capability
    gate cannot be stepped around by skipping ratification."""
    from aios.application.governance.amendment_authority import (
        AmendmentError,
        activate_amendment,
        propose_amendment,
    )
    from aios.domain.governance.constitution import build_constitution_snapshot

    proposal = propose_amendment(
        proposal_id="invariant-2",
        target_articles=("router_max_cost policy",),
        proposed_diff="raise router_max_cost",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="model:test",
        proposer_type="model",
    )
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    for status in ("proposed", "critiqued", "simulated", "rejected"):
        with pytest.raises(AmendmentError):
            activate_amendment(
                proposal.model_copy(update={"status": status}),
                previous_snapshot=snapshot,
            )


def test_the_screening_layer_is_not_on_the_ratification_path() -> None:
    """States the separation the campaigns kept re-proving by accident.

    `ratify_amendment` must not consult the adversarial simulations, the
    learning organ, or any text screen. If it ever did, every screening bypass
    would become an authority bypass, and the 24 confirmed findings from the
    two campaigns would have been catastrophic instead of merely misleading.
    """
    source = (
        REPO_ROOT / "aios/application/governance/amendment_authority.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    ratify = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "ratify_amendment"
    )
    called = {
        node.func.id
        if isinstance(node.func, ast.Name)
        else getattr(node.func, "attr", "")
        for node in ast.walk(ratify)
        if isinstance(node, ast.Call)
    }
    forbidden = {
        "run_adversarial_simulations",
        "screen_proposal",
        "require_all_simulations_pass",
        "assert_never_reduces_human_authority",
    }
    assert not (called & forbidden), (
        "ratification consults the evadable screening layer: "
        f"{sorted(called & forbidden)}"
    )


# --------------------------------------------------------------------------- #
# The typed approval declaration. The architectural answer to what two
# campaigns established: prose cannot decide who ratifies, so it no longer does.
# --------------------------------------------------------------------------- #


def test_the_approval_model_vocabulary_has_exactly_one_member_in_v1() -> None:
    """Pins the closed vocabulary itself.

    Widening it is the change that would matter, and it must be deliberate --
    a schema edit somebody reviews, not a value a proposal can carry in. This
    test failing is not a bug; it is the review trigger firing.
    """
    import typing

    from aios.domain.governance.amendments import ConstitutionalAmendmentProposalV1

    annotation = ConstitutionalAmendmentProposalV1.model_fields[
        "approval_model"
    ].annotation
    assert typing.get_args(annotation) == ("human_capability_required",), (
        "the approval-model vocabulary changed; widening it moves 'who "
        "ratifies' back into reach of something other than a human"
    )


@pytest.mark.parametrize(
    "attempted",
    [
        "timeout_auto_ratification",
        "objection_window",
        "delegate_approver",
        "risk_tier_auto_activate",
        "human_capability_optional",
        "",
    ],
)
def test_a_proposal_cannot_declare_any_other_approval_model(attempted: str) -> None:
    """Each of these is a *semantic* attack the campaigns confirmed against the
    prose screens -- consent-by-silence, objection windows, delegate identity,
    risk tiering. As prose they were bypasses. As data they do not typecheck.

    This is the difference the architecture buys: there is no paraphrase of an
    invalid enum member.
    """
    from pydantic import ValidationError

    from aios.domain.governance.amendments import ConstitutionalAmendmentProposalV1

    with pytest.raises(ValidationError):
        ConstitutionalAmendmentProposalV1(
            proposal_id="typed-1",
            target_articles=("some policy",),
            proposed_diff="a change",
            motivation="m",
            migration_plan="m",
            rollback_plan="r",
            proposed_by="model:test",
            proposer_type="model",
            approval_model=attempted,  # type: ignore[arg-type]
        )


def test_prose_describing_another_approval_model_does_not_change_the_field() -> None:
    """The point of moving this out of prose, stated as a test.

    A proposal may *say* anything -- this diff describes timeout ratification
    in plain English, which no marker list can be trusted to catch forever. The
    runtime does not care, because it reads `approval_model`, and that still
    says a human capability is required.
    """
    from aios.application.governance.amendment_authority import propose_amendment

    proposal = propose_amendment(
        proposal_id="typed-2",
        target_articles=("Article IX",),
        proposed_diff=(
            "Ratification shall be deemed complete where the reviewing "
            "operator has not responded within seventy-two hours."
        ),
        motivation="reduce latency",
        migration_plan="none",
        rollback_plan="revert",
        proposed_by="model:test",
        proposer_type="model",
    )
    assert proposal.approval_model == "human_capability_required"


def test_the_approval_model_cannot_be_mutated_after_construction() -> None:
    """`frozen=True` is what stops the field being edited between screening and
    ratification -- otherwise the type would be a suggestion."""
    from pydantic import ValidationError

    from aios.application.governance.amendment_authority import propose_amendment

    proposal = propose_amendment(
        proposal_id="typed-3",
        target_articles=("Article IX",),
        proposed_diff="a change",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="model:test",
        proposer_type="model",
    )
    with pytest.raises(ValidationError):
        proposal.approval_model = "timeout_auto_ratification"  # type: ignore[misc]
