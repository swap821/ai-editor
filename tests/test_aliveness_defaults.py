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
    # NOTE: earned autonomy was asserted awake here until 2026-08-17. It moved to
    # test_authority_crossing_arms_stay_opt_in below, for the same reason swarm
    # cloud burst moved out in 2026-08-04 — it crosses a boundary rather than
    # being an aliveness organ, and the two sets have different defaults by
    # design. The boundary it crosses is authority, not privacy.
    # council reasoning: LLM-backed Queen planning (degrades to deterministic)
    assert config.COUNCIL_REASONING is True
    # council origination: chat -> council mission pipeline
    assert config.COUNCIL_ORIGINATION is True
    # cortex bus: cold-path dispatcher for non-authority observations
    assert config.CORTEX_BUS is True
    # NOTE: swarm cloud burst was asserted awake here until 2026-08-04. It moved
    # to test_boundary_crossing_arms_stay_opt_in below — it is an egress path,
    # not an aliveness organ, and the two sets have different defaults by design.


def test_authority_crossing_arms_stay_opt_in() -> None:
    """Aliveness defaults may not hand out authority.

    Earned autonomy auto-approves a write with no human in the loop, which is
    precisely what Invariant II forbids. The capability is unchanged and still
    gated by its evidence floor — what changed on 2026-08-17 is that switching it
    on is now a deliberate act (``AIOS_EARNED_AUTONOMY=1``) rather than the
    default posture. Kept in its own test because the boundary is authority,
    not privacy: locking down egress must not be mistaken for withholding
    authority, or the reverse.
    """
    assert config.EARNED_AUTONOMY_ENABLED is False


def test_boundary_crossing_arms_stay_opt_in() -> None:
    # CRAG's external arms cross the privacy boundary — require explicit config
    assert config.CRAG_EXTERNAL is False
    assert config.CRAG_CLOUD is False
    assert config.CRAG_WEBSEARCH is False
    assert config.CRAG_LLM_JUDGE is False
    # The two router-level egress paths cross the same boundary and are opt-in
    # for the same reason (2026-08-04). They are independent switches: locking
    # down one must not be mistaken for closing the other.
    assert config.ROUTER_CLOUD_TASKS == ()
    assert config.SWARM_CLOUD_BURST_ENABLED is False
