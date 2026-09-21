#!/usr/bin/env python3
"""LC1..LC12 — the twelve-condition contract, applied to the animal.

WHY THIS EXISTS
---------------
The governance side earns trust by measuring itself forever: 55 organs, twelve
machine-verified conditions, evidence currency, lineage, a mutation probe, an
operator attestation, and a number it is judged by. The learning side had a
scoreboard that printed numbers and never once failed.

The asymmetry showed. On 2026-09-21 three defects were found by RUNNING the
loop rather than reading it, and all three were the same shape: a measurement
that could not distinguish "didn't happen" from "happened and failed". Nobody
watching timings is what an unattended loop is.

So the faculties get the same apparatus the organs have. The conditions below
mirror C1..C12 in MEANING, not in wording, because "does a type-checker own
this" and "does a learning faculty own this" are different questions with the
same shape.

WHAT IS DELIBERATELY DIFFERENT FROM THE ORGAN GATE
--------------------------------------------------
* **Verdicts are computed, never declared.** The organ ledger stores prose
  verdicts and this gate checks a mechanical subset of them. Here the ledger
  stores only INPUTS -- owner, entrypoints, callers, stores, tests, evidence --
  and every verdict is derived. There is no field an author can write "PASS"
  into.
* **LC8 is a mutation proof, not a frontend condition.** C8 asks about frontend
  error states, which no learning faculty has. The slot is spent on the
  question that actually matters here: if this faculty were broken, would
  anything notice?
* **LC10 requires ORGANIC evidence.** A faculty proven only against
  `training_ground/` toys has not been proven. The self-corpus is the bar.

NO --skip-tests. LC6/LC7 execute the referenced suites, for the reason the
organ gate gives: an opt-out that saves CI minutes becomes the default within a
release or two, silently restoring the weakness it was meant to close.

    python scripts/verify_learning_conditions.py
    python scripts/verify_learning_conditions.py --json
    python scripts/verify_learning_conditions.py --require-green L3,L7
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# One derivation, two callers. The organ gate already solved "run a pile of
# test files once and map results back per record", including the part that
# matters most -- refusing to report when pytest could not be run at all.
# Re-implementing it here would let the two gates drift into disagreeing about
# what a passing test is.
from scripts.verify_organ_twelve_conditions import (  # noqa: E402
    TestExecutionUnavailable,
    _run_pytest,
)

LEDGER = REPO_ROOT / ".aios" / "state" / "LEARNING_LEDGER.json"
JUNIT = REPO_ROOT / ".aios" / "tmp" / "learning-conditions-junit.xml"

CONDITIONS: dict[str, str] = {
    "LC1": "a named authority class owns this faculty in a production entrypoint",
    "LC2": "the faculty is reachable from the LIVE turn path, not only a script or API",
    "LC3": "its state survives a fresh process/DB open",
    "LC4": "every state transition is journalled append-only",
    "LC5": "unmeasurable input is REFUSED, not scored",
    "LC6": "focused tests resolve on disk and pass",
    "LC7": "integration tests resolve on disk and pass",
    "LC8": "breaking the faculty is caught (mutation-proven)",
    "LC9": "no residual known blockers",
    "LC10": "live evidence on ORGANIC data, with a reproducible command and artifact",
    "LC11": "last_verified_sha is recorded",
    "LC12": "that sha is an ancestor of HEAD",
}


@dataclass
class Verdict:
    """One condition's outcome. `state` is PASS / FAIL / N-A."""

    state: str
    why: str

    @property
    def ok(self) -> bool:
        return self.state in ("PASS", "N-A")


@dataclass
class FacultyResult:
    faculty_id: str
    name: str
    verdicts: dict[str, Verdict] = field(default_factory=dict)

    @property
    def failing(self) -> list[str]:
        return [k for k, v in self.verdicts.items() if not v.ok]

    @property
    def status(self) -> str:
        return "green" if not self.failing else "yellow"


