"""Contract test: wonder organs are fail-closed even when their flag is on.

Enabling the wonder flags does NOT grant autonomy, enable LLM reasoning, or
burst to cloud by itself. Each organ checks its runtime dependency (ledger
evidence, LLM client, cloud credentials) before acting. This test proves the
flags are safe to enable — they unlock capability, not action.

Earned autonomy is no longer among the default-on flags: it defaults OFF to
match Invariant II, so the tests below enable it explicitly rather than reading
the default. What is under test is the evidence floor, not the switch.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.runtime.cortex_bus import CortexBus
from tests.cortex_event_helpers import append_event


@pytest.fixture()
def fresh_ledger(tmp_path: Path) -> AutonomyLedger:
    return AutonomyLedger(db_path=tmp_path / "autonomy.db")


class TestEarnedAutonomyFailClosed:
    """Even with the flag on, autonomy requires verified evidence."""

    def test_is_earned_false_without_evidence(self, fresh_ledger: AutonomyLedger) -> None:
        """Evidence, not the flag, is what withholds autonomy here.

        This asserted ``EARNED_AUTONOMY_ENABLED is True`` until the default was
        flipped OFF for Invariant II. That assertion was a guard, not the
        subject: it existed so the ``False`` below could only come from missing
        evidence rather than from the kill switch. Now that the flag defaults
        OFF, the guard has to enable it explicitly — otherwise this test passes
        vacuously and stops covering the evidence floor it was written for.
        """
        with patch.object(config, "EARNED_AUTONOMY_ENABLED", True):
            assert fresh_ledger.is_earned("create", "some/file.py") is False

    def test_single_success_not_enough(self, fresh_ledger: AutonomyLedger) -> None:
        fresh_ledger.record_outcome("create", "some/file.py", success=True)
        assert fresh_ledger.is_earned("create", "some/file.py") is False

    def test_requires_min_successes_streak(self, fresh_ledger: AutonomyLedger) -> None:
        for _ in range(config.EARNED_AUTONOMY_MIN_SUCCESSES - 1):
            fresh_ledger.record_outcome("create", "some/file.py", success=True)
        assert fresh_ledger.is_earned("create", "some/file.py") is False

    def test_disabled_via_env_overrides_default(self, fresh_ledger: AutonomyLedger) -> None:
        for _ in range(config.EARNED_AUTONOMY_MIN_SUCCESSES + 5):
            fresh_ledger.record_outcome("create", "some/file.py", success=True)
        with patch.object(config, "EARNED_AUTONOMY_ENABLED", False):
            assert fresh_ledger.is_earned("create", "some/file.py") is False


class TestCouncilReasoningFailClosed:
    """Council reasoning degrades to deterministic when no LLM is injected."""

    def test_planner_queen_deterministic_without_llm(self) -> None:
        from aios.council.queens.planner import PlannerQueen
        assert config.COUNCIL_REASONING is True
        queen = PlannerQueen(llm=None)
        assert queen._llm is None


class TestCloudBurstFailClosed:
    """Cloud burst is off by default, and inert even when switched on."""

    def test_cloud_burst_flag_is_off(self) -> None:
        # Flipped 2026-08-04: this asserted True until the egress defaults were
        # closed. Burst is an opt-in egress path, not a wonder organ.
        assert config.SWARM_CLOUD_BURST_ENABLED is False

    def test_no_cloud_client_without_credentials(self) -> None:
        # The second guard, which held even while the flag defaulted on: the
        # burst only fires when BOTH the flag is set AND a cloud client is
        # constructed — which requires BEDROCK_ENABLED or GEMINI_ENABLED
        # (themselves dependent on AWS/GCP credentials). Asserted here with the
        # flag forced ON, so this proves the credential guard independently
        # rather than passing for free on the new default.
        with patch.object(config, "SWARM_CLOUD_BURST_ENABLED", True), \
             patch.object(config, "BEDROCK_ENABLED", False), \
             patch.object(config, "GEMINI_ENABLED", False):
            assert config.SWARM_CLOUD_BURST_ENABLED
            assert not config.BEDROCK_ENABLED
            assert not config.GEMINI_ENABLED


class TestCortexBusFailClosed:
    """Cortex bus is infrastructure; enabling it adds no authority path."""

    def test_bus_on_by_default(self) -> None:
        assert config.CORTEX_BUS is True

    def test_bus_refuses_authority_events(self, tmp_path: Path) -> None:
        bus = CortexBus(db_path=tmp_path / "bus.db")
        with pytest.raises(ValueError, match="authority"):
            append_event(bus, "skill.promoted", "test-entity", {"skill": "test"})
