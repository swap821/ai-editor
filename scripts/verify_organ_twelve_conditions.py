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
                # Per-test names, not just counts. C3/C4/C5 name a SPECIFIC
                # test as their proof, so file-level "0 failures" is not
                # enough -- a verdict could cite a test that does not exist,
                # or that was skipped, and the file would still look clean.
                "passed_names": set(),
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
            bucket["passed_names"].add(name)

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


#: A condition proof: an exact test that must have executed and PASSED, written
#: `tests/foo.py::test_bar` inside the condition's own written verdict.
_CONDITION_PROOF_RE = re.compile(
    r"((?:tests|frontend)/[\w./\-]+\.(?:py|tsx?|jsx?))::([\w\[\]\-]+)"
)

#: C3 and C4 are defined as "... (or N/A-BY-DESIGN with cite)", so they may be
#: discharged by a resolvable code cite instead of a test. C5 -- "Fail-safe
#: reporting: unavailable rather than a plausible zero" -- carries no such
#: clause, so it must be positively proven. Inventing an escape hatch the
#: contract does not grant would be the whole failure mode in miniature.
_NA_DISCHARGEABLE = frozenset({"C3", "C4"})
_PROOF_CONDITIONS = ("C3", "C4", "C5")


#: The four shapes a live-evidence row can take. Everything a green organ
#: claims as "live" must be one of these -- see _evidence_reference_failures.
_PHASE4_ARTIFACT_RE = re.compile(r"release/phase4/live-evidence-[\w.\-]+\.json")
_CI_RUN_RE = re.compile(r"actions/runs/(\d+)")
#: Human-witnessed evidence (an operator driving a real browser) cannot be
#: re-derived by a script. It is a legitimate kind of proof and the ledger has
#: four such rows, but it must be DECLARED rather than inferred -- otherwise it
#: is indistinguishable from prose, which is how `_LIVE_RECHECKABLE` came to
#: accept any string containing "https://".
_OPERATOR_ATTESTED = "OPERATOR-ATTESTED"


def _github_run_verifier(root: Path):
    """Resolve a cited CI run against the GitHub API.

    Checks the three things a fabricated or mis-cited run would fail: that the
    run exists at all, that it actually SUCCEEDED, and that its head_sha is the
    commit the evidence row claims. The last one is the subtle one -- citing a
    real green run from a different commit is exactly how a row ends up
    describing work the named commit never contained.
    """

    def verify(run_id: str, expected_sha: str) -> str | None:
        proc = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}",
                "-q",
                '.conclusion + " " + .head_sha',
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return f"could not be resolved ({proc.stderr.strip()[:100]})"
        parts = proc.stdout.split()
        if len(parts) != 2:
            return f"unexpected API response {proc.stdout.strip()[:60]!r}"
        conclusion, head_sha = parts
        if conclusion != "success":
            return f"conclusion is {conclusion!r}, not success"
        if head_sha != expected_sha:
            return f"ran at {head_sha[:12]} but the evidence claims {expected_sha[:12]}"
        return None

    return verify


