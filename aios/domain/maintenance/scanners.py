"""Admitted production scanner implementations for GAGOS maintenance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.application.workspaces.staged import tree_digest

ADMITTED_SCANNER_ID = "deterministic_config_scanner"
ADMITTED_SCANNER_VERSION = "1"


def deterministic_config_scanner(context: Any) -> Sequence[MaintenanceFinding]:
    """Production scanner scanning files in allowed_root for maintenance markers."""
    contract: BoundedScanContract = getattr(context, "contract", context)
    allowed_root = Path(contract.allowed_root).resolve()
    if not allowed_root.exists():
        return ()

    findings: list[MaintenanceFinding] = []
    files_scanned = 0
    total_bytes_scanned = 0
    src_digest = _compute_source_digest(allowed_root)

    # Scan python, markdown, txt, and json files under allowed_root
    target_files = [allowed_root] if allowed_root.is_file() else sorted(allowed_root.rglob("*"))
    for file_path in target_files:
        if file_path.is_dir():
            continue
        rel_parts = file_path.relative_to(allowed_root).parts
        if any(part.startswith(".") or part in ("__pycache__", "venv", ".venv", "node_modules") for part in rel_parts):
            continue

        try:
            rel_path = str(file_path.relative_to(allowed_root)).replace("\\", "/")
            stat = file_path.stat()
        except (ValueError, OSError):
            continue

        if stat.st_size > contract.max_file_bytes:
            continue
        total_bytes_scanned += stat.st_size
        if total_bytes_scanned > contract.max_total_bytes:
            break

        files_scanned += 1
        if files_scanned > contract.max_files:
            break

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        file_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Check for explicit maintenance marker
        if "# DEFECT_MARKER: fix_required" in content or "TODO_MAINTENANCE_DEFECT" in content:
            marker = "# DEFECT_MARKER: fix_required" if "# DEFECT_MARKER: fix_required" in content else "TODO_MAINTENANCE_DEFECT"
            raw_fingerprint_material = f"{ADMITTED_SCANNER_ID}:{rel_path}:{marker}"
            fingerprint = hashlib.sha256(raw_fingerprint_material.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            
            finding = MaintenanceFinding(
                finding_id=f"finding-{fingerprint[:12]}",
                fingerprint=fingerprint,
                scanner_id=ADMITTED_SCANNER_ID,
                scanner_version=ADMITTED_SCANNER_VERSION,
                kind="code_defect",
                severity="HIGH",
                confidence=1.0,
                evidence_quality="DETERMINISTIC",
                target_id=rel_path,
                target_digest=file_digest,
                source_digest=src_digest,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                status="OPEN",
                deterministic_evidence=f"Maintenance marker '{marker}' found in {rel_path}",
            )
            findings.append(finding)
            if len(findings) >= contract.max_findings:
                break

    return tuple(findings)


def get_admitted_scanners() -> dict[str, ScannerAdapter]:
    """Return dictionary of admitted scanner adapters."""
    return {
        ADMITTED_SCANNER_ID: deterministic_config_scanner,
    }


def _compute_source_digest(root: Path) -> str:
    try:
        return tree_digest(root)
    except (OSError, ValueError):
        return hashlib.sha256(str(root).encode("utf-8")).hexdigest()


__all__ = [
    "ADMITTED_SCANNER_ID",
    "ADMITTED_SCANNER_VERSION",
    "deterministic_config_scanner",
    "get_admitted_scanners",
]
