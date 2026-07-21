"""Contract test: all five layers ship awake; only boundary-crossing arms stay gated.

Operator directive (2026-07-04): the wonder phase begins. Earned autonomy,
council reasoning/origination, cloud burst, and the cortex bus join the
foundation layers as default-on. They are fail-closed by design: each checks
for its runtime dependency (LLM client, cloud credentials, earned evidence)
before acting, so flipping the flag on is safe — it enables the *capability*,
not the *action*.

Only CRAG's external/cloud arms (which cross the privacy boundary to external
services) remain explicitly opt-in — they require operator-configured endpoints.

These assertions pin that posture so a stray default flip in either direction
is caught by the gate, not discovered in production. They read the config
module as imported (env-driven): CI and fresh installs run with none of these
AIOS_* variables set.
"""
from __future__ import annotations

from aios import config


def test_foundation_layers_default_awake() -> None:
    # chemotaxis/narrative — corrective recall refinement (local, deterministic)
    assert config.CRAG is True
    # chemotaxis — alignment interpretation feeds the confidence gate
    assert config.INTERPRET_ALIGNMENT is True
    # emotion — failures reflect into behavior; gate threshold is calibrated
    assert config.REFLECT_ON_FAILURE is True
    assert 0.0 < config.CONFIDENCE_THRESHOLD < 1.0
    # narrative — self-model recall and organic curriculum learning
    assert config.NARRATIVE_SELF_ENABLED is True
    assert config.CURRICULUM_FUZZY is True
    assert 0.0 <= config.CURRICULUM_FUZZY_THRESHOLD <= 1.0
    # narrative — supervised memory formation (quarantined proposals)
    assert config.FACTS_AUTO_EXTRACT is True
    assert config.FACTS_AUTO_EXTRACT_MAX_PER_TURN >= 1
    # narrative — chat turns are indexed into memory
    assert config.INDEX_CHAT is True


def test_wonder_phase_organs_default_awake() -> None:
    # earned autonomy: after N verified successes, auto-approve without pausing
    assert config.EARNED_AUTONOMY_ENABLED is True
    # council reasoning: LLM-backed Queen planning (degrades to deterministic)
    assert config.COUNCIL_REASONING is True
    # council origination: chat -> council mission pipeline
    assert config.COUNCIL_ORIGINATION is True
    # cloud burst: swarm subtasks can burst to cloud providers
    assert config.SWARM_CLOUD_BURST_ENABLED is True
    # cortex bus: cold-path dispatcher for non-authority observations
    assert config.CORTEX_BUS is True


def test_boundary_crossing_arms_stay_opt_in() -> None:
    # CRAG's external arms cross the privacy boundary — require explicit config
    assert config.CRAG_EXTERNAL is False
    assert config.CRAG_CLOUD is False
    assert config.CRAG_WEBSEARCH is False
    assert config.CRAG_LLM_JUDGE is False