def _evidence_reference_failures(
    record,
    root: Path,
    results: dict[str, dict],
    *,
    run_verifier=None,
) -> tuple[list[tuple[str, str]], int]:
    """Live evidence must be CHECKABLE, not merely look checkable.

    ``_LIVE_RECHECKABLE`` only asked whether the description contained a
    substring like ``https://`` or ``docker-compose``. It never opened the
    artifact, never confirmed the cited run existed, and never checked that
    what was cited said anything about THIS organ. Fifty-nine rows of prose
    were load-bearing on the author's good faith alone.

    Every ``proof_level="live"`` row must now resolve as one of:

    * a ``release/phase4/live-evidence-*.json`` artifact that exists, carries a
      proof record FOR THIS ORGAN, records it as passed, and whose ``tip_sha``
      matches the row's ``commit_sha``;
    * a ``tests/foo.py::test_bar`` node that ran and passed in this gate run;
    * an ``actions/runs/<id>`` CI run, verified when a verifier is supplied;
    * an explicitly declared ``OPERATOR-ATTESTED`` human observation.

    Returns (failures, operator_attested_count). The count is reported rather
    than hidden: how much of the ledger rests on human attestation is exactly
    the kind of thing that should be visible on every run.
    """
    failures: list[tuple[str, str]] = []
    attested = 0

    for evidence in record.live_evidence:
        if evidence.proof_level != "live":
            continue
        desc = evidence.description
        artifacts = _PHASE4_ARTIFACT_RE.findall(desc)
        runs = _CI_RUN_RE.findall(desc)
        nodes = _CONDITION_PROOF_RE.findall(desc)
        operator = _OPERATOR_ATTESTED in desc

        if not (artifacts or runs or nodes or operator):
            failures.append(
                (
                    "C10",
                    "live evidence resolves to nothing checkable -- cite a "
                    "release/phase4 artifact, a tests/foo.py::test_bar node, an "
                    f"actions/runs/<id> URL, or declare {_OPERATOR_ATTESTED}",
                )
            )
            continue

        if operator:
            attested += 1

        for ref in artifacts:
            path = root / ref
            if not path.exists():
                failures.append(("C10", f"cited artifact does not exist: {ref}"))
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(("C10", f"cited artifact unreadable: {ref} ({exc})"))
                continue
            proofs = {
                p.get("organ_id"): p
                for p in payload.get("proofs", [])
                if isinstance(p, dict)
            }
            proof = proofs.get(record.organ_id)
            if proof is None:
                failures.append(
                    (
                        "C10",
                        f"{ref} carries no proof record for organ "
                        f"{record.organ_id} -- it proves someone else's claim",
                    )
                )
                continue
            if not proof.get("passed"):
                failures.append(
                    ("C10", f"{ref} records organ {record.organ_id} as NOT passed")
                )
            tip = payload.get("tip_sha")
            if tip != evidence.commit_sha:
                failures.append(
                    (
                        "C10",
                        f"{ref} was generated at {str(tip)[:12]} but the evidence "
                        f"claims {evidence.commit_sha[:12]}",
                    )
                )

        for path, test_name in nodes:
            outcome = results.get(path)
            if outcome is None:
                failures.append(
                    (
                        "C10",
                        f"cited test {path}::{test_name} did not execute in this run",
                    )
                )
            elif not _proof_ran_and_passed(outcome, test_name):
                failures.append(
                    ("C10", f"cited test {path}::{test_name} did not run and pass")
                )

        if run_verifier is not None:
            for run_id in runs:
                problem = run_verifier(run_id, evidence.commit_sha)
                if problem:
                    failures.append(("C10", f"CI run {run_id}: {problem}"))

    return failures, attested


def _referenced_test_files(records) -> set[str]:
    """Every on-disk .py file any GREEN organ needs run in this gate.

    Two sources, both real citations: ``focused_tests``/``integration_tests``
    (C6/C7/C9's evidence) and any ``tests/foo.py::test_bar`` named inside a
    ``condition_verdicts`` string (C3/C4/C5's evidence). A test can be the
    latter without ever being the former -- e.g. organs 1-5 cite
    ``tests/test_spine_invariants.py`` for C5 while their focused/integration
    lists point elsewhere entirely -- and omitting that source left a real,
    passing proof indistinguishable from one that was never run at all.
    """
    referenced: set[str] = set()
    for record in records:
        if record.status != "green":
            continue
        for path in (*record.focused_tests, *record.integration_tests):
            if path.endswith(".py") and (REPO_ROOT / path).exists():
                referenced.add(path)
        for text in (record.condition_verdicts or {}).values():
            for path, _test_name in _CONDITION_PROOF_RE.findall(str(text or "")):
                if path.endswith(".py") and (REPO_ROOT / path).exists():
                    referenced.add(path)
    return referenced


