#!/usr/bin/env python3
"""The operator's own attestation: declare a human observation as evidence.

WHY THIS IS A SEPARATE TOOL AND WHY AN AGENT MUST NOT RUN IT
------------------------------------------------------------
C10 accepts four kinds of referent: a ``release/phase4`` artifact, a
``tests/foo.py::test_bar`` node that ran and passed in the gate run, an
``actions/runs/<id>`` CI run, or an explicitly declared ``OPERATOR-ATTESTED``
human observation.

The first three a machine can check. The fourth is a person saying *I looked at
this and it is so* -- and the gate's own note is that it "must be DECLARED rather
than inferred, otherwise it is indistinguishable from prose". An agent writing
``OPERATOR-ATTESTED`` about evidence it produced itself would be signing its own
homework, which is the entire failure mode the word exists to prevent.

So this tool refuses to run without the operator saying so in their own words,
and it prints the full evidence first so the declaration is made against
something read, not something assumed.

USAGE
-----
    python scripts/operator_attest.py                       # show candidates
    python scripts/operator_attest.py --show 20             # read one in full
    python scripts/operator_attest.py --attest 20 48 --i-am-the-operator "Swapnil" --observed "I opened the UI at :5173 and saw all three states myself"

ONE LINE, no continuations. This is written for PowerShell as well as bash: the
first version of this docstring used bash trailing backslashes, the operator
pasted it into PowerShell, and got `invalid int value: '\\'` followed by three
more parse errors. A tool whose entire job is to be run by a human must hand
that human a command their shell can read.

Run it with no arguments first: it lists exactly which organs it will accept,
fills their ids into a ready command for the shell you are actually in, and
refuses to guess. Organ 55 is deliberately NOT among them -- its C10 is blocked
on Outside-machine, which no signature can supply.

After writing, it regenerates the doc and then the manifest (that order --
the manifest hash-pins the doc), and tells you the two gates to run.

WHAT IT WILL NOT DO
-------------------
* attest an organ whose only unsettled condition is NOT C10 -- a signature is
  not a substitute for a condition that has not been met;
* attest an organ with no live evidence to attest TO;
* touch a spine-attested organ (1-5), whose status is covered by the Ed25519
  signature and can only change by re-signing;
* invent the words. ``--observed`` is recorded verbatim as the operator's own.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
ATTESTATION_PATH = REPO_ROOT / ".aios" / "state" / "spine_release_attestation.json"

MARKER = "OPERATOR-ATTESTED"
SETTLED = ("PASS", "N/A", "MET")


def _spine_attested() -> set[int]:
    try:
        data = json.loads(ATTESTATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {int(x) for x in (data.get("organ_ids") or [])}


def _unsettled(row: dict) -> list[str]:
    verdicts = row.get("condition_verdicts") or {}
    return sorted(
        (k for k, v in verdicts.items() if not str(v).startswith(SETTLED)),
        key=lambda k: int(k[1:]),
    )


def eligibility(row: dict, spine: set[int]) -> tuple[bool, str]:
    """Can this organ be attested, and if not, why not."""
    oid = int(row["organ_id"])
    if oid in spine:
        return False, "spine-attested; its status is covered by the Ed25519 signature"
    if row.get("status") == "green":
        return False, "already green"
    live = [
        e for e in (row.get("live_evidence") or []) if e.get("proof_level") == "live"
    ]
    if not live:
        return False, "no live evidence to attest to"
    if any(MARKER in str(e.get("description", "")) for e in live):
        return False, "already carries an operator attestation"
    unsettled = _unsettled(row)
    if not unsettled:
        return False, "nothing unsettled to attest"
    verdicts = row.get("condition_verdicts") or {}

    # NOTHING OPEN MAY NAME A THING A SIGNATURE CANNOT SUPPLY.
    #
    # Checked BEFORE the C10-alone shortcut, because that shortcut used to
    # return True without ever reading why C10 was unsettled. Dropping
    # "outside-machine" from `_WAITS_ON` fixed only the multi-condition path;
    # an organ blocked at C10 alone on outside-machine sailed straight through.
    # One bug, two doors, and the second was found by the test written for the
    # first.
    #
    # The rule is about WHAT IS MISSING, not who is asking: a person can declare
    # what they observed, and cannot declare that a second machine ran the
    # cohort, that Docker was up, or that a model was served.
    for key in unsettled:
        lowered = str(verdicts.get(key, "")).lower()
        named = [phrase for phrase in _NOT_A_SIGNATURE if phrase in lowered]
        if named:
            return False, (
                f"{key} is blocked on {named[0]!r}, which a human declaration "
                "cannot supply — that needs the thing itself, not a signature"
            )

    # C10 ALONE is the ordinary case: a human observation answering the one
    # condition a machine cannot check.
    if unsettled == ["C10"]:
        return True, ""

    # ORGAN 55 IS THE OTHER SHAPE, and it is legitimate rather than an
    # exception carved out to reach a number. Its C11 says in its own words:
    # "the sha stays null because pinning it is part of the operator
    # attestation this organ is still waiting on", and C12 says "Follows from
    # C11". C9's sole remaining blocker IS the attestation. So every open
    # condition names this same act as the thing it waits for.
    #
    # The check is on the TEXT, not on a hardcoded organ id: a condition may
    # only be resolved this way if it says so itself. A verdict that is
    # unsettled for some other reason still blocks, which is what keeps this
    # from becoming a skeleton key.
    unexplained = [
        key
        for key in unsettled
        # C10 is the condition an attestation exists to answer, so it does not
        # also have to announce that it is waiting for one. Every OTHER open
        # condition does -- that is what stops this becoming a skeleton key.
        if key != "C10" and not _waits_on_attestation(str(verdicts.get(key, "")))
    ]
    if unexplained:
        return False, (
            f"unsettled conditions are {unsettled}, and {unexplained} do not say "
            "they are waiting on an operator attestation — an attestation answers "
            "only what names it; the rest is real work"
        )
    return True, ""


#: Things a human declaration CANNOT supply, however sincerely given.
#:
#: An operator can say "I observed this". They cannot say a second machine ran
#: the cohort, that a Docker daemon was up, or that a model was served. A
#: condition naming one of these needs the thing itself.
_NOT_A_SIGNATURE = (
    "outside-machine",
    "no docker",
    "no ollama",
    "phase 6 gate",
    "frozen spine",
)


#: Phrases by which a verdict declares the OPERATOR ATTESTATION is its blocker.
#:
#: "outside-machine" WAS in this list and had to come out. It does not mean
#: "waiting for the operator to sign" -- it means evidence from a machine that
#: is not this one. Those are different requirements, and conflating them made
#: this tool willing to flip organ 55 green on a signature given on the very
#: laptop that produced its evidence. That is the self-certification the whole
#: ledger is built to refuse, and it would have been laundered by a helper
#: written to be convenient.
#:
#: A phrase belongs here only if the thing it names IS a human declaration.
_WAITS_ON = (
    "operator attestation",
    "operator-attestation",
    "follows from c11",
)


def _waits_on_attestation(text: str) -> bool:
    """Does this verdict say, in its own words, that it waits on the operator?"""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _WAITS_ON)


#: The twelve-condition gate, as ONE line.
#:
#: Defined once and printed, never retyped. Both places this tool emitted a
#: command originally used bash trailing backslashes; the usage hint was fixed
#: and THIS one was missed, so the operator hit the identical PowerShell parse
#: errors a second time on the very next command. Two copies of a string is two
#: chances to fix only one of them.
_GATE_COMMAND = (
    "python scripts/verify_organ_twelve_conditions.py "
    "--frontend-junit frontend/vitest-junit.xml "
    "--extra-junit release/organ-33-37/clerk-junit-2026-09-14.xml"
)


def _shell_name() -> str:
    """Which shell the operator is most likely pasting into."""
    return "PowerShell" if os.name == "nt" else "bash"


def _attest_example(ids: list[int]) -> str:
    """A command that can actually be pasted, on THIS platform.

    Printed as ONE line with no continuations. The first version emitted
    bash-style trailing backslashes, which the operator pasted into PowerShell
    and got `invalid int value: '\'` followed by three more parse errors --
    a tool whose whole job is to be run by a human, handing that human a command
    their shell cannot read.
    """
    wanted = " ".join(str(i) for i in ids) if ids else "<ids>"
    return (
        f"python scripts/operator_attest.py --attest {wanted} "
        '--i-am-the-operator "Your Name" '
        '--observed "what you actually observed, in your own words"'
    )


def show(row: dict, full: bool = False) -> None:
    oid = int(row["organ_id"])
    print(f"\n─── organ {oid}: {row['name']} ───")
    print(f"    status            {row.get('status')}")
    print(f"    unsettled         {_unsettled(row) or '[]'}")
    for blocker in row.get("known_blockers") or []:
        text = str(blocker)
        print(
            f"    blocker           {text if full else text[:150] + ('…' if len(text) > 150 else '')}"
        )
    for entry in row.get("live_evidence") or []:
        if entry.get("proof_level") != "live":
            continue
        desc = str(entry.get("description", ""))
        print(f"\n    EVIDENCE @ {str(entry.get('commit_sha'))[:12]}")
        print(
            f"    {desc if full else desc[:600] + ('…  (--show for all)' if len(desc) > 600 else '')}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show",
        nargs="*",
        type=int,
        metavar="ID",
        help="print candidates (or the given organs) in full",
    )
    parser.add_argument(
        "--attest", nargs="+", type=int, metavar="ID", help="organ ids to attest"
    )
    parser.add_argument(
        "--i-am-the-operator",
        dest="operator",
        metavar="NAME",
        help="your name — required, and recorded",
    )
    parser.add_argument(
        "--observed",
        metavar="TEXT",
        help="what YOU observed, in your words — recorded verbatim",
    )
    args = parser.parse_args(argv)

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    spine = _spine_attested()
    by_id = {int(r["organ_id"]): r for r in ledger}

    if not args.attest:
        wanted = args.show if args.show else None
        print(
            "Organs awaiting an operator attestation (C10 is their only open condition):"
        )
        any_found = False
        eligible_ids: list[int] = []
        for row in ledger:
            oid = int(row["organ_id"])
            if wanted and oid not in wanted:
                continue
            ok, why = eligibility(row, spine)
            if ok:
                any_found = True
                eligible_ids.append(oid)
                show(row, full=bool(args.show))
            elif wanted:
                print(f"\n─── organ {oid}: {row['name']} ───\n    NOT ELIGIBLE: {why}")
        if not any_found and not wanted:
            print("  (none)")
        print(
            "\nTo attest, read the evidence above and then run "
            f"({_shell_name()} — ONE line, no continuations):\n\n"
            f"  {_attest_example(eligible_ids)}\n\n"
            "  Replace the --observed text with what YOU saw; it is recorded "
            "verbatim as your words."
        )
        return 0

    if not args.operator or not args.observed:
        print(
            "refusing: --attest requires BOTH --i-am-the-operator and --observed.\n"
            "This is a human declaration; it does not get made on someone's behalf.",
            file=sys.stderr,
        )
        return 2
    if len(args.observed.strip()) < 15:
        print(
            "refusing: --observed is too short to be an observation. Say what you "
            "saw; it is recorded verbatim and read by whoever audits this next.",
            file=sys.stderr,
        )
        return 2

    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()

    attested: list[int] = []
    for oid in args.attest:
        row = by_id.get(oid)
        if row is None:
            print(f"organ {oid}: not in the ledger", file=sys.stderr)
            return 1
        ok, why = eligibility(row, spine)
        if not ok:
            print(f"organ {oid}: REFUSED — {why}", file=sys.stderr)
            return 1

        declaration = (
            f"{MARKER} by {args.operator} at {stamp} (tip {head[:12]}): "
            f'"{args.observed.strip()}" — declared against the live evidence '
            "recorded on this organ, which the operator read before declaring."
        )
        live = [
            e
            for e in (row.get("live_evidence") or [])
            if e.get("proof_level") == "live"
        ]
        live[-1]["description"] = (
            str(live[-1].get("description", "")) + " || " + declaration
        )[:2000]

        verdicts = dict(row.get("condition_verdicts") or {})
        verdicts["C10"] = (
            f"PASS — {MARKER}. {args.operator} declared on {stamp}: "
            f'"{args.observed.strip()}". This is a HUMAN OBSERVATION, which is '
            "what C10's fourth referent is for; it is not a machine re-check and "
            "does not claim to be."
        )

        # PINNING THE SHA IS PART OF THE ATTESTATION, not a step before it.
        # Organ 55's own C11 says so: "the sha stays null because pinning it is
        # part of the operator attestation this organ is still waiting on". An
        # agent setting it in advance would perform the operator's act and leave
        # only a rubber stamp -- so it happens here, by this command, at the
        # moment the operator runs it.
        if not row.get("last_verified_sha"):
            row["last_verified_sha"] = head
            verdicts["C11"] = (
                f"PASS — last_verified_sha={head}, pinned by {args.operator} as "
                f"part of the {MARKER} declaration on {stamp}. It was null until "
                "now precisely because pinning it is the operator's act."
            )
            verdicts["C12"] = (
                f"PASS — {head[:12]} must be an ancestor of HEAD (ordinary CI "
                "--require-sha-ancestry); exact tip match is --strict-release at "
                "the tagged evidence tip. Follows from C11, now that C11 holds."
            )

        # Any OTHER condition that named the attestation as its blocker is
        # answered by the same act -- and only those. The prior text is kept
        # inline rather than overwritten: a reader auditing this later needs to
        # see what the condition said before a human resolved it.
        for key in list(verdicts):
            if key in ("C10", "C11", "C12"):
                continue
            current = str(verdicts[key])
            if not current.startswith(SETTLED) and _waits_on_attestation(current):
                verdicts[key] = (
                    f"PASS — the residual this condition named was the operator "
                    f"attestation, declared by {args.operator} on {stamp}. Prior "
                    f"text retained: || {current}"
                )[:2000]

        row["condition_verdicts"] = verdicts
        row["known_blockers"] = [
            b
            for b in (row.get("known_blockers") or [])
            if "operator-attestation" not in str(b)
            and "Operator attestation" not in str(b)
        ]
        row["status"] = "green"
        attested.append(oid)
        print(f"organ {oid}: attested by {args.operator}")

    LEDGER_PATH.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nattested: {attested}")
    print(
        "regenerating the generated artifacts (doc BEFORE manifest — the manifest hash-pins the doc) …"
    )
    for script in ("build_organ_ledger_doc.py", "build_release_manifest.py"):
        result = subprocess.run(
            [sys.executable, f"scripts/{script}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        print(f"  {script}: rc={result.returncode}")
        if result.returncode != 0:
            print(result.stderr[-800:], file=sys.stderr)
            return 1
    print(
        f"\nNow prove it, and believe the gates over this script ({_shell_name()}, "
        "one line each):\n\n"
        "  python scripts/verify_organ_contracts.py\n\n"
        "  " + _GATE_COMMAND + "\n\n"
        "The second runs 122 test files and takes roughly twenty minutes.\n"
        "Both must exit 0 and report `green mechanical failures: 0`. If either\n"
        "objects, the attestation was premature — revert it rather than argue."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
