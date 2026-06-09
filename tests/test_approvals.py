from __future__ import annotations

import pytest

from aios.core.approvals import ApprovalError, ApprovalStore


def test_approval_token_is_exact_session_bound_and_single_use() -> None:
    store = ApprovalStore(timeout_ms=1000)
    token = store.issue("edit", {"filepath": "x.txt", "content": "x"}, "s1")

    with pytest.raises(ApprovalError, match="different session"):
        store.consume(token, "s2")
    with pytest.raises(ApprovalError, match="already used"):
        store.consume(token, "s1")


def test_approval_token_expires() -> None:
    now = [10.0]
    store = ApprovalStore(timeout_ms=100, clock=lambda: now[0])
    token = store.issue("command", {"command": "echo ok"}, "s1")
    now[0] = 10.2

    with pytest.raises(ApprovalError, match="expired"):
        store.consume(token, "s1")


def test_redeemed_grant_expires() -> None:
    now = [10.0]
    store = ApprovalStore(timeout_ms=100, clock=lambda: now[0])
    token = store.issue("command", {"command": "echo ok"}, "s1")
    store.redeem(token, "s1")
    assert len(store.grants("s1")) == 1

    now[0] = 10.2
    assert store.grants("s1") == []