def _proof_ran_and_passed(outcome: dict, test_name: str) -> bool:
    """Did the cited test run and pass -- including when it is parametrized?

    The bug this closes
    -------------------
    Both proof checks asked ``test_name not in outcome["passed_names"]``, an
    exact membership test. pytest never records a parametrized test under its
    bare name: ``test_x`` decorated with three cases appears as
    ``test_x[case0]``, ``test_x[case1]``, ``test_x[case2]``. So a citation
    naming a parametrized test could NEVER be discharged, no matter how
    thoroughly it passed, and the organ silently joined the proof-gap set.

    That is what took master's release-authority job down. Organ 46 went green
    in #213 citing
    ``test_applicable_amendments.py::test_changes_swapped_after_ratification_are_refused``
    for C4 -- three parametrized cases, all passing. The gate scored it
    unproven, the gap count went 46 -> 47, and the condition-proof ratchet
    correctly refused a regression it had been handed by a measurement error.

    Why this does not lower the bar
    -------------------------------
    A parametrized test that passes IS an executed, passing proof; crediting it
    is the gate finally asking the question it always claimed to ask. The bar
    is if anything RAISED: a parametrized proof counts only when NO case of it
    failed, so citing a test whose fifth case is red no longer half-counts.

    Deliberately narrow: ``test_x`` matches ``test_x`` and ``test_x[...]``, and
    nothing else. It does not prefix-match sibling tests -- ``test_x`` must not
    be discharged by ``test_x_and_more`` passing.
    """
    passed = outcome.get("passed_names", ())
    bracket = f"{test_name}["

    def _matches(name: str) -> bool:
        return name == test_name or name.startswith(bracket)

    if not any(_matches(name) for name in passed):
        return False
    # `failed_names` is capped by the collector, so this cannot be the ONLY
    # guard -- but where a failure IS recorded it must veto the citation
    # outright rather than let a passing sibling case launder it.
    return not any(_matches(name) for name in outcome.get("failed_names", ()))


