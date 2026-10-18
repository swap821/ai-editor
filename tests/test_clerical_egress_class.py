"""`clerical` is a cloud-egress class the operator may opt into, and nothing more.

§VIII, applied 2026-10-18 (docs/security/PROPOSAL_CLERICAL_EGRESS_CLASS.md;
release/section-viii/2026-10-18-scope-b-and-clerical-egress.md). The proposal's
test plan, items 1 and 3; item 2 is tests/test_guardrails_ignore_dotenv.py,
item 4 is scripts/check_frozen_core.py.
"""

from __future__ import annotations

import pytest

from aios.security import limits


def test_clerical_is_accepted_only_when_the_operator_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_TEST_ROUTER_TASKS", "clerical")
    assert limits._env_router_tasks("AIOS_TEST_ROUTER_TASKS", ()) == ("clerical",)
    monkeypatch.setenv("AIOS_TEST_ROUTER_TASKS", "reasoning, Coding ,clerical")
    assert limits._env_router_tasks("AIOS_TEST_ROUTER_TASKS", ()) == (
        "reasoning",
        "coding",
        "clerical",
    )


def test_it_is_in_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOS_TEST_ROUTER_TASKS", raising=False)
    assert limits._env_router_tasks("AIOS_TEST_ROUTER_TASKS", ()) == ()


def test_a_typo_is_still_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_TEST_ROUTER_TASKS", "clerk,clerica,clerical-x")
    assert limits._env_router_tasks("AIOS_TEST_ROUTER_TASKS", ()) == ()


def test_the_set_grew_by_exactly_one_name() -> None:
    assert limits._VALID_ROUTER_TASKS == frozenset(
        {"coding", "reasoning", "research", "vision", "long_context", "clerical"}
    )
