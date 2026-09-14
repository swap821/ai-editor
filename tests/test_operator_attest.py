"""The attestation tool must refuse everything it is not entitled to flip.

This tool writes `status: green` into the organ ledger on the strength of a
human saying so. That makes its REFUSALS the interesting part, and this file is
mostly refusals.

It exists because the tool shipped with a real defect that a hand-check caught
and nothing else would have. `_WAITS_ON` -- the list of phrases by which a
condition declares "I am waiting on the operator" -- included `outside-machine`.
That phrase does not mean "waiting for a signature"; it means evidence from a
machine that is not this one. An attestation cannot make a second machine exist.
With the phrase present, the tool would have flipped organ 55 (the organ GAGOS
is judged by) green on a signature given on the very laptop that produced its
evidence -- self-certification, laundered by a helper written to be convenient.

So the last test here is the one that matters most: outside-machine must NOT
satisfy an attestation, forever.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "operator_attest", REPO_ROOT / "scripts" / "operator_attest.py"
)
assert _spec and _spec.loader
operator_attest = importlib.util.module_from_spec(_spec)
sys.modules["operator_attest"] = operator_attest
_spec.loader.exec_module(operator_attest)

SPINE = {1, 2, 3, 4, 5}


def _row(**over):
    base = {
        "organ_id": 90,
        "name": "Test Organ",
        "status": "yellow",
        "production_entrypoints": ["aios/x.py"],
        "live_evidence": [
            {
                "description": "a real probe",
                "commit_sha": "a" * 40,
                "proof_level": "live",
            }
        ],
        "known_blockers": [],
        "condition_verdicts": {f"C{i}": "PASS — fine" for i in range(1, 13)},
    }
    base.update(over)
    return base


def _verdicts(**over):
    verdicts = {f"C{i}": "PASS — fine" for i in range(1, 13)}
    verdicts.update(over)
    return verdicts


# --------------------------------------------------------------------------- #
# The ordinary case
# --------------------------------------------------------------------------- #
def test_c10_alone_is_attestable() -> None:
    """A human observation answering the one condition a machine cannot check."""
    row = _row(condition_verdicts=_verdicts(C10="NOT MET - needs a human look"))

    ok, why = operator_attest.eligibility(row, SPINE)

    assert ok, why


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #
def test_a_spine_organ_is_never_attestable() -> None:
    """Their status is covered by the Ed25519 signature and changes by re-signing."""
    row = _row(organ_id=3, condition_verdicts=_verdicts(C10="NOT MET"))

    ok, why = operator_attest.eligibility(row, SPINE)

    assert not ok
    assert "spine-attested" in why


def test_an_organ_with_no_live_evidence_is_refused() -> None:
    """There must be something to attest TO. A signature is not evidence."""
    row = _row(live_evidence=[], condition_verdicts=_verdicts(C10="NOT MET"))

    ok, why = operator_attest.eligibility(row, SPINE)

    assert not ok
    assert "no live evidence" in why


def test_an_already_attested_organ_is_refused() -> None:
    """Two signatures on one row is not twice the evidence."""
    row = _row(
        live_evidence=[
            {
                "description": f"probe || {operator_attest.MARKER} by someone",
                "commit_sha": "a" * 40,
                "proof_level": "live",
            }
        ],
        condition_verdicts=_verdicts(C10="NOT MET"),
    )

    ok, why = operator_attest.eligibility(row, SPINE)

    assert not ok
    assert "already carries" in why


def test_a_condition_that_is_not_about_the_operator_still_blocks() -> None:
    """An attestation answers what names it. The rest is real work.

    A signature must not be able to stand in for a Docker proof that was never
    run, however sincerely it is given.
    """
    row = _row(
        condition_verdicts=_verdicts(
            C9="NOT MET - no Docker: the daemon is unavailable on this host",
            C10="NOT MET - needs a human look",
        )
    )

    ok, why = operator_attest.eligibility(row, SPINE)

    assert not ok
    assert "C9" in why


def test_conditions_that_name_the_attestation_are_attestable_together() -> None:
    """Organ 55's shape: every open condition says it waits on this same act.

    C11 says the sha is null "because pinning it is part of the operator
    attestation this organ is still waiting on"; C12 "Follows from C11".
    """
    row = _row(
        condition_verdicts=_verdicts(
            C9="NOT MET - one known_blocker remains: operator attestation",
            C10="NOT MET - awaiting the operator",
            C11="NOT MET - pinning it is part of the operator attestation",
            C12="NOT MET - Follows from C11",
        )
    )

    ok, why = operator_attest.eligibility(row, SPINE)

    assert ok, why


# --------------------------------------------------------------------------- #
# The defect this file exists for
# --------------------------------------------------------------------------- #
def test_outside_machine_is_not_satisfied_by_a_signature() -> None:
    """THE BUG. Outside-machine means another MACHINE, not another person.

    `_WAITS_ON` briefly listed "outside-machine", which made this tool willing
    to flip organ 55 green on a signature given on the same laptop that produced
    its evidence. An operator can declare what they observed; they cannot
    declare that a second machine ran the cohort.
    """
    assert not operator_attest._waits_on_attestation(
        "NOT MET - Outside-machine: live scores have only been produced here"
    )

    row = _row(
        condition_verdicts=_verdicts(
            C10="NOT MET - Outside-machine. Live scores HAVE been produced, but "
            "only on this machine."
        )
    )

    ok, why = operator_attest.eligibility(row, SPINE)

    assert not ok, "a signature must not discharge an outside-machine residual"
    assert "C10" in why


def test_the_phrases_that_do_qualify_all_name_a_human_act() -> None:
    """Guards the list itself, not just today's members.

    Every phrase here must describe something a PERSON does. "outside-machine"
    failed that test and was removed; anything added later has to pass it too.
    """
    for phrase in operator_attest._WAITS_ON:
        assert "machine" not in phrase, (
            f"{phrase!r} names a machine, not a human act — an attestation "
            "cannot satisfy it"
        )


# --------------------------------------------------------------------------- #
# The CLI refuses to speak for the operator
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("argv", "marker"),
    [
        (["--attest", "90"], "requires BOTH"),
        (["--attest", "90", "--i-am-the-operator", "X"], "requires BOTH"),
        (
            ["--attest", "90", "--i-am-the-operator", "X", "--observed", "ok"],
            "too short",
        ),
    ],
)
def test_the_cli_will_not_attest_on_someones_behalf(argv, marker, capsys) -> None:
    """A declaration with no declarer, or no words, is not a declaration."""
    code = operator_attest.main(argv)

    assert code == 2
    assert marker in capsys.readouterr().err


def test_no_printed_command_uses_a_shell_continuation() -> None:
    """Every command this tool prints must be one line.

    Two separate places emitted bash trailing backslashes. The usage hint was
    fixed; the post-attest block was missed, so the operator hit the identical
    PowerShell parse errors on the very next command they ran. Asserted over the
    source rather than over one call site, because the defect was that a second
    call site existed.
    """
    source = (REPO_ROOT / "scripts" / "operator_attest.py").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        # A printed line ending in a backslash-continuation, i.e. the literal
        # two characters `\` and `n` preceded by an escaped backslash.
        if '\\\n"' in line and "python " in line
    ]
    assert not offenders, (
        "these printed lines end in a shell continuation and will not paste "
        f"into PowerShell: {offenders}"
    )


def test_the_gate_command_is_defined_once() -> None:
    """One string, printed — not retyped in each place that mentions it.

    Two copies is two chances to fix only one of them, which is exactly what
    happened.
    """
    source = (REPO_ROOT / "scripts" / "operator_attest.py").read_text(encoding="utf-8")
    assert source.count("verify_organ_twelve_conditions.py ") == 1, (
        "the gate command appears more than once; define it once and print it"
    )
