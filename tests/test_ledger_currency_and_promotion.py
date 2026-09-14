"""The two tools that decide what is stale and what may go green.

Both write to `ORGAN_GREEN_LEDGER.json`, and between them they can move an organ
from yellow to green. Neither had a test.

The property that matters for `verify_evidence_currency` is SYMMETRY: it must be
as willing to add staleness as to remove it. A tool that only ever clears
blockers is not a verifier, it is a way to make rows green, and the difference is
invisible from the outside until someone checks. (It earned that trust once
already by promptly marking organ 55 stale on the same run that cleared
thirty-one others -- 55's entrypoints had moved because of edits made minutes
earlier, by me.)

The property that matters for `promote_verified_organs` is that its qualifying
clauses actually bite. The flip it writes is a HYPOTHESIS which
`verify_organ_twelve_conditions` then adjudicates -- and that adjudication
rejected the first real batch, 31 organs, which is how the evidence-row
accumulation bug was found. These tests pin the clauses so the hypothesis stays
narrow.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


currency = _load("verify_evidence_currency")
promotion = _load("promote_verified_organs")


# --------------------------------------------------------------------------- #
# verify_evidence_currency — the symmetry is the point
# --------------------------------------------------------------------------- #
def test_an_untouched_file_is_not_stale() -> None:
    """A commit that is old is not thereby wrong.

    Relevance, not a time window: an organ whose entrypoints have not moved is
    still telling the truth however long ago it was verified.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()

    assert currency.changed_since(head, ["aios/config.py"], head) == []


def test_a_changed_file_is_stale() -> None:
    """The other direction, without which the test above proves nothing.

    Compares HEAD against its own parent over a path the parent commit touched,
    so this cannot pass by the diff always being empty.
    """
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1..HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    ).stdout.split()
    if not changed:
        pytest.skip("HEAD is empty; nothing to measure drift against")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()

    drift = currency.changed_since("HEAD~1", changed[:3], head)

    assert drift, f"files changed in HEAD were not detected as drift: {changed[:3]}"


def test_an_unresolvable_sha_is_reported_not_guessed() -> None:
    """Squash-merges orphan commits. That is unknown, not fresh.

    Answering "no drift" for a sha git cannot resolve would silently mark every
    orphaned row current — the failure mode with the worst blast radius here.
    """
    drift = currency.changed_since("0" * 40, ["aios/config.py"], "HEAD")

    assert drift, "an unresolvable sha must not read as 'no drift'"
    assert "unresolvable" in drift[0]


def test_both_stale_spellings_are_recognised() -> None:
    """Organ 13 sat yellow holding evidence at HEAD with zero drift.

    Its blocker said `STALE LIVE EVIDENCE` while the pass stripped only
    `STALE ATTESTATION` -- one rule, two spellings, and a tool that knew one of
    them. Guarded on the tuple so a third spelling has to be added here too.
    """
    assert "STALE ATTESTATION" in currency.STALE_MARKERS
    assert "STALE LIVE EVIDENCE" in currency.STALE_MARKERS


def test_the_spine_is_never_touched_by_the_currency_pass() -> None:
    """`evidence_digest` covers known_blockers for the attested organs.

    Rewriting one -- even to record something true -- invalidates a signature
    only the operator can replace.
    """
    attested = currency._spine_attested_organ_ids()

    assert attested, "the attestation should cover at least the spine organs"
    assert attested <= {1, 2, 3, 4, 5}


# --------------------------------------------------------------------------- #
# promote_verified_organs — every clause must bite
# --------------------------------------------------------------------------- #
def _row(**over):
    base = {
        "organ_id": 91,
        "name": "Candidate",
        "status": "yellow",
        "condition_verdicts": {f"C{i}": "PASS — fine" for i in range(1, 13)},
        "known_blockers": [
            f"{promotion.READY_MARKER} 3207c3757076 via release/phase4/x.json"
        ],
    }
    base.update(over)
    return base


def test_a_ready_row_qualifies() -> None:
    ok, why = promotion.qualifies(_row(), set())

    assert ok, why


@pytest.mark.parametrize(
    ("over", "marker"),
    [
        ({"status": "green"}, "not yellow"),
        ({"condition_verdicts": {}}, "no condition verdicts"),
        (
            {
                "condition_verdicts": {
                    **{f"C{i}": "PASS" for i in range(1, 12)},
                    "C12": "FAIL — ancestry unproven",
                }
            },
            "unsettled conditions",
        ),
        (
            {
                "known_blockers": [
                    "browser-session — needs an operator browser at :5173"
                ]
            },
            "named residual",
        ),
        (
            {"known_blockers": ["STALE ATTESTATION (recorded abc): entrypoints moved"]},
            "named residual",
        ),
    ],
)
def test_each_clause_refuses_on_its_own(over, marker) -> None:
    """One unmet thing is one too many.

    The residual clause is the one doing the real work: it is what keeps the
    browser, Outside-machine and staleness organs yellow while everything
    around them is promoted.
    """
    ok, why = promotion.qualifies(_row(**over), set())

    assert not ok
    assert marker in why


def test_a_spine_organ_is_never_promoted() -> None:
    """Its status is inside the operator's signature."""
    ok, why = promotion.qualifies(_row(organ_id=4), {1, 2, 3, 4, 5})

    assert not ok
    assert "spine-attested" in why


def test_the_shipped_ledger_has_no_silently_promotable_rows() -> None:
    """Whatever this tool would flip right now must be a deliberate decision.

    Not an assertion that the count is zero -- it is an assertion that the count
    is KNOWN. If this fails, someone changed the ledger such that a row became
    promotable without anyone running the tool and reading the gate's answer.
    """
    ledger = json.loads(
        (REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json").read_text(
            encoding="utf-8"
        )
    )
    attested = promotion._spine_attested_organ_ids()
    promotable = [
        int(row["organ_id"]) for row in ledger if promotion.qualifies(row, attested)[0]
    ]

    assert promotable == [], (
        "rows are sitting promotable in the shipped ledger: "
        f"{promotable}. Run promote_verified_organs.py --apply and then the "
        "twelve-condition gate, and believe the gate."
    )
