"""Contract test: the four foundation layers ship awake; wonder stays gated.

Operator directive (2026-07-02): chemotaxis + reflex + emotion + narrative at
100% — every foundation organ on by default on the hot path — while the
wonder-phase organs (council, swarm, earned autonomy, cloud burst, CRAG's
external/cloud arms) remain explicitly opt-in until their phase begins.

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


def test_wonder_phase_organs_stay_opt_in() -> None:
    # CRAG's boundary-crossing arms never ride along with the local default
    assert config.CRAG_EXTERNAL is False
    assert config.CRAG_CLOUD is False
    assert config.CRAG_WEBSEARCH is False
    assert config.CRAG_LLM_JUDGE is False
    # autonomy is earned, never default
    assert config.EARNED_AUTONOMY_ENABLED is False
    # council reasoning/origination and cloud burst await the wonder phase
    assert config.COUNCIL_REASONING is False
    assert config.COUNCIL_ORIGINATION is False
    assert config.SWARM_CLOUD_BURST_ENABLED is False
    # cortex bus W2: the cold-path dispatcher is opt-in (wonder-phase infra)
    assert config.CORTEX_BUS is False
