"""The learning gate must fail the things it exists to fail.

A gate nobody tests is paperwork, and this one shipped a real bug on its first
run: `_suite_verdict` read `tests`/`failures` from the JUnit buckets, which are
actually named `passed`/`failed`, so every faculty was reported as "ran ZERO
tests". The condition caught its own verifier — which is the argument for the
condition, and also the argument for these tests.

Everything below is adversarial in the same direction: each case is a way a
faculty could look compliant while proving nothing. LC6 passing because a file
EXISTS is the exact weakness the organ gate had to fix the hard way, and it is
re-pinned here so this gate cannot re-acquire it.
"""

from __future__ import annotations

import pytest

from scripts.verify_learning_conditions import evaluate

#: A file that really exists, so referent checks resolve for the right reason.
REAL_ENTRYPOINT = "aios/memory/skills.py"
REAL_SUITE = "tests/test_skill_failure_streak.py"


def _record(**overrides) -> dict:
    base = {
        "faculty_id": "LX",
        "name": "a faculty under test",
        "authority_owner": "SkillMemory",
        "production_entrypoints": [REAL_ENTRYPOINT],
        "live_path_callers": ["aios/application/turns/generate_pipeline.py"],
        # Declared explicitly, and measured: ReflectionAgent really is
        # referenced there. SkillMemory is NOT -- it arrives by injection as
        # `runtime.skills` -- which is exactly why the symbol must be named.
        "live_path_symbols": ["ReflectionAgent"],
        "durable_store": {"table": "procedural_skills"},
        "journal": {"kind": "jsonl", "referent": "x", "append_only_claim": True},
        "fail_closed_tests": [REAL_SUITE],
        "focused_tests": [REAL_SUITE],
        "integration_tests": [REAL_SUITE],
        "mutation_probe": {"referent": f"{REAL_ENTRYPOINT}::record_attempt"},
        "known_blockers": [],
        "live_evidence": [
            {
                "description": "d",
                "command": "python tools/reverse_engineer_gagos.py",
                "artifact": REAL_ENTRYPOINT,
                "commit_sha": "0" * 40,
                "proof_level": "live",
                "organic": True,
            }
        ],
        "last_verified_sha": None,
        "na_by_design": {},
    }
    base.update(overrides)
    return base


PASSING = {REAL_SUITE: {"passed": 7, "failed": 0, "skipped": 0, "failed_names": []}}


def _verdict(record, results=None, condition="LC6"):
    return evaluate(record, results if results is not None else PASSING).verdicts[
        condition
    ]


class TestSuitesMustActuallyRunAndPass:
    def test_a_failing_suite_fails_the_condition(self) -> None:
        results = {REAL_SUITE: {"passed": 3, "failed": 1, "failed_names": ["test_x"]}}
        v = _verdict(_record(), results)
        assert v.state == "FAIL" and "test_x" in v.why

    def test_a_suite_that_ran_nothing_fails(self) -> None:
        """Zero tests is the hollow-run hole wearing a green tick."""
        results = {REAL_SUITE: {"passed": 0, "failed": 0, "failed_names": []}}
        v = _verdict(_record(), results)
        assert v.state == "FAIL" and "ZERO" in v.why

    def test_a_suite_that_exists_but_never_ran_fails(self) -> None:
        """Existing on disk is what the organ gate used to accept. Not enough."""
        v = _verdict(_record(), {})
        assert v.state == "FAIL" and "did not run" in v.why

    def test_a_declared_suite_that_is_missing_fails(self) -> None:
        v = _verdict(_record(focused_tests=["tests/test_does_not_exist.py"]))
        assert v.state == "FAIL" and "missing" in v.why

    def test_declaring_no_suite_at_all_fails(self) -> None:
        v = _verdict(_record(focused_tests=[]))
        assert v.state == "FAIL"

    def test_a_genuinely_passing_suite_passes(self) -> None:
        assert _verdict(_record()).state == "PASS"


class TestNotApplicableNeedsSomewhereToLook:
    def test_an_na_without_a_resolving_referent_is_refused(self) -> None:
        """'Not applicable' with no pointer is just the word 'no'."""
        v = _verdict(
            _record(journal={}, na_by_design={"LC4": "not applicable here, trust me"}),
            condition="LC4",
        )
        assert v.state == "FAIL" and "excuse" in v.why

    def test_an_na_pointing_at_a_nonexistent_file_is_refused(self) -> None:
        v = _verdict(
            _record(
                journal={},
                na_by_design={"LC4": "Referent: aios/memory/not_a_real_file.py::Thing"},
            ),
            condition="LC4",
        )
        assert v.state == "FAIL"

    def test_an_na_with_a_real_referent_is_honoured(self) -> None:
        v = _verdict(
            _record(
                journal={},
                na_by_design={"LC4": f"Referent: {REAL_ENTRYPOINT}::SkillMemory"},
            ),
            condition="LC4",
        )
        assert v.state == "N-A"

    def test_a_bare_path_referent_resolves(self) -> None:
        """Not every referent is a symbol; an artifact file is a real pointer."""
        v = _verdict(
            _record(journal={}, na_by_design={"LC4": f"Referent: {REAL_ENTRYPOINT}"}),
            condition="LC4",
        )
        assert v.state == "N-A"


