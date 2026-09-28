"""Test helpers for recall tests whose subject is NOT provenance.

Since plan Phase 3c the live semantic adapter admits a retrieved memory only if
its provenance verifies (``tests/test_phase3c_recall_gate.py``). Tests of CRAG,
of the prompt's formatting, and of the Phase 0b unverified-chat withholding
replace retrieval with synthetic hits that have no database rows at all, so the
gate rightly refuses every one of them. Those tests switch the gate off, by
name, through this helper: what they measure is downstream of it.
"""

from __future__ import annotations

from typing import Any


def ungate_semantic_recall(monkeypatch: Any) -> None:
    """Remove the provenance gate from the process authority's semantic adapter."""
    from aios.api.deps import get_memory_authority

    monkeypatch.setattr(get_memory_authority().adapters["semantic"], "gate", None)