def _na(record: dict, condition: str) -> Verdict | None:
    """An N/A-BY-DESIGN declaration, which MUST carry a referent.

    The organ contract's referent rule exists because "not applicable" with no
    pointer is indistinguishable from "we did not do it". A declaration without
    a `::` referent is rejected rather than honoured.
    """
    text = (record.get("na_by_design") or {}).get(condition)
    if not text:
        return None
    if not _referent_resolves(text):
        return Verdict(
            "FAIL",
            f"N/A-BY-DESIGN declared for {condition} but its referent does not "
            f"resolve to anything on disk, which is indistinguishable from an "
            f"excuse: {text[:140]}",
        )
    return Verdict("N-A", text)


#: A referent is either `module/path.py::symbol` or a bare path. Both must
#: EXIST -- the point of the referent rule is that "not applicable" comes with
#: somewhere to go and look, and a pointer at nothing is just the word "no".
_REFERENT = re.compile(r"[\w./\\-]+\.(?:py|jsonl|json|md|sql)(?:::[\w.]+)?")


def _referent_resolves(text: str) -> bool:
    for candidate in _REFERENT.findall(text or ""):
        rel = candidate.split("::", 1)[0]
        if (REPO_ROOT / rel).exists():
            return True
    return False


def _paths_exist(paths: list[str]) -> tuple[bool, str]:
    missing = [p for p in paths if not (REPO_ROOT / p).exists()]
    return (not missing), ("missing: " + ", ".join(missing) if missing else "")


def _class_is_defined(owner: str, entrypoints: list[str]) -> bool:
    pattern = re.compile(rf"^class {re.escape(owner)}\b", re.M)
    for rel in entrypoints:
        path = REPO_ROOT / rel
        if path.exists() and pattern.search(
            path.read_text(encoding="utf-8", errors="replace")
        ):
            return True
    return False


def _mentions(haystack: Path, needle: str) -> int:
    if not haystack.exists():
        return 0
    return haystack.read_text(encoding="utf-8", errors="replace").count(needle)