class TestLivePathReachability:
    """LC2 is the condition that catches 'documented canonical, imported by nothing'."""

    def test_a_caller_that_never_mentions_the_faculty_fails(self) -> None:
        v = _verdict(_record(live_path_callers=["README.md"]), condition="LC2")
        assert v.state == "FAIL" and "appears in any declared caller" in v.why

    def test_declaring_no_caller_fails(self) -> None:
        v = _verdict(_record(live_path_callers=[]), condition="LC2")
        assert v.state == "FAIL" and "script" in v.why

    def test_a_real_caller_passes(self) -> None:
        assert _verdict(_record(), condition="LC2").state == "PASS"

    def test_a_symbol_reached_only_by_injection_must_be_named_as_such(self) -> None:
        """`SkillMemory` never appears in the turn path; `runtime.skills` does.

        Defaulting to the owner class name would mark a faculty unreachable
        when it is merely injected -- and a word-level grep for "skills"
        would mark README.md a caller. Only the exact symbol is honest.
        """
        assert (
            _verdict(_record(live_path_symbols=["SkillMemory"]), condition="LC2").state
            == "FAIL"
        )
        assert (
            _verdict(
                _record(live_path_symbols=["runtime.skills"]), condition="LC2"
            ).state
            == "PASS"
        )


class TestEvidenceMustBeOrganicAndReal:
    def test_synthetic_evidence_does_not_count(self) -> None:
        record = _record()
        record["live_evidence"][0]["organic"] = False
        v = _verdict(record, condition="LC10")
        assert v.state == "FAIL" and "ORGANIC" in v.why

    def test_evidence_citing_a_missing_artifact_fails(self) -> None:
        record = _record()
        record["live_evidence"][0]["artifact"] = ".aios/audit/not-here.jsonl"
        v = _verdict(record, condition="LC10")
        assert v.state == "FAIL" and "does not exist" in v.why

    def test_evidence_without_a_reproducible_command_fails(self) -> None:
        record = _record()
        record["live_evidence"][0]["command"] = ""
        v = _verdict(record, condition="LC10")
        assert v.state == "FAIL" and "command" in v.why


class TestOwnershipAndLineage:
    def test_an_owner_not_defined_in_its_entrypoint_fails(self) -> None:
        v = _verdict(_record(authority_owner="NoSuchClass"), condition="LC1")
        assert v.state == "FAIL"

    def test_an_unreachable_sha_fails_ancestry(self) -> None:
        """A squash-merge orphans the evidence commit; that must be caught."""
        v = _verdict(_record(last_verified_sha="0" * 40), condition="LC12")
        assert v.state == "FAIL" and "ancestor" in v.why

    def test_a_missing_sha_fails_both_currency_conditions(self) -> None:
        record = _record(last_verified_sha=None)
        assert _verdict(record, condition="LC11").state == "FAIL"
        assert _verdict(record, condition="LC12").state == "FAIL"


class TestBlockersAreNotDecoration:
    def test_a_stated_blocker_keeps_the_faculty_yellow(self) -> None:
        """The organ contract's rule: never flip green because nobody wrote a
        blocker down. The inverse must also hold — writing one down must cost."""
        v = _verdict(
            _record(known_blockers=["something is genuinely broken"]), condition="LC9"
        )
        assert v.state == "FAIL"

    def test_a_mutation_probe_without_a_referent_fails(self) -> None:
        v = _verdict(_record(mutation_probe={"referent": "vibes"}), condition="LC8")
        assert v.state == "FAIL"

    def test_no_mutation_probe_at_all_fails(self) -> None:
        v = _verdict(_record(mutation_probe=None), condition="LC8")
        assert v.state == "FAIL" and "silently absorbed" in v.why


class TestTheLedgerOnDiskIsWellFormed:
    def test_every_faculty_declares_the_fields_the_gate_reads(self) -> None:
        import json
        from scripts.verify_learning_conditions import LEDGER

        faculties = json.loads(LEDGER.read_text(encoding="utf-8"))["faculties"]
        assert faculties, "an empty ledger would trivially pass everything"
        for record in faculties:
            for key in (
                "faculty_id",
                "name",
                "authority_owner",
                "production_entrypoints",
            ):
                assert record.get(key), f"{record.get('faculty_id')} missing {key}"

    def test_faculty_ids_are_unique(self) -> None:
        import json
        from scripts.verify_learning_conditions import LEDGER

        ids = [
            f["faculty_id"]
            for f in json.loads(LEDGER.read_text(encoding="utf-8"))["faculties"]
        ]
        assert len(ids) == len(set(ids))


@pytest.mark.parametrize("condition", ["LC1", "LC2", "LC5", "LC6", "LC7", "LC10"])
def test_every_condition_reports_a_reason(condition: str) -> None:
    """A verdict with no `why` cannot be acted on, which makes it decoration."""
    v = _verdict(_record(), condition=condition)
    assert v.why.strip(), f"{condition} produced a verdict with no reason"
