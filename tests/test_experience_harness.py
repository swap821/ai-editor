"""Tests for the automated experience harness tools.

These test the harness logic (domain selection, file reset, event parsing)
without requiring a running backend — the actual supervised-loop integration
is tested by running the tools against a live server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestExperienceAccumulator:
    def test_domains_are_populated(self):
        from tools.experience_accumulator import DOMAINS
        assert len(DOMAINS) >= 4
        for domain, tasks in DOMAINS.items():
            assert isinstance(domain, str)
            assert len(tasks) >= 1
            for task in tasks:
                assert "prompt" in task
                assert "files" in task
                assert len(task["files"]) >= 1

    def test_all_prompts_are_unique(self):
        from tools.experience_accumulator import DOMAINS
        all_prompts = [
            task["prompt"]
            for tasks in DOMAINS.values()
            for task in tasks
        ]
        assert len(all_prompts) == len(set(all_prompts))

    def test_all_files_in_training_ground(self):
        from tools.experience_accumulator import DOMAINS
        from aios.probe_common import ALLOWED_FILE_RE
        for domain, tasks in DOMAINS.items():
            for task in tasks:
                for f in task["files"]:
                    assert ALLOWED_FILE_RE.match(f), f"{domain}: {f} not in training_ground"

    def test_pick_sessions_limits_count(self):
        from tools.experience_accumulator import pick_sessions
        sessions = pick_sessions(None, 3)
        assert len(sessions) == 3
        for s in sessions:
            assert "domain" in s
            assert "prompt" in s

    def test_pick_sessions_filters_domain(self):
        from tools.experience_accumulator import pick_sessions
        sessions = pick_sessions("coding", 100)
        for s in sessions:
            assert s["domain"] == "coding"

    def test_pick_sessions_unknown_domain_returns_all(self):
        from tools.experience_accumulator import pick_sessions
        sessions = pick_sessions("nonexistent", 3)
        assert len(sessions) == 3

    def test_reset_files_only_allowed(self, tmp_path):
        from tools.experience_accumulator import reset_files, ROOT
        safe = "training_ground/test_file.py"
        unsafe = "aios/config.py"
        with patch.object(
            sys.modules["tools.experience_accumulator"], "ROOT", tmp_path
        ):
            (tmp_path / "training_ground").mkdir()
            target = tmp_path / "training_ground" / "test_file.py"
            target.write_text("x")
            reset_files([safe, unsafe])
            assert not target.exists()


class TestGoldenMissionRunner:
    def test_missions_are_populated(self):
        from tools.golden_mission_runner import MISSIONS
        assert len(MISSIONS) >= 3
        for name, mission in MISSIONS.items():
            assert "description" in mission
            assert "steps" in mission
            assert len(mission["steps"]) >= 1
            for step in mission["steps"]:
                assert "prompt" in step
                assert "expect" in step
                assert step["expect"] in ("verified_success", "verified_failure")

    def test_all_step_files_in_training_ground(self):
        from tools.golden_mission_runner import MISSIONS
        from aios.probe_common import ALLOWED_FILE_RE
        for name, mission in MISSIONS.items():
            for step in mission["steps"]:
                for f in step.get("files", []):
                    assert ALLOWED_FILE_RE.match(f), f"{name}: {f} not in training_ground"

    def test_all_prompts_unique_within_mission(self):
        from tools.golden_mission_runner import MISSIONS
        for name, mission in MISSIONS.items():
            prompts = [s["prompt"] for s in mission["steps"]]
            assert len(prompts) == len(set(prompts)), f"duplicate prompts in {name}"


class TestEnduranceTester:
    def test_prompts_are_populated(self):
        from tools.endurance_tester import ENDURANCE_PROMPTS
        assert len(ENDURANCE_PROMPTS) >= 5
        for task in ENDURANCE_PROMPTS:
            assert "prompt" in task
            assert "files" in task

    def test_all_files_in_training_ground(self):
        from tools.endurance_tester import ENDURANCE_PROMPTS
        from aios.probe_common import ALLOWED_FILE_RE
        for task in ENDURANCE_PROMPTS:
            for f in task["files"]:
                assert ALLOWED_FILE_RE.match(f), f"{f} not in training_ground"

    def test_prompts_are_unique(self):
        from tools.endurance_tester import ENDURANCE_PROMPTS
        prompts = [t["prompt"] for t in ENDURANCE_PROMPTS]
        assert len(prompts) == len(set(prompts))


class TestSSEParsing:
    """Verify the SSE parser shared across all three harnesses."""

    def _make_sse_response(self, lines: list[str]):
        """Create a mock requests.Response with iter_lines."""
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        return mock_resp

    def test_parse_sse_basic(self):
        from tools.experience_accumulator import parse_sse
        lines = [
            "event:step",
            'data:{"type":"tool_call","output":"hello"}',
            "",
            "event:done",
            "data:{}",
            "",
        ]
        resp = self._make_sse_response(lines)
        events = list(parse_sse(resp))
        assert len(events) == 2
        assert events[0][0] == "step"
        assert events[0][1]["output"] == "hello"
        assert events[1][0] == "done"

    def test_parse_sse_handles_trailing_event(self):
        from tools.experience_accumulator import parse_sse
        lines = [
            "event:text_chunk",
            'data:{"text":"hi"}',
        ]
        resp = self._make_sse_response(lines)
        events = list(parse_sse(resp))
        assert len(events) == 1
        assert events[0][1]["text"] == "hi"


class TestAllowlistChecking:
    def test_creation_allowed(self):
        from tools.experience_accumulator import check_allowlist
        ok, why = check_allowlist({
            "input": {"creations": [{"filepath": "training_ground/test.py"}]}
        })
        assert ok

    def test_creation_denied_outside_sandbox(self):
        from tools.experience_accumulator import check_allowlist
        ok, why = check_allowlist({
            "input": {"creations": [{"filepath": "aios/config.py"}]}
        })
        assert not ok
        assert "allowlist" in why

    def test_command_allowed(self):
        from tools.experience_accumulator import check_allowlist
        ok, why = check_allowlist({
            "input": {"commands": ["pytest training_ground/test.py -q"]}
        })
        assert ok

    def test_command_denied(self):
        from tools.experience_accumulator import check_allowlist
        ok, why = check_allowlist({
            "input": {"commands": ["rm -rf /"]}
        })
        assert not ok
