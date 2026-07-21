"""Unit tests for the learning-loop prover's pure parts.

The live chain (failure -> lesson -> promotion -> reflex replay) needs a
running backend + local LLM and is exercised by the harness itself; these
tests CI-gate everything deterministic: sandbox-allowlist compliance,
outcome/evidence classification, and the strict/lenient check semantics.
"""
from __future__ import annotations

import pytest

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE
from aios.security.secret_scanner import scan_and_redact
from tools.learning_loop_prover import (
    REFLEX_REPS,
    Check,
    check_allowlist,
    fail_before_pass,
    fixture_paths,
    has_confirm_step,
    has_id,
    strong_pass,
    used_write_tools,
    verify_command,
    _seed,
    _slug,
)


class TestSlug:
    """3-letter lowercase slug: deterministic, and short enough to stay
    scanner-clean (unlike the raw 15-char run_id timestamp)."""

    def test_deterministic_for_same_run_id(self):
        assert _slug("20260706T120000") == _slug("20260706T120000")

    def test_differs_for_different_run_ids(self):
        assert _slug("20260706T120000") != _slug("20260706T120001")

    def test_is_three_lowercase_letters(self):
        slug = _slug("20260706T120000")
        assert len(slug) == 3
        assert slug.isalpha()
        assert slug.islower()


class TestSandboxCompliance:
    def test_all_fixture_paths_inside_allowlist(self):
        for rel in fixture_paths("20260706T120000").values():
            assert ALLOWED_FILE_RE.match(rel), rel

    def test_fixture_paths_use_lab_and_a_three_letter_slug_stem(self):
        slug = _slug("20260706T120000")
        for rel in fixture_paths("20260706T120000").values():
            assert rel.startswith("lab/"), rel
            stem = rel.rsplit("/", 1)[-1][: -len(".py")]
            assert stem.endswith(slug), rel
            # The raw 15-char run_id must NOT appear in the filename — that
            # long a base64-alphabet run is exactly what trips the scanner.
            assert "20260706T120000" not in rel

    def test_all_verify_commands_inside_allowlist(self):
        for rel in fixture_paths("20260706T120000").values():
            assert ALLOWED_CMD_RE.match(verify_command(rel)), verify_command(rel)

    def test_verify_commands_are_scanner_clean(self):
        """Locks the scanner-clean property: a future rename can't silently
        regress fixture filenames back into HIGH_ENTROPY territory."""
        for run_id in ("20260706T120000", "20260707T091234", "20261231T235959"):
            for rel in fixture_paths(run_id).values():
                cmd = verify_command(rel)
                result = scan_and_redact(cmd)
                assert result.detected is False, (run_id, cmd, result)

    def test_fixture_paths_are_unique_per_run(self):
        a = set(fixture_paths("20260706T120000").values())
        b = set(fixture_paths("20260706T120001").values())
        assert not (a & b)

    def test_seed_refuses_paths_outside_sandbox(self, tmp_path):
        with pytest.raises(ValueError):
            _seed("aios/evil.py", "boom")
        with pytest.raises(ValueError):
            _seed("training_ground/nested/evil.py", "boom")
        with pytest.raises(ValueError):
            _seed("lab/nested/evil.py", "boom")

    def test_reflex_reps_meet_the_promotion_floor(self):
        # SkillMemory promotes at min_successes=3; fewer reps can never compile.
        assert REFLEX_REPS >= 3


class TestApprovalAllowlist:
    def test_sandbox_edit_approved(self):
        ok, _ = check_allowlist(
            {"input": {"edits": [{"filepath": "training_ground/llp_buggy_x.py"}]}}
        )
        assert ok

    def test_outside_edit_rejected(self):
        ok, why = check_allowlist({"input": {"edits": [{"filepath": "aios/config.py"}]}})
        assert not ok and "outside allowlist" in why

    def test_pytest_command_approved(self):
        ok, _ = check_allowlist(
            {"input": {"commands": ["pytest training_ground/test_llp_reflex_x.py -q"]}}
        )
        assert ok

    def test_arbitrary_command_rejected(self):
        ok, _ = check_allowlist({"input": {"commands": ["rm -rf /"]}})
        assert not ok

    def test_unrecognized_shape_rejected(self):
        ok, why = check_allowlist({"input": {}})
        assert not ok and "unrecognized" in why


class TestEvidenceClassification:
    def test_fail_before_pass_true_on_recovery(self):
        result = {"evidence": [
            "[VERIFY FAIL] 0 passed, 2 failed (exit 1) (strength=NONE)",
            "[VERIFY PASS] 2 passed, 0 failed (exit 0) (strength=STRONG)",
        ]}
        assert fail_before_pass(result)

    def test_fail_before_pass_false_without_failure(self):
        assert not fail_before_pass(
            {"evidence": ["[VERIFY PASS] 2 passed, 0 failed (exit 0) (strength=STRONG)"]}
        )

    def test_fail_before_pass_false_when_ending_failed(self):
        result = {"evidence": [
            "[VERIFY PASS] 2 passed, 0 failed (exit 0) (strength=STRONG)",
            "[VERIFY FAIL] 0 passed, 2 failed (exit 1) (strength=NONE)",
        ]}
        assert not fail_before_pass(result)

    def test_fail_before_pass_ignores_skipped(self):
        assert not fail_before_pass({"evidence": ["[VERIFY SKIPPED] no sibling test"]})

    def test_strong_pass_requires_strong_label(self):
        assert strong_pass(
            {"evidence": ["[VERIFY PASS] 3 passed, 0 failed (exit 0) (strength=STRONG)"]}
        )
        assert not strong_pass(
            {"evidence": ["[VERIFY PASS] 0 passed, 0 failed (exit 0) (strength=WEAK)"]}
        )
        assert not strong_pass(
            {"evidence": ["[VERIFY FAIL] 0 passed, 1 failed (exit 1) (strength=NONE)"]}
        )

    def test_has_id_prefix_match(self):
        result = {"step_ids": ["memory-recall", "reflect-3", "verify-7"]}
        assert has_id(result, "reflect-")
        assert has_id(result, "verify-")
        assert not has_id(result, "lesson-recall")

    def test_confirm_step_requires_reflect_tool(self):
        # An ordinary verify tool call also has a verify-* id; only the
        # reflect-tagged one is the lesson-promotion step.
        plain_verify = {"step_ids": ["verify-2"], "step_tools": ["verify"]}
        assert not has_confirm_step(plain_verify)
        confirm = {"step_ids": ["reflect-1", "verify-4"],
                   "step_tools": ["reflect", "reflect"]}
        assert has_confirm_step(confirm)

    def test_used_write_tools(self):
        assert used_write_tools({"step_tools": ["read_file", "edit_file"]})
        assert used_write_tools({"step_tools": ["create_file"]})
        assert not used_write_tools({"step_tools": ["read_file", "verify"]})


class TestCheckSemantics:
    def test_hard_failure_fails_run(self):
        check = Check(lenient=True)
        check.hard("x", False, "boom")
        assert not check.passed

    def test_soft_failure_fails_strict_run(self):
        check = Check(lenient=False)
        check.soft("x", False, "llm disobeyed")
        assert not check.passed

    def test_soft_failure_downgraded_in_lenient_run(self):
        check = Check(lenient=True)
        check.soft("x", False, "llm disobeyed")
        check.hard("y", True, "fine")
        assert check.passed
        assert check.results[0]["downgraded"]

    def test_all_green_passes(self):
        check = Check(lenient=False)
        check.hard("a", True, "ok")
        check.soft("b", True, "ok")
        assert check.passed
