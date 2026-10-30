"""Admitted production scanner implementations for GAGOS maintenance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

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
    target_files = (
        [allowed_root] if allowed_root.is_file() else sorted(allowed_root.rglob("*"))
    )
    for file_path in target_files:
        if file_path.is_dir():
            continue
        rel_parts = file_path.relative_to(allowed_root).parts
        if any(
            part.startswith(".")
            or part in ("__pycache__", "venv", ".venv", "node_modules")
            for part in rel_parts
        ):
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
        if (
            "# DEFECT_MARKER: fix_required" in content
            or "TODO_MAINTENANCE_DEFECT" in content
        ):
            marker = (
                "# DEFECT_MARKER: fix_required"
                if "# DEFECT_MARKER: fix_required" in content
                else "TODO_MAINTENANCE_DEFECT"
            )
            raw_fingerprint_material = f"{ADMITTED_SCANNER_ID}:{rel_path}:{marker}"
            fingerprint = hashlib.sha256(
                raw_fingerprint_material.encode("utf-8")
            ).hexdigest()
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


VULTURE_DEAD_IMPORT_SCANNER_ID = "vulture_dead_imports"
VULTURE_DEAD_IMPORT_SCANNER_VERSION = "1"
PROJECT_ROOT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")


def vulture_dead_import_scanner(context: Any) -> Sequence[MaintenanceFinding]:
    """The vulture's dead imports as maintenance findings: one finding per file.

    Added 2026-10-12 for GAGOS's first self-maintenance mission. The rule is
    the vulture's own (aios/maintenance/dead_imports.py), the one the repair
    operation REMOVE_DEAD_IMPORTS_V1 removes by -- so a repair can never
    delete what this scanner did not call dead.

    PROJECT-ROOTED. An import is alive when any file of the project takes it
    (tests patch ``main.scan_and_redact``), so a scan rooted in a subdirectory
    would call live re-exports dead. The contract's allowed_root must
    therefore be a project root; anything else fails the scan. Every read --
    the cross-file index's included -- goes through the bounded context, so
    the contract's file, byte and deadline limits hold, and a project larger
    than them fails the scan instead of returning a partial answer.

    The context's ``target_id`` narrows what is REPORTED (a rescan of the
    repaired file), never what is read.
    """
    from aios.domain.maintenance.service import BoundedScanContext
    from aios.maintenance.dead_imports import ExternalImportIndex, python_files

    if not isinstance(context, BoundedScanContext):
        raise ValueError("the dead-import scanner reads only through a bounded context")
    root = context.root
    if not root.is_dir() or not any((root / m).is_file() for m in PROJECT_ROOT_MARKERS):
        raise ValueError(
            "the dead-import scanner must be rooted at a project root "
            f"({' / '.join(PROJECT_ROOT_MARKERS)}): importers outside a subtree "
            "are invisible from inside it"
        )

    texts: dict[Path, str] = {}

    def read(path: Path) -> str:
        if path not in texts:
            texts[path] = context.read_text(path.relative_to(root))
        return texts[path]

    sources = python_files(root)
    target = (context.target_id or "").replace("\\", "/").strip("/")
    if target in ("", "."):
        reported = sources
    else:
        wanted = (root / target).resolve()
        try:
            wanted.relative_to(root)
        except ValueError as exc:
            raise ValueError("scan target escapes the project root") from exc
        reported = [p for p in sources if p == wanted or wanted in p.parents]

    index = ExternalImportIndex(root, read=read)
    for path in sources:  # read everything up front: the bounds apply to all of it
        read(path)
    source_digest = hashlib.sha256(
        "".join(
            f"{p.relative_to(root).as_posix()}:"
            f"{hashlib.sha256(texts[p].encode('utf-8')).hexdigest()}\n"
            for p in sources
        ).encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    findings: list[MaintenanceFinding] = []
    for path in reported:
        text = texts[path]
        try:
            dead = index.dead_in(path, text)  # the vulture's own judgement
        except SyntaxError:
            continue  # not this scanner's finding
        if not dead:
            continue
        rel = path.relative_to(root).as_posix()
        names = sorted(dead)
        fingerprint = hashlib.sha256(
            f"{VULTURE_DEAD_IMPORT_SCANNER_ID}:{rel}:dead_imports".encode("utf-8")
        ).hexdigest()
        findings.append(
            MaintenanceFinding(
                finding_id=f"finding-{fingerprint[:12]}",
                fingerprint=fingerprint,
                scanner_id=VULTURE_DEAD_IMPORT_SCANNER_ID,
                scanner_version=VULTURE_DEAD_IMPORT_SCANNER_VERSION,
                kind="dead_import",
                severity="LOW",
                confidence=1.0,
                evidence_quality="DETERMINISTIC",
                target_id=rel,
                target_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                source_digest=source_digest,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                status="OPEN",
                deterministic_evidence=(
                    f"{len(names)} dead import(s) in {rel}: {', '.join(names)}"
                ),
            )
        )
    return tuple(findings)


# Read by the maintenance routes: scan from the project root, report on the target.
vulture_dead_import_scanner.project_rooted = True  # type: ignore[attr-defined]


FRONTEND_UNUSED_IMPORT_SCANNER_ID = "frontend_unused_imports"
FRONTEND_UNUSED_IMPORT_SCANNER_VERSION = "1"
#: The lab-to-product port's manifest: the product files it owns.
SUPERBRAIN_PORT_MANIFEST = "frontend/superbrain-source.json"


def frontend_unused_import_scanner(context: Any) -> Sequence[MaintenanceFinding]:
    """Unused imports in GAGOS's own frontend: one finding per file.

    Added 2026-10-30 for GAGOS's daily frontend worker. The rule is
    ``aios/maintenance/frontend_imports.py``, the one the repair operation
    REMOVE_UNUSED_FRONTEND_IMPORTS_V1 removes by, and only names that operation
    CAN remove are reported -- so every finding is repairable and a repair can
    never remove what was not reported.

    Files the lab-to-product port owns (``frontend/superbrain-source.json``)
    are never reported: an edit there is overwritten by the next port, and the
    port refuses a product it did not write ("Product drift"). Their fixes
    belong in the lab.

    PROJECT-ROOTED like the dead-import scanner, so a finding's ``target_id``
    is relative to the project (the staged workspace a repair runs in); every
    read goes through the bounded context. ``target_id`` narrows what is
    reported (a rescan of the repaired file), never what is read.
    """
    import json

    from aios.domain.maintenance.service import BoundedScanContext
    from aios.maintenance.frontend_imports import (
        FrontendImportError,
        frontend_files,
        remove_unused_frontend_imports,
    )

    if not isinstance(context, BoundedScanContext):
        raise ValueError("the frontend scanner reads only through a bounded context")
    root = context.root
    if not (root / "frontend" / "src").is_dir():
        raise ValueError(
            "the frontend scanner must be rooted at a project root with frontend/src"
        )
    managed: set[str] = set()
    if (root / SUPERBRAIN_PORT_MANIFEST).is_file():
        manifest = json.loads(context.read_text(SUPERBRAIN_PORT_MANIFEST))
        managed = {
            f"frontend/src/superbrain/{path}" for path in manifest.get("files", {})
        }
    target = (context.target_id or "").replace("\\", "/").strip("/")
    texts: dict[str, str] = {}
    for path in frontend_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in managed:
            continue
        if (
            target not in ("", ".")
            and rel != target
            and not rel.startswith(target.rstrip("/") + "/")
        ):
            continue
        texts[rel] = context.read_text(rel)
    source_digest = hashlib.sha256(
        "".join(
            f"{rel}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}\n"
            for rel, text in sorted(texts.items())
        ).encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    findings: list[MaintenanceFinding] = []
    for rel, text in sorted(texts.items()):
        try:
            removable = remove_unused_frontend_imports(
                text, suffix=Path(rel).suffix
            ).removed
        except FrontendImportError:
            continue  # a file the rule cannot follow is not this scanner's finding
        if not removable:
            continue
        fingerprint = hashlib.sha256(
            f"{FRONTEND_UNUSED_IMPORT_SCANNER_ID}:{rel}:unused_imports".encode("utf-8")
        ).hexdigest()
        findings.append(
            MaintenanceFinding(
                finding_id=f"finding-{fingerprint[:12]}",
                fingerprint=fingerprint,
                scanner_id=FRONTEND_UNUSED_IMPORT_SCANNER_ID,
                scanner_version=FRONTEND_UNUSED_IMPORT_SCANNER_VERSION,
                kind="unused_import",
                severity="LOW",
                confidence=1.0,
                evidence_quality="DETERMINISTIC",
                target_id=rel,
                target_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                source_digest=source_digest,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                status="OPEN",
                deterministic_evidence=(
                    f"{len(removable)} unused import(s) in {rel}: "
                    f"{', '.join(removable)}"
                ),
            )
        )
    return tuple(findings)


frontend_unused_import_scanner.project_rooted = True  # type: ignore[attr-defined]


def get_admitted_scanners() -> dict[str, Callable[[Any], Sequence[MaintenanceFinding]]]:
    """Return dictionary of admitted scanner adapters."""
    return {
        ADMITTED_SCANNER_ID: deterministic_config_scanner,
        VULTURE_DEAD_IMPORT_SCANNER_ID: vulture_dead_import_scanner,
        FRONTEND_UNUSED_IMPORT_SCANNER_ID: frontend_unused_import_scanner,
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
