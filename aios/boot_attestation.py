"""Boot attestation module for GAGOS AI-OS.

Computes a SHA-256 Merkle hash of the frozen security spine files and records
it at boot time to detect tampering.  This module READS files in aios/security/
but lives outside that directory — the security spine is FOUNDATION_LOCK frozen.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aios.config import PROJECT_ROOT


def compute_spine_hash(spine_dir: Path) -> str:
    """Compute a SHA-256 Merkle tree hash over all .py files in *spine_dir*.

    Files are sorted by name for determinism.  The Merkle tree is built by
    hashing each file's content individually, then hashing the concatenation
    of all individual file hashes (hex-encoded, in sorted filename order).

    Returns the hex-encoded root hash.
    """
    py_files = sorted(spine_dir.glob("*.py"), key=lambda p: p.name)

    file_hashes: list[str] = []
    for fp in py_files:
        content = fp.read_bytes()
        file_hashes.append(hashlib.sha256(content).hexdigest())

    # Root hash: SHA-256 of the concatenation of all leaf hashes
    combined = "".join(file_hashes).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def verify_spine_integrity(spine_dir: Path, expected_hash: str) -> bool:
    """Compare the current Merkle hash of *spine_dir* to *expected_hash*."""
    current_hash = compute_spine_hash(spine_dir)
    return current_hash == expected_hash


def attest_boot(project_root: Path) -> dict:
    """Run the boot attestation flow.

    1. Compute the current spine hash.
    2. Read the last recorded hash from the JSONL audit log.
    3. Determine integrity status.
    4. Append a new attestation entry to the log.
    5. Return a summary dict.

    Returns
    -------
    dict with keys:
        hash          — current spine Merkle hash (hex)
        previous_hash — last recorded hash (hex) or None on first boot
        integrity     — "valid" | "first_boot" | "TAMPERED"
    """
    spine_dir = project_root / "aios" / "security"
    audit_dir = project_root / ".aios" / "audit"
    log_path = audit_dir / "boot-attestation.jsonl"

    current_hash = compute_spine_hash(spine_dir)

    # Read previous hash from the last line of the attestation log
    previous_hash: Optional[str] = None
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            last_entry = json.loads(lines[-1])
            previous_hash = last_entry.get("spine_hash")

    # Determine integrity
    if previous_hash is None:
        integrity = "first_boot"
    elif current_hash == previous_hash:
        integrity = "valid"
    else:
        integrity = "TAMPERED"

    # Count files hashed
    py_files = sorted(spine_dir.glob("*.py"), key=lambda p: p.name)
    files_hashed = len(py_files)

    # Write attestation entry
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "spine_hash": current_hash,
        "previous_hash": previous_hash,
        "integrity": integrity,
        "files_hashed": files_hashed,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return {
        "hash": current_hash,
        "previous_hash": previous_hash,
        "integrity": integrity,
    }