def _condition_proof_failures(
    record, results: dict[str, dict], *, require_execution: bool = True
) -> list[tuple[str, str]]:
    """C3/C4/C5 must point at something real, not merely read well.

    These three were the ledger's weakest link: the only mechanical check on
    them was ``len(text) >= 8``. C3 ("durable state survives process restart"),
    C4 ("tamper-evidence / integrity chain") and C5 ("fail-safe reporting:
    unavailable rather than a plausible zero") are precisely the conditions a
    hostile reviewer cares about, and precisely the ones nothing enforced.

    The bar here is the same one C6/C7 already apply, so it is proven
    machinery rather than a new idea: name a test, and that exact test must
    have RUN and PASSED in this very gate invocation. A file-level "no
    failures" would not do -- a verdict could cite a test that does not exist,
    or one that skipped, and the file would still look clean.

    ``require_execution`` (default True) is the real gate's behaviour and is
    unchanged: a named proof must have RUN and PASSED in this invocation.

    Set it False to ask the narrower question "does this verdict name a referent
    at all", independent of any test run. Only the monotonic budget in
    ``tests/test_condition_proof_ratchet.py`` wants that, and it is a separate
    parameter rather than an inference from ``results == {}`` on purpose: an
    empty results mapping from a REAL gate run means nothing passed, which must
    stay a failure. Conflating the two is what broke the ratchet -- see
    ``test_condition_proof_ratchet`` for the arithmetic.
    """
    failures: list[tuple[str, str]] = []
    verdicts = record.condition_verdicts or {}

    for cond in _PROOF_CONDITIONS:
        text = str(verdicts.get(cond) or "")

        if cond in _NA_DISCHARGEABLE and "N/A-BY-DESIGN" in text:
            # The cite itself is resolved by na_cite_validator, which reads
            # condition_verdicts as well as known_blockers. Here we only
            # require that one is actually present -- "N/A-BY-DESIGN" with no
            # cite is an assertion, not a discharge.
            from aios.application.governance.na_cite_validator import (
                _extract_cites_from_blocker,
            )

            if not _extract_cites_from_blocker(text):
                failures.append(
                    (cond, "N/A-BY-DESIGN carries no path::symbol cite to resolve")
                )
            continue

        refs = _CONDITION_PROOF_RE.findall(text)
        if not refs:
            failures.append(
                (
                    cond,
                    "no executable proof named -- cite a test as "
                    "'tests/foo.py::test_bar'"
                    + (
                        " or discharge with 'N/A-BY-DESIGN — path::symbol'"
                        if cond in _NA_DISCHARGEABLE
                        else " (C5 has no N/A-BY-DESIGN clause)"
                    ),
                )
            )
            continue

        if not require_execution:
            # A referent is named; that is the whole question in this mode.
            continue

        for path, test_name in refs:
            outcome = results.get(path)
            if outcome is None:
                failures.append(
                    (cond, f"proof {path}::{test_name} did not execute in this run")
                )
            elif not _proof_ran_and_passed(outcome, test_name):
                failures.append(
                    (cond, f"proof {path}::{test_name} did not run and pass")
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
        # Every live row must resolve to something a machine can open. The
        # run_verifier is left off here: network checks belong to the explicit
        # --verify-evidence-runs path, so a local run degrades to the offline
        # subset rather than silently passing rows it never resolved.
        evidence_failures, _ = _evidence_reference_failures(record, root, results)
        failures.extend(evidence_failures)
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
    # newline="\n" on every write below: without it a Windows run rewrites all
    # 54 tracked proof docs with CRLF, producing an all-lines-changed diff that
    # buries whatever actually changed. The ledger write further down is worse
    # than noise -- its bytes are sha256-pinned by release/organ-proof-manifest
    # .json, so a CRLF copy pins a hash that an LF checkout cannot reproduce.
    path.write_text(body, encoding="utf-8", newline="\n")
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
        "--extra-junit",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Additional JUnit XML to merge, repeatable. For suites this gate's "
            "own pytest run cannot execute -- notably "
            "tests/test_executor_integration.py, which gates on "
            "AIOS_EXECUTOR_INTEGRATION and only runs inside the executor "
            "container. Without it those suites are all-skipped here, and an "
            "organ whose ONLY integration suite is env-gated (organ 40) can "
            "never satisfy C7."
        ),
    )
    parser.add_argument(
        "--allow-unexecuted-frontend",
        action="store_true",
        help=(
            "Treat frontend suites this Python-only job cannot run as not-failing. "
            "Records the gap honestly; never claims those tests passed."
        ),
    )
    parser.add_argument(
        "--verify-evidence-runs",
        action="store_true",
        help=(
            "Resolve every cited actions/runs/<id> against the GitHub API and "
            "require it to exist, to have succeeded, and to have run at the "
            "commit the evidence claims. Needs network and an authenticated "
            "gh; off by default so a local run degrades to the offline subset "
            "honestly rather than reporting rows it never resolved."
        ),
    )
    parser.add_argument(
        "--enforce-condition-proofs",
        action="store_true",
        help=(
            "Make a missing C3/C4/C5 mechanical proof a hard failure rather "
            "than a ratcheted budget. This is the end state: every green organ "
            "names a test that ran and passed (or, for C3/C4 only, discharges "
            "with an N/A-BY-DESIGN cite that resolves). Off by default only "
            "because turning it on today would demote ~45 greens at once, "
            "which is an operator decision."
        ),
    )
    args = parser.parse_args(argv)

    tip = current_commit_sha(REPO_ROOT)
    records = list(load_ledger(LEDGER_PATH))
    ledger_rows = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    by_id = {int(r["organ_id"]): r for r in ledger_rows}

    # C6/C7/C9 need real outcomes, and so do C3/C4/C5's named proofs -- see
    # _referenced_test_files's docstring for why both sources matter. The
    # suites overlap heavily between organs, so per-organ runs would repeat
    # the same files many times over; run the union once instead.
    referenced = _referenced_test_files(records)

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
        # A supplied-but-missing report is a hard failure, not a shrug. The
        # previous `and .exists()` meant a failed artifact download silently
        # produced a gate run with no frontend evidence -- while
        # `frontend_ok` stayed True because the FLAG was passed, so those
        # suites were waved through as allowed-unverified. That is the same
        # "verification passes while the thing it verifies is absent" shape
        # this gate exists to stop.
        for extra in [args.frontend_junit, *args.extra_junit]:
            if extra is None:
                continue
            if not extra.exists():
                raise TestExecutionUnavailable(
                    f"JUnit report was passed but does not exist: {extra}"
                )
            merged = _parse_junit(extra, REPO_ROOT)
            if not merged:
                raise TestExecutionUnavailable(
                    f"JUnit report resolved no known test files: {extra}"
                )
            results.update(merged)
            print(f"merged {len(merged)} file result(s) from {extra}")
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
    # C3/C4/C5 proof inventory, tracked separately from green_failures so the
    # ratchet below can report the true gap without demoting 45 organs on the
    # day the check lands. See the budget block after this loop.
    proof_gaps: dict[int, list[tuple[str, str]]] = {}

    for record in records:
        if record.status == "green":
            gaps = _condition_proof_failures(record, results)
            if gaps:
                proof_gaps[record.organ_id] = gaps
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
        newline="\n",
    )

    if args.demote and demoted:
        LEDGER_PATH.write_text(
            json.dumps(ledger_rows, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"demoted organs: {demoted}")

    print(f"phase5 proofs written under {PHASE5_DIR.as_posix()}")

    # ---- C3/C4/C5 mechanical-proof ratchet ---------------------------------
    #
    # Until this landed, the ONLY check on C3 (durable state survives restart),
    # C4 (tamper-evidence chain) and C5 (fail-safe reporting) was that the
    # written verdict was >= 8 characters. Those are the three conditions a
    # hostile reviewer cares about most, and they were the three nothing
    # enforced.
    #
    # Enforcing them outright on day one would demote ~45 greens at a stroke,
    # which is an operator decision, not a gate decision. So this follows the
    # precedent already set by "Enforce monotonic frontend warning budget":
    # record the current gap and refuse to let it GROW. Progress is one-way,
    # the true number is printed every run rather than hidden, and the day the
    # budget reaches zero the --enforce-condition-proofs flag can become the
    # permanent default.
    # ---- live-evidence reference report ------------------------------------
    #
    # How much of the ledger rests on human attestation rather than on
    # something a machine can re-open is exactly the kind of number that should
    # be visible on every run instead of buried in prose.
    attested_total = 0
    run_failures: list[str] = []
    verifier = _github_run_verifier(REPO_ROOT) if args.verify_evidence_runs else None
    for record in records:
        if record.status != "green":
            continue
        failures_, attested_ = _evidence_reference_failures(
            record, REPO_ROOT, results, run_verifier=verifier
        )
        attested_total += attested_
        if verifier is not None:
            run_failures.extend(
                f"organ {record.organ_id}: {why}"
                for cond, why in failures_
                if why.startswith("CI run ")
            )
    print(f"live evidence rows resting on operator attestation: {attested_total}")
    if args.verify_evidence_runs:
        print(
            f"cited CI runs verified against the GitHub API; problems: {len(run_failures)}"
        )
        for msg in run_failures:
            print(f"  - {msg}", file=sys.stderr)
        if run_failures:
            return 1

    budget_path = REPO_ROOT / ".aios" / "state" / "condition_proof_budget.json"
    gap_count = len(proof_gaps)
    print(f"C3/C4/C5 greens without a mechanical proof: {gap_count}")
    if proof_gaps:
        shown = sorted(proof_gaps)[:5]
        for oid in shown:
            reasons = "; ".join(f"{c}: {r}" for c, r in proof_gaps[oid][:1])
            print(f"    organ {oid}: {reasons}")
        if len(proof_gaps) > len(shown):
            print(f"    ... and {len(proof_gaps) - len(shown)} more")

    if args.enforce_condition_proofs:
        if proof_gaps:
            for oid in sorted(proof_gaps):
                for cond, reason in proof_gaps[oid]:
                    print(f"  - organ {oid} {cond}: {reason}", file=sys.stderr)
            return 1
    elif budget_path.exists():
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        allowed = int(budget.get("greens_without_condition_proofs", 0))
        if gap_count > allowed:
            print(
                f"C3/C4/C5 proof budget REGRESSED: {gap_count} > {allowed}. "
                "A green organ lost its mechanical proof, or a new green "
                "landed without one. The budget may only go down; update "
                f"{budget_path.as_posix()} deliberately, never to make a "
                "failure go away.",
                file=sys.stderr,
            )
            return 1

    print(f"green mechanical failures: {len(green_failures)}")
    if green_failures and not args.demote:
        for msg in green_failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
