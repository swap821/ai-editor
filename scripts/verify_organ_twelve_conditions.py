"""Phase 5 — mechanical adversarial re-read of the 12-condition green contract.

Checks every green organ against the enforceable subset of C1..C12 using the
ledger, on-disk paths, Decision A class attestation, live-evidence artifacts,
and SHA ancestry. Fail-closed on missing attestation.

Also writes one proof record per organ under ``release/phase5/`` (greens and
yellows). Does NOT flip Outside/frozen/Ollama/Docker/browser/organ-23 without
real evidence — those stay yellow with named failing conditions.

Exit 0 only when every currently-green organ passes the mechanical subset.

C6/C7/C9 EXECUTE THE TESTS
--------------------------
These three conditions used to be satisfied by paperwork:

* C6 ("focused tests pass") passed if the *file existed on disk*.
* C7 ("integration tests pass") passed if the *file existed on disk*.
* C9 ("adversarial / failure-path tests pass") passed if ``known_blockers``
  was empty -- which is the anti-pattern the green contract explicitly
  forbids: "never flip green because the ledger has no blocker text."

So a green organ could point at a test file that failed, contained zero
tests, or tested something else entirely, and still pass all three. Nothing
was ever executed.

They now run the referenced tests and require them to actually pass. Every
green organ's Python tests are collected into ONE deduplicated pytest run
(94 distinct files across the current greens, most shared between organs) and
results are mapped back per organ from the JUnit report.

There is deliberately no ``--skip-tests`` escape. An opt-out that saves CI
minutes becomes the default within a release or two, which would silently
restore the exact weakness this closes. The only way to avoid re-running is
``--test-results``, which requires a real JUnit report to consume.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
PHASE5_DIR = REPO_ROOT / "release" / "phase5"
EVIDENCE_GLOB = "release/phase4/live-evidence-*.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
_PASSISH = re.compile(r"\A\s*(PASS|N/A)\b", re.I)

#: A test exercises a failure path if it lives in the dedicated adversarial
#: suite, or its name uses the vocabulary this repo already writes such tests
#: in. Derived from the actual corpus (`refus` 136, `reject` 185, `_not_` 224,
#: `fails` 84, `never` 79, `blocked` 78, `cannot` 76 ...), not invented.
_ADVERSARIAL_DIR = "tests/adversarial/"
_ADVERSARIAL_NAME = re.compile(
    r"refus|reject|denie|denied|blocked|invalid|tamper|unavailable|expired"
    r"|revoked|revoke|bypass|escape|spoof|unauthor|forbidden|mismatch|stale"
    r"|never|cannot|_not_|fails|failure|refused|malformed|corrupt|replay"
    r"|out_of_order|missing|empty|too_long|oversized|conflict|409|403|422"
    # Added after the first real CI run, which flagged organ 11 as having NO
    # failure-path test while its suites contained `test_no_handler_raises`,
    # `test_chat_without_transcript_emits_error` and
    # `test_unregistered_mode_falls_back_to_conversation`. That was a gap in
    # THIS vocabulary, not in the organ: `_not_` does not match `_no_`, and
    # raise/error were simply absent. Widening moves corpus coverage from
    # 31.3% to 40.1% of test names -- still discriminating, so C9 keeps
    # meaning something rather than matching everything.
    r"|raise|error|without|unregistered|omit|fallback|falls_back|_no_"
    r"|refuse|survives|detect",
    re.I,
)


class TestExecutionUnavailable(RuntimeError):
    """Raised when the referenced tests could not be executed at all.

    Fail-closed: an unexecutable suite is never treated as a passing one.
    """


#: vitest reports a test file PATH as its classname, relative to the frontend
#: package root, while the ledger records it repo-relative.
_FRONTEND_ROOT = "frontend"
_JS_TEST_SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".mts", ".mjs")


def _classname_to_path(classname: str, root: Path) -> str | None:
    """Map a JUnit ``classname`` back to the test file that produced it.

    Two runners, two conventions:

    * pytest emits a dotted module path (``tests.test_foo``) and appends the
      class name for tests inside a class (``tests.test_foo.TestBar``). Walking
      the prefix from longest to shortest resolves both without guessing which
      trailing segments are classes.
    * vitest emits a real path (``src/workbench/Foo.test.tsx``) relative to the
      frontend package, whereas the ledger records it repo-relative
      (``frontend/src/workbench/Foo.test.tsx``). Splitting that on "." would
      produce nonsense, so it is matched as a path first.
    """
    if classname.endswith(_JS_TEST_SUFFIXES):
        direct = Path(classname)
        if (root / direct).exists():
            return direct.as_posix()
        prefixed = Path(_FRONTEND_ROOT) / classname
        if (root / prefixed).exists():
            return prefixed.as_posix()
        return None

    parts = classname.split(".")
    while parts:
        candidate = Path(*parts).with_suffix(".py")
        if (root / candidate).exists():
            return candidate.as_posix()
        parts.pop()
    return None


def _parse_junit(xml_path: Path, root: Path) -> dict[str, dict]:
    """Return ``{test_file: {passed, failed, skipped, adversarial_*}}``.

    A test is counted as failed for either ``<failure>`` or ``<error>`` --
    a collection error is not a pass.
    """
    results: dict[str, dict] = {}
    tree = ET.parse(xml_path)
    for case in tree.getroot().iter("testcase"):
        path = _classname_to_path(case.get("classname", ""), root)
        if path is None:
            continue
        bucket = results.setdefault(
            path,
            {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "adversarial_total": 0,
                "adversarial_failed": 0,
                "failed_names": [],
            },
        )
        name = case.get("name", "")
        is_failure = case.find("failure") is not None or case.find("error") is not None
        is_skipped = case.find("skipped") is not None

        if is_failure:
            bucket["failed"] += 1
            if len(bucket["failed_names"]) < 5:
                bucket["failed_names"].append(name)
        elif is_skipped:
            bucket["skipped"] += 1
        else:
            bucket["passed"] += 1

        if path.startswith(_ADVERSARIAL_DIR) or _ADVERSARIAL_NAME.search(name):
            bucket["adversarial_total"] += 1
            if is_failure:
                bucket["adversarial_failed"] += 1
    return results


def _run_pytest(files: list[str], root: Path, xml_path: Path) -> dict[str, dict]:
    """Execute `files` in one pytest run and return per-file results.

    ``-o addopts=''`` clears the repo's coverage defaults: this run exists to
    establish pass/fail per organ, and the coverage gate is the backend job's
    responsibility, not this gate's.
    """
    if not files:
        return {}
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        f"--junit-xml={xml_path}",
        *files,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, timeout=5400
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise TestExecutionUnavailable(f"pytest could not be run: {exc}") from exc

    if not xml_path.exists():
        tail = (proc.stderr or proc.stdout or "")[-600:]
        raise TestExecutionUnavailable(
            f"pytest produced no JUnit report (exit={proc.returncode}): {tail}"
        )
    # A non-zero exit is expected when tests fail -- that is the signal this
    # gate exists to read, not an error. Only a missing report is fatal.
    return _parse_junit(xml_path, root)


def _failing_conditions_from_verdicts(verdicts: dict[str, str]) -> list[str]:
    failed: list[str] = []
    for key in (f"C{i}" for i in range(1, 13)):
        text = str(verdicts.get(key) or "").strip()
        if not text:
            failed.append(key)
            continue
        if _PASSISH.match(text):
            continue
        # Explicit FAIL / residual language
        if re.search(r"\bFAIL\b", text, re.I) or text.upper().startswith("FAIL"):
            failed.append(key)
    return failed


def _suite_outcome(
    paths, results: dict[str, dict], condition: str, label: str, frontend_ok: bool
) -> list[tuple[str, str]]:
    """Require this organ's suites to have actually run and passed.

    A real test FAILURE always fails the condition. Beyond that the rule is
    "at least one suite genuinely proved something, and nothing broke":

    * A suite that only SKIPPED is unverified here, not failed. Skipping is a
      deliberate declaration that the suite does not apply in this context --
      `tests/test_executor_integration.py` gates itself on
      AIOS_EXECUTOR_INTEGRATION and runs later in this same CI job, inside the
      container. Failing it here would report a passing organ as broken and
      push whoever hits it toward weakening the gate.
    * An organ whose suites ALL end up unverified still fails: nothing was
      proven, and "nothing was proven" must never read as "verified".
    """
    failures: list[tuple[str, str]] = []
    unverified: list[str] = []
    proven = 0

    if not paths:
        return [(condition, f"no {label} listed")]

    for path in paths:
        # Look the suite up FIRST, whatever runner produced it. Checking the
        # extension before consulting `results` discarded real vitest outcomes
        # that --frontend-junit had already supplied and parsed: the report was
        # read, 115 frontend files resolved, and then thrown away because the
        # path did not end in ".py". A gate that ignores evidence it holds is
        # no better than one that never asked for it.
        outcome = results.get(path)
        if outcome is None:
            if not path.endswith(".py"):
                # Frontend suite with no report supplied. Unexecuted is
                # reported as unverified, never as passing -- fail-closed
                # unless the operator consciously allows it.
                if frontend_ok:
                    unverified.append(f"{path} (vitest, no report supplied)")
                else:
                    failures.append(
                        (
                            condition,
                            f"{label} not executed here (needs vitest): {path} "
                            "-- pass --frontend-junit or --allow-unexecuted-frontend",
                        )
                    )
            else:
                failures.append((condition, f"{label} did not run: {path}"))
            continue
        if outcome["failed"]:
            names = ", ".join(outcome["failed_names"])
            failures.append(
                (condition, f"{label} FAILED: {path} ({outcome['failed']}: {names})")
            )
            continue
        if outcome["passed"] == 0:
            if outcome["skipped"]:
                unverified.append(f"{path} (all {outcome['skipped']} skipped)")
            else:
                # A file that exists, runs, and asserts nothing is exactly the
                # hole the old existence check left open.
                failures.append(
                    (condition, f"{label} collected no passing tests: {path}")
                )
            continue
        proven += 1

    if not failures and proven == 0:
        failures.append(
            (
                condition,
                f"no {label} proved anything here (unverified: {', '.join(unverified)})",
            )
        )
    return failures


def _mechanical_checks(
    record,
    root: Path,
    *,
    ancestry_fn,
    results: dict[str, dict],
    frontend_ok: bool,
) -> list[tuple[str, str]]:
    """Return list of (condition, failure_reason) for enforceable subset."""
    from aios.application.governance.organ_ledger import (
        _authority_owner_is_class_reference,
        _frontend_error_state_coverage,
    )

    failures: list[tuple[str, str]] = []
    # C1
    if not _authority_owner_is_class_reference(record, root):
        failures.append(("C1", "authority_owner class not in production_entrypoints"))
    # C2 — focused_tests non-empty (reachability suite listed)
    if not record.focused_tests:
        failures.append(("C2", "no focused_tests for caller/reachability proof"))

    # C6 — focused tests must EXIST, RUN and PASS (not merely be on disk).
    for path in record.focused_tests:
        if not (root / path).exists():
            failures.append(("C6", f"focused_tests path missing: {path}"))
    failures.extend(
        _suite_outcome(
            record.focused_tests, results, "C6", "focused_tests", frontend_ok
        )
    )

    # C7 — same bar for the integration suite.
    for path in record.integration_tests:
        if not (root / path).exists():
            failures.append(("C7", f"integration_tests path missing: {path}"))
    failures.extend(
        _suite_outcome(
            record.integration_tests, results, "C7", "integration_tests", frontend_ok
        )
    )

    # C8
    if record.requires_frontend_error_states and not _frontend_error_state_coverage(
        record, root
    ):
        failures.append(("C8", "frontend error/unavailable coverage missing"))

    # C9 — adversarial / failure-path tests must exist AND pass.
    #
    # Was: "known_blockers is empty", which is the contract's own forbidden
    # anti-pattern -- an organ passed by having nothing written against it.
    # Emptiness is still required (a green organ with a live blocker is a
    # contradiction), but it is no longer sufficient.
    if record.known_blockers:
        failures.append(
            ("C9", f"green still lists known_blockers: {list(record.known_blockers)}")
        )
    organ_py = [
        p
        for p in (*record.focused_tests, *record.integration_tests)
        if p.endswith(".py")
    ]
    adversarial_total = sum(
        results.get(p, {}).get("adversarial_total", 0) for p in organ_py
    )
    adversarial_failed = sum(
        results.get(p, {}).get("adversarial_failed", 0) for p in organ_py
    )
    if adversarial_failed:
        failures.append(
            ("C9", f"{adversarial_failed} adversarial/failure-path test(s) FAILED")
        )
    elif adversarial_total == 0 and organ_py:
        failures.append(
            (
                "C9",
                "no adversarial/failure-path test found in this organ's own suites "
                "-- a guard with no refusal test is untested where it matters",
            )
        )
    # C10 — greens must hold live evidence (Decision B as practiced for Phase 5 flips)
    live_rows = [e for e in record.live_evidence if e.proof_level == "live"]
    if not live_rows:
        failures.append(("C10", "green has no proof_level=live evidence"))
    else:
        for e in live_rows:
            if not _SHA.fullmatch(e.commit_sha):
                failures.append(
                    ("C10", f"live evidence commit_sha malformed: {e.commit_sha!r}")
                )
    # C11
    sha = record.last_verified_sha
    if not sha or not _SHA.fullmatch(sha):
        failures.append(("C11", "missing/malformed last_verified_sha"))
    # C12
    elif ancestry_fn(root, sha) is False:
        failures.append(("C12", f"last_verified_sha {sha} is not an ancestor of HEAD"))
    # Written verdicts must exist and not be empty theater
    verdicts = record.condition_verdicts or {}
    for key in (f"C{i}" for i in range(1, 13)):
        text = str(verdicts.get(key) or "").strip()
        if len(text) < 8:
            failures.append(
                (key, "missing/short written condition_verdicts attestation")
            )
    return failures


def _write_proof(
    organ_id: int,
    name: str,
    status: str,
    *,
    mechanical: list[tuple[str, str]],
    verdict_fails: list[str],
    tip: str | None,
) -> Path:
    PHASE5_DIR.mkdir(parents=True, exist_ok=True)
    path = PHASE5_DIR / f"organ-{organ_id:02d}.md"
    mech_lines = (
        "\n".join(f"- **{c}**: {reason}" for c, reason in mechanical)
        if mechanical
        else "- (none — mechanical subset passed)"
    )
    verdict_line = (
        ", ".join(verdict_fails)
        if verdict_fails
        else "(none — written verdicts PASS/N/A)"
    )
    surviving = status == "green" and not mechanical
    body = f"""# Phase 5 proof — Organ {organ_id}: {name}

