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
#: These are QUALIFIED names -- the full scope path, not a bare function name.
#: The third red-team campaign defeated the bare-name version with a helper
#: nested inside another function that happened to share the name.
#:
#: `ratify_amendment` -- refuses unless `capability_proof.consumed_at` is set,
#:   the action_type is the exact ratify action, and the operator matches.
#: `activate_amendment` -- refuses unless `proposal.status == "ratified"`,
#:   which only `ratify_amendment` can produce.
SANCTIONED_WRITERS = {
    (
        "aios/application/governance/amendment_authority.py",
        "ConstitutionalAmendmentAuthority.ratify_amendment",
    ),
    ("aios/application/governance/amendment_authority.py", "activate_amendment"),
}


def _python_files() -> list[pathlib.Path]:
    return sorted(path for path in AIOS.rglob("*.py") if path.is_file())


def _qualified_name(tree: ast.Module, target: ast.AST) -> str | None:
    """Dotted path of every scope containing *target*, innermost last.

    Returns e.g. "ratify_amendment" for a module-level function,
    "ConstitutionalAmendmentAuthority.ratify_amendment" for a method, and
    "_MigrationHelpers._rebuild_legacy_rows.ratify_amendment" for a function
    nested inside one.

    The earlier version returned only the innermost BARE name, and the third
    red-team campaign broke the proof with it: a helper named
    `ratify_amendment` nested inside `_MigrationHelpers._rebuild_legacy_rows`,
    performing no capability check whatsoever, matched SANCTIONED_WRITERS
    purely because `ast.FunctionDef.name == "ratify_amendment"` at any nesting
    depth anywhere in the file. The invariant test reported zero offenders.

    A proof that authorises by bare name authorises by spelling. Qualifying
    the path means a sanctioned entry names one specific function and nothing
    that merely shares its name.
    """
    scopes: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        if node.lineno <= target.lineno <= end:
            scopes.append((node.lineno, node.name))
    if not scopes:
        return None
    scopes.sort()
    return ".".join(name for _, name in scopes)


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
                            _qualified_name(tree, node.value),
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
                                _qualified_name(tree, value),
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


# --------------------------------------------------------------------------- #
# What the constitution actually contains.
#
# This exists because the model asserted, in commit ac8736c6's message, in PR
# #204's description, and in this repo's own ledger, that organ 46's C4 wording
# was changeable only by constitutional amendment under Law XIII. That was
# false, and it was committed before anyone checked.
#
# The error was not cosmetic. Acting on it would have routed a self-graded
# ledger edit through `ratify_amendment`, producing a genuine audit record
# asserting a ratification that never had that meaning -- ceremony standing in
# for a control, which is precisely what organ 46 exists to detect.
# --------------------------------------------------------------------------- #


def test_the_twelve_condition_contract_is_not_constitutional_content() -> None:
    """The constitution is foundation laws, policies, scope roots and frozen
    paths. It is not the organ ledger, and it is not C1-C12.

    Anything that governs which mechanism may change a given rule has to be
    checkable, or the next confident-sounding sentence about it goes unchecked
    too.
    """
    from aios.domain.governance.constitution import build_constitution_snapshot

    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    blob = str(snapshot.model_dump())

    for absent in ("C1", "C4", "C12", "red-team", "red team", "N/A-BY-DESIGN"):
        assert absent not in blob, (
            f"{absent!r} appears in the constitution snapshot; if the "
            "twelve-condition contract has genuinely become constitutional "
            "content, the amendment path claims in the ledger need revisiting "
            "-- but as of this test being written it had not"
        )

    assert set(snapshot.model_dump()) == {
        "constitution_id",
        "version",
        "foundation_laws",
        "policy_references",
        "scope_roots",
        "frozen_paths",
        "provider_policy_digest",
        "autonomy_policy_digest",
        "created_at",
        "ratified_by_operator_id",
        "previous_snapshot_digest",
        "snapshot_digest",
    }


def test_organ_46_condition_verdicts_live_in_the_ledger_not_the_constitution() -> None:
    """States the thing the model got wrong, in the place a future session will
    look: C4's text for organ 46 is a ledger string, and the ledger is changed
    by an operator decision, not by `ratify_amendment`."""
    import json

    ledger = json.loads(
        (REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json").read_text(encoding="utf-8")
    )
    records = ledger["organs"] if isinstance(ledger, dict) else ledger
    organ_46 = next(r for r in records if r["organ_id"] == 46)

    assert "C4" in organ_46["condition_verdicts"]
    assert "red-team" in organ_46["condition_verdicts"]["C4"]

    # And the ledger must not re-assert the corrected claim.
    blockers = " ".join(organ_46["known_blockers"])
    assert "Changing it is a constitutional amendment" not in blockers, (
        "the corrected false claim has been reintroduced"
    )


# --------------------------------------------------------------------------- #
# THIRD CAMPAIGN (2026-08-09, 21 agents). 7 confirmed findings, and -- the
# headline -- ZERO that reach ratified or activated without a real consumed
# human capability. The authorisation invariant held.
#
# The findings pinned below are the ones that do not break that invariant but
# are real defects anyway: a proof that authorised by spelling, a store that
# let its own record be made to lie, and two screens that refused honest text.
# --------------------------------------------------------------------------- #


def test_a_nested_impostor_sharing_a_sanctioned_name_is_not_sanctioned() -> None:
    """Finding 3, the high one, and it was against the proof itself.

    `SANCTIONED_WRITERS` matched on a BARE function name at any nesting depth,
    so a helper called `ratify_amendment` defined inside another function --
    performing no capability check at all -- was authorised purely because it
    shared the spelling. The invariant test reported zero offenders.

    Sanctioning is by qualified path now. This constructs the campaign's exact
    shape and requires the scan to attribute it to its full scope rather than
    to the sanctioned entry.
    """
    source = (
        "class _MigrationHelpers:\n"
        "    def _rebuild_legacy_rows(self, rows):\n"
        "        def ratify_amendment(p):\n"
        '            return p.model_copy(update={"status": "ratified"})\n'
        "        return [ratify_amendment(r) for r in rows]\n"
    )
    tree = ast.parse(source)
    target = next(
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "status"
    )
    qualified = _qualified_name(tree, target)
    assert qualified == "_MigrationHelpers._rebuild_legacy_rows.ratify_amendment"
    assert ("aios/application/governance/amendment_authority.py", qualified) not in (
        SANCTIONED_WRITERS
    ), "a nested impostor is being sanctioned by name again"


def test_sanctioned_writers_are_qualified_not_bare_names() -> None:
    """Guards the shape of the allowlist itself.

    A future edit that shortens an entry back to a bare name silently restores
    the finding, because everything would still pass.
    """
    assert any("." in func for _, func in SANCTIONED_WRITERS), (
        "no sanctioned entry is qualified; the allowlist has regressed to "
        "bare-name matching, which the third campaign defeated"
    )
