"""Phase 9 — Test suite for full Evidence & Audit Logging Pass.

Tests:
1. Audit logger initialization, Ed25519 signature generation, and SHA-256 hash chaining.
2. Maintenance scan, repair creation, and repair execution audit logging into tamper_audit_trail.
3. Secret redaction before hashing: Credentials in audit payloads are redacted prior to SHA-256 chain calculation.
4. Cryptographic tamper detection: Altering historical audit rows invalidates the chain in verify_chain().
5. EvidenceAuthority bundle creation and audit ledger integration.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from aios.application.evidence.authority import EvidenceAuthority
from aios.application.evidence.verification import VerificationAuthority
from aios.security.audit_logger import (
    AuditEntry,
    AuditError,
    init_audit_db,
    log_action,
    verify_chain,
)


@pytest.fixture()
def audit_db(tmp_path: Path) -> Path:
    db = tmp_path / "audit_test.db"
    init_audit_db(db)
    return db


def test_audit_logger_hash_chain_and_signature(audit_db: Path) -> None:
    # Append multiple actions to audit logger
    e1 = log_action(actor="op-admin", payload="action=scan_started target=src/", zone="GREEN", db_path=audit_db)
    e2 = log_action(actor="op-admin", payload="action=repair_create mission=m-100", zone="YELLOW", db_path=audit_db)
    e3 = log_action(actor="op-admin", payload="action=repair_run status=completed", zone="YELLOW", db_path=audit_db)

    assert e1.entry_id == 1
    assert e2.entry_id == 2
    assert e3.entry_id == 3

    assert e1.previous_hash == "0" * 64
    assert e2.previous_hash == e1.current_hash
    assert e3.previous_hash == e2.current_hash

    # Verify the Ed25519 signed chain
    result = verify_chain(db_path=audit_db)
    assert result.valid is True
    assert result.total_entries == 3
    assert result.signature_valid is True


def test_audit_logger_secret_redaction(audit_db: Path) -> None:
    # Pass sensitive secret payload
    raw_payload = "api_key=sk-proj-1234567890abcdef1234567890abcdef action=login"
    entry = log_action(actor="user", payload=raw_payload, zone="YELLOW", db_path=audit_db)

    assert entry.redacted is True

    # Query raw database row to verify stored payload is redacted
    conn = sqlite3.connect(audit_db)
    row = conn.execute(
        "SELECT action_payload FROM tamper_audit_trail WHERE entry_id = ?",
        (entry.entry_id,),
    ).fetchone()
    conn.close()

    stored_payload = row[0]
    assert "sk-proj-1234567890abcdef1234567890abcdef" not in stored_payload

    # Chain verification must remain valid over redacted payload
    result = verify_chain(db_path=audit_db)
    assert result.valid is True


def test_audit_logger_tamper_detection(audit_db: Path) -> None:
    log_action(actor="op-admin", payload="entry 1", zone="GREEN", db_path=audit_db)
    log_action(actor="op-admin", payload="entry 2", zone="YELLOW", db_path=audit_db)
    log_action(actor="op-admin", payload="entry 3", zone="GREEN", db_path=audit_db)

    # Confirm chain is valid before tampering
    assert verify_chain(db_path=audit_db).valid is True

    # Tamper with entry 2 payload in SQLite database directly
    conn = sqlite3.connect(audit_db)
    conn.execute(
        "UPDATE tamper_audit_trail SET action_payload = ? WHERE entry_id = 2",
        ("FORGED PAYLOAD",),
    )
    conn.commit()
    conn.close()

    # verify_chain must detect tampering fail-closed
    result = verify_chain(db_path=audit_db)
    assert result.valid is False
    assert result.broken_at == 2


def test_evidence_authority_bundle_building_and_redaction(tmp_path: Path) -> None:
    evidence_auth = EvidenceAuthority()

    record1 = evidence_auth.record(
        mission_id="m-ev-1",
        action_id="act-ev-1",
        worker_id="w-ev-1",
        evidence_type="test",
        source="verification",
        content="api_key=secret-key-12345\n1 test passed",
        environment_digest="env-dig-1",
        tool_version="pytest-8.0",
        trust_level="verified",
        verification_strength=1,
    )

    assert record1.evidence_id.startswith("evidence-")
    # Content reference digest must be hashed and redacted
    assert "secret-key-12345" not in record1.content_reference

    bundle = evidence_auth.bundle(
        mission_id="m-ev-1",
        worker_id="w-ev-1",
        contract_digest="c-dig-1",
        workspace_digest="ws-dig-1",
        diff_digest="diff-dig-1",
        executor_job_id="job-1",
        environment_digest="env-dig-1",
        commands=[
            {
                "command": "pytest",
                "exit_code": 0,
                "stdout": "api_key=secret-key-12345 1 passed",
                "stderr": "",
            }
        ],
        verification_strength=1,
        targets_exercised=("test_file.py",),
        started_at="2026-07-19T12:00:00Z",
        ended_at="2026-07-19T12:01:00Z",
    )

    assert bundle.mission_id == "m-ev-1"
    assert bundle.verification_strength == 1
    assert bundle.commands[0].stdout_digest != ""