**Status under re-read:** `{status}`
**Survives mechanical adversarial re-read:** `{"yes" if surviving else "no"}`
**Evaluated tip:** `{tip}`
**Generated:** {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

## Mechanical failures (enforceable subset)

{mech_lines}

## Written verdict keys that are not PASS/N/A

{verdict_line}

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
"""
    path.write_text(body, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    from aios.application.governance.organ_ledger import (
        current_commit_sha,
        load_ledger,
        sha_is_ancestor_of_head,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demote",
        action="store_true",
        help="Demote greens that fail the mechanical subset to yellow (writes ledger).",
    )
    parser.add_argument(
        "--test-results",
        type=Path,
        default=None,
        help=(
            "Consume an existing pytest JUnit XML instead of re-running. Use when "
            "the same commit's suite already ran in this CI job graph. There is "
            "no way to skip execution entirely -- a real report is required."
        ),
    )
    parser.add_argument(
        "--frontend-junit",
        type=Path,
        default=None,
        help="Vitest JUnit XML, so frontend-referenced organs can be verified too.",
    )
    parser.add_argument(
        "--allow-unexecuted-frontend",
        action="store_true",
        help=(
            "Treat frontend suites this Python-only job cannot run as not-failing. "
            "Records the gap honestly; never claims those tests passed."
        ),
    )
    args = parser.parse_args(argv)

    tip = current_commit_sha(REPO_ROOT)
    records = list(load_ledger(LEDGER_PATH))
    ledger_rows = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    by_id = {int(r["organ_id"]): r for r in ledger_rows}

    # C6/C7/C9 need real outcomes. Collect every Python test file any GREEN
    # organ relies on and run them once -- the suites overlap heavily between
    # organs, so per-organ runs would repeat the same files many times over.
    referenced: set[str] = set()
    for record in records:
        if record.status != "green":
            continue
        for path in (*record.focused_tests, *record.integration_tests):
            if path.endswith(".py") and (REPO_ROOT / path).exists():
                referenced.add(path)

    results: dict[str, dict] = {}
    try:
        if args.test_results:
            if not args.test_results.exists():
                raise TestExecutionUnavailable(
                    f"--test-results not found: {args.test_results}"
                )
            results = _parse_junit(args.test_results, REPO_ROOT)
            print(f"consumed test results from {args.test_results}")
        else:
            print(f"running {len(referenced)} referenced test file(s) for C6/C7/C9 ...")
            results = _run_pytest(
                sorted(referenced), REPO_ROOT, PHASE5_DIR / "junit-organ-tests.xml"
            )
        if args.frontend_junit and args.frontend_junit.exists():
            results.update(_parse_junit(args.frontend_junit, REPO_ROOT))
    except TestExecutionUnavailable as exc:
        # Fail closed. An unrunnable suite must never read as a passing one.
        print(f"C6/C7/C9 cannot be verified: {exc}", file=sys.stderr)
        return 2

    total_failed = sum(v["failed"] for v in results.values())
    print(
        f"test outcomes: {len(results)} file(s), "
        f"{sum(v['passed'] for v in results.values())} passed, {total_failed} failed"
    )

    green_failures: list[str] = []
    demoted: list[int] = []

    for record in records:
        mechanical = (
            _mechanical_checks(
                record,
                REPO_ROOT,
                ancestry_fn=sha_is_ancestor_of_head,
                results=results,
                frontend_ok=args.allow_unexecuted_frontend or bool(args.frontend_junit),
            )
            if record.status == "green"
            else []
        )
        if record.status == "yellow":
            # Still produce a proof section; yellows fail by residual conditions.
            verdict_fails = _failing_conditions_from_verdicts(
                record.condition_verdicts or {}
            )
            # Ensure residual conditions appear for honesty
            residual = " ".join(record.known_blockers).lower()
            for cond, needle in (
                ("C1", "frozen spine"),  # frozen may still pass C1 class after §VIII
                ("C10", "outside-machine"),
                ("C10", "no ollama"),
                ("C10", "no docker"),
                ("C10", "browser-session"),
                ("C10", "phase 6 gate"),
                ("C10", "frozen spine"),
            ):
                if needle in residual and cond not in verdict_fails:
                    # Don't force-add if written verdict already PASS for C1 on frozen
                    pass
            _write_proof(
                record.organ_id,
                record.name,
                record.status,
                mechanical=[("residual", b) for b in record.known_blockers]
                or [("residual", "yellow without named residual")],
                verdict_fails=verdict_fails or ["C10"],
                tip=tip,
            )
            continue

        verdict_fails = _failing_conditions_from_verdicts(
            record.condition_verdicts or {}
        )
        _write_proof(
            record.organ_id,
            record.name,
            record.status,
            mechanical=mechanical,
            verdict_fails=verdict_fails,
            tip=tip,
        )
        if mechanical:
            msg = (
                f"organ {record.organ_id} ({record.name}) failed mechanical "
                f"re-read: {mechanical}"
            )
            green_failures.append(msg)
            if args.demote:
                row = by_id[record.organ_id]
                row["status"] = "yellow"
                reasons = [f"{c}: {r}" for c, r in mechanical]
                row["known_blockers"] = [
                    "Phase 5 mechanical re-read demotion — " + "; ".join(reasons)
                ]
                demoted.append(record.organ_id)

    # Index file
    PHASE5_DIR.mkdir(parents=True, exist_ok=True)
    greens = [r for r in records if r.status == "green"]
    yellows = [r for r in records if r.status == "yellow"]
    index = PHASE5_DIR / "README.md"
    index.write_text(
        f"""# Phase 5 — per-organ adversarial re-read

**Tip:** `{tip}`
**Counts at generation:** {len(greens)} green / {len(yellows)} yellow (pre-demote)
**Demoted this run:** {demoted or "none"}
**Green mechanical failures:** {len(green_failures)}

One proof file per organ: `organ-NN.md`. This is not a mass-flip note.

## Green mechanical failures

{chr(10).join("- " + g for g in green_failures) if green_failures else "- (none)"}
""",
        encoding="utf-8",
    )

    if args.demote and demoted:
        LEDGER_PATH.write_text(
            json.dumps(ledger_rows, indent=2) + "\n", encoding="utf-8"
        )
        print(f"demoted organs: {demoted}")

    print(f"phase5 proofs written under {PHASE5_DIR.as_posix()}")
    print(f"green mechanical failures: {len(green_failures)}")
    if green_failures and not args.demote:
        for msg in green_failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