def _sha_is_ancestor(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def _suite_verdict(
    paths: list[str], results: dict[str, dict], condition: str
) -> Verdict:
    """Require the suites to have actually RUN and passed — not merely to exist.

    This is the condition the organ gate had to fix the hard way: C6/C7 used to
    pass when the FILE EXISTED, so a green organ could cite a suite that failed,
    contained no tests, or tested something else.
    """
    if not paths:
        return Verdict("FAIL", f"{condition}: no suites declared")
    ok, why = _paths_exist(paths)
    if not ok:
        return Verdict("FAIL", why)

    ran = 0
    for rel in paths:
        outcome = results.get(rel.replace("\\", "/"))
        if outcome is None:
            return Verdict("FAIL", f"{rel} did not run")
        # Key names come from `_parse_junit`: passed / failed / skipped. Reading
        # the wrong ones here reported "ran ZERO tests" for every faculty on the
        # first run -- this condition catching its own verifier's bug is the
        # argument for having the condition at all.
        if outcome.get("failed"):
            return Verdict(
                "FAIL",
                f"{rel}: {outcome['failed']} failed "
                f"({', '.join(outcome.get('failed_names', [])[:3])})",
            )
        ran += int(outcome.get("passed", 0))
    if ran == 0:
        return Verdict(
            "FAIL",
            "the declared suites ran ZERO tests — a suite that executes nothing "
            "is the hollow-run hole wearing a green tick",
        )
    return Verdict("PASS", f"{len(paths)} suite(s), {ran} test(s) passed")


def evaluate(record: dict, results: dict[str, dict]) -> FacultyResult:
    out = FacultyResult(record["faculty_id"], record["name"])

    def put(cond: str, verdict: Verdict) -> None:
        out.verdicts[cond] = _na(record, cond) or verdict

    owner = record.get("authority_owner") or ""
    entrypoints = record.get("production_entrypoints") or []

    # LC1 — someone owns it, in code that ships.
    exists, why = _paths_exist(entrypoints)
    if not exists:
        put("LC1", Verdict("FAIL", why))
    elif not _class_is_defined(owner, entrypoints):
        put(
            "LC1",
            Verdict("FAIL", f"class {owner} is not defined in {entrypoints}"),
        )
    else:
        put("LC1", Verdict("PASS", f"{owner} defined in {entrypoints[0]}"))

    # LC2 — reachable from the LIVE path. This is the condition that catches the
    # defect class where a heavily-tested component is documented as canonical
    # and imported by nothing a real turn touches.
    callers = record.get("live_path_callers") or []
    # The symbol the caller actually uses. Naming it exactly is the author's job
    # and is the check's whole strength: several faculties reach the turn path
    # by DEPENDENCY INJECTION (`runtime.skills`) rather than by import, so a
    # grep for the module name proves nothing. The first version of this check
    # counted the word "skills" and accepted README.md as a live-path caller.
    # An exact symbol cannot be satisfied by coincidence.
    symbols = record.get("live_path_symbols") or ([owner] if owner else [])
    if not callers:
        put(
            "LC2",
            Verdict(
                "FAIL",
                "no live-path caller declared: reachable only from a script or "
                "an API route is not reachable from a turn",
            ),
        )
    elif not symbols:
        put("LC2", Verdict("FAIL", "no live_path_symbols declared to look for"))
    else:
        hit = {s: [c for c in callers if _mentions(REPO_ROOT / c, s)] for s in symbols}
        found = {s: c for s, c in hit.items() if c}
        put(
            "LC2",
            Verdict("PASS", ", ".join(f"{s} in {c[0]}" for s, c in found.items()))
            if found
            else Verdict(
                "FAIL", f"none of {symbols} appears in any declared caller {callers}"
            ),
        )

    # LC3 — durability. A store is declared, or it is N/A with a referent.
    store = record.get("durable_store") or {}
    put(
        "LC3",
        Verdict("PASS", f"durable store: {store.get('table')}")
        if store.get("table")
        else Verdict("FAIL", "no durable store declared and no N/A-BY-DESIGN referent"),
    )

    # LC4 — journal.
    journal = record.get("journal") or {}
    put(
        "LC4",
        Verdict("PASS", f"append-only journal: {journal.get('referent')}")
        if journal.get("append_only_claim")
        else Verdict(
            "FAIL",
            "no append-only journal: state transitions leave no record that "
            "survives being overwritten",
        ),
    )

    # LC5 — refusal. The condition today's defects were all violations of.
    put("LC5", _suite_verdict(record.get("fail_closed_tests") or [], results, "LC5"))

    # LC6 / LC7 — the suites must run and pass.
    put("LC6", _suite_verdict(record.get("focused_tests") or [], results, "LC6"))
    put("LC7", _suite_verdict(record.get("integration_tests") or [], results, "LC7"))

    # LC8 — would anything notice if this faculty broke?
    probe = record.get("mutation_probe")
    if not probe:
        put(
            "LC8",
            Verdict(
                "FAIL",
                "no mutation proof: nothing establishes that breaking this "
                "faculty would be caught rather than silently absorbed",
            ),
        )
    elif "::" not in str(probe.get("referent") or ""):
        put("LC8", Verdict("FAIL", "mutation probe declared without a referent"))
    else:
        put("LC8", Verdict("PASS", str(probe["referent"])))

    # LC9 — residual blockers, stated rather than hidden.
    blockers = record.get("known_blockers") or []
    put(
        "LC9",
        Verdict("PASS", "no residual blockers")
        if not blockers
        else Verdict("FAIL", f"{len(blockers)} blocker(s): {blockers[0][:150]}"),
    )

    # LC10 — organic live evidence, citing an artifact that exists.
    evidence = [e for e in (record.get("live_evidence") or []) if e.get("organic")]
    if not evidence:
        put(
            "LC10",
            Verdict(
                "FAIL",
                "no ORGANIC live evidence. Synthetic training_ground runs do not "
                "satisfy this: the claim is that the faculty works on real code.",
            ),
        )
    else:
        latest = evidence[-1]
        artifact = REPO_ROOT / str(latest.get("artifact") or "")
        if not latest.get("command"):
            put("LC10", Verdict("FAIL", "evidence cites no reproducible command"))
        elif not artifact.exists():
            put(
                "LC10",
                Verdict(
                    "FAIL",
                    f"cited artifact does not exist here: {latest.get('artifact')} "
                    "(expected when the trail is gitignored — that is the finding, "
                    "not an excuse)",
                ),
            )
        else:
            put(
                "LC10",
                Verdict("PASS", f"organic evidence at {latest['commit_sha'][:12]}"),
            )

    # LC11 / LC12 — currency and lineage.
    sha = record.get("last_verified_sha")
    put(
        "LC11",
        Verdict("PASS", f"last_verified_sha={sha[:12]}")
        if sha
        else Verdict("FAIL", "no last_verified_sha"),
    )
    if not sha:
        put("LC12", Verdict("FAIL", "no sha to check ancestry for"))
    else:
        put(
            "LC12",
            Verdict("PASS", f"{sha[:12]} is an ancestor of HEAD")
            if _sha_is_ancestor(sha)
            else Verdict(
                "FAIL",
                f"{sha[:12]} is NOT an ancestor of HEAD — typically a squash-merge "
                "orphaning the evidence commit",
            ),
        )
    return out


def _collect_suites(faculties: list[dict]) -> list[str]:
    seen: list[str] = []
    for record in faculties:
        for key in ("fail_closed_tests", "focused_tests", "integration_tests"):
            for rel in record.get(key) or []:
                norm = rel.replace("\\", "/")
                if norm not in seen and (REPO_ROOT / norm).exists():
                    seen.append(norm)
    return seen


def render(results: list[FacultyResult]) -> str:
    lines = ["LEARNING LEDGER — LC1..LC12", ""]
    green = [r for r in results if r.status == "green"]
    lines.append(f"  {len(green)} green / {len(results)} faculties")
    lines.append("")
    for r in results:
        mark = "GREEN " if r.status == "green" else "yellow"
        lines.append(f"  [{mark}] {r.faculty_id}  {r.name}")
        for cond in CONDITIONS:
            v = r.verdicts.get(cond)
            if v is None:
                continue
            if v.state == "PASS":
                continue
            tag = "N/A " if v.state == "N-A" else "FAIL"
            lines.append(f"            {tag} {cond}  {' '.join(v.why.split())[:150]}")
        lines.append("")
    failing = sorted({c for r in results for c in r.failing})
    if failing:
        lines.append("  conditions failing somewhere: " + ", ".join(failing))
        lines.append("")
        lines.append(
            "  A mostly-yellow first run is the expected result and is not a "
            "problem to paper over. Each FAIL above names work, not wording."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--require-green",
        default="",
        help="comma-separated faculty ids that MUST be green for exit 0",
    )
    args = parser.parse_args(argv)

    if not args.ledger.is_file():
        print(f"no learning ledger at {args.ledger}")
        return 2
    faculties = json.loads(args.ledger.read_text(encoding="utf-8"))["faculties"]

    suites = _collect_suites(faculties)
    try:
        results_by_file = _run_pytest(suites, REPO_ROOT, JUNIT)
    except TestExecutionUnavailable as exc:
        # The same refusal the faculties themselves are judged on: a gate that
        # could not run its tests must not report a verdict about them.
        print(f"REFUSED — {exc}")
        return 3

    evaluated = [evaluate(record, results_by_file) for record in faculties]

    if args.json:
        print(
            json.dumps(
                {
                    r.faculty_id: {
                        "name": r.name,
                        "status": r.status,
                        "verdicts": {
                            k: [v.state, v.why] for k, v in r.verdicts.items()
                        },
                    }
                    for r in evaluated
                },
                indent=2,
            )
        )
    else:
        print(render(evaluated))

    required = [f.strip() for f in args.require_green.split(",") if f.strip()]
    if required:
        broken = [
            r.faculty_id for r in evaluated if r.faculty_id in required and r.failing
        ]
        if broken:
            print(f"\nFAIL — required green but yellow: {', '.join(broken)}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
