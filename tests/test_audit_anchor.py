"""Tests for the external audit-anchoring API wrapper (aios/audit_anchor.py)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aios import audit_anchor
from aios.security.audit_logger import ChainStatus


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_anchor, "_DEFAULT_DB", tmp_path / "audit.db")
    monkeypatch.setattr(audit_anchor, "_DEFAULT_DATA_DIR", tmp_path)


_FAKE_ANCHOR = {
    "head_hash": "a" * 64,
    "signature": "sig-hex",
    "key_id": 1,
    "entry_id": 7,
    "timestamp": "2026-01-01T00:00:00+00:00",
}


def test_get_external_anchor(tmp_path: Path) -> None:
    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)) as mock_get:
        result = audit_anchor.get_external_anchor(tmp_path / "audit.db")

    mock_get.assert_called_once()
    assert result["head_hash"] == _FAKE_ANCHOR["head_hash"]
    assert result["signature"] == _FAKE_ANCHOR["signature"]
    assert result["key_id"] == _FAKE_ANCHOR["key_id"]
    assert result["entry_id"] == _FAKE_ANCHOR["entry_id"]
    assert "verified_at" in result
    assert "chain_length" in result
    assert isinstance(result["chain_length"], int)


def test_verify_anchor_matches(tmp_path: Path) -> None:
    valid_status = ChainStatus(valid=True, total_entries=7, head_hash=_FAKE_ANCHOR["head_hash"])
    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)), \
         patch("aios.audit_anchor.verify_chain", return_value=valid_status):
        result = audit_anchor.verify_anchor(_FAKE_ANCHOR["head_hash"], tmp_path / "audit.db")

    assert result["matches"] is True
    assert result["chain_valid"] is True
    assert result["current_hash"] == _FAKE_ANCHOR["head_hash"]
    assert result["expected_hash"] == _FAKE_ANCHOR["head_hash"]
    assert result["anchor"]["head_hash"] == _FAKE_ANCHOR["head_hash"]


def test_verify_anchor_mismatch(tmp_path: Path) -> None:
    valid_status = ChainStatus(valid=True, total_entries=7, head_hash=_FAKE_ANCHOR["head_hash"])
    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)), \
         patch("aios.audit_anchor.verify_chain", return_value=valid_status):
        result = audit_anchor.verify_anchor("b" * 64, tmp_path / "audit.db")

    assert result["matches"] is False
    assert result["chain_valid"] is True
    assert result["current_hash"] == _FAKE_ANCHOR["head_hash"]
    assert result["expected_hash"] == "b" * 64


def test_publish_anchor_success(tmp_path: Path) -> None:
    received: list[dict] = []

    def publisher(anchor: dict) -> None:
        received.append(anchor)

    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)):
        result = audit_anchor.publish_anchor(publisher, tmp_path / "audit.db")

    assert result["published"] is True
    assert len(received) == 1
    assert received[0]["head_hash"] == _FAKE_ANCHOR["head_hash"]


def test_publish_anchor_failure(tmp_path: Path) -> None:
    def bad_publisher(anchor: dict) -> None:
        raise RuntimeError("network unreachable")

    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)):
        result = audit_anchor.publish_anchor(bad_publisher, tmp_path / "audit.db")

    assert result["published"] is False
    assert "network unreachable" in result["error"]


def test_anchor_history(tmp_path: Path) -> None:
    assert audit_anchor.anchor_history(tmp_path / "audit.db") == []

    with patch("aios.audit_anchor.get_anchor", return_value=dict(_FAKE_ANCHOR)):
        audit_anchor.publish_anchor(lambda anchor: None, tmp_path / "audit.db")
        audit_anchor.publish_anchor(lambda anchor: None, tmp_path / "audit.db")

    history = audit_anchor.anchor_history(tmp_path / "audit.db", limit=10)
    assert len(history) == 2
    assert all(entry["published"] is True for entry in history)

    history_file = tmp_path / "anchor_history.jsonl"
    assert history_file.exists()
    lines = history_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["head_hash"] == _FAKE_ANCHOR["head_hash"]

    limited = audit_anchor.anchor_history(tmp_path / "audit.db", limit=1)
    assert len(limited) == 1
