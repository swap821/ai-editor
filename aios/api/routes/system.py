"""System/observability routes: liveness, metrics, intent preview, onboarding,
security classification, and audit-chain verification.

Extracted from ``aios/api/main.py`` (monolith split tranche 2, 2026-07-06).
Dependency providers come from ``aios.api.deps`` — the SAME function objects
``main`` re-exports, so ``app.dependency_overrides`` keyed on either import
path keep working.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.api.deps import (
    get_approval_store,
    get_autonomy,
    get_development_tracker,
    get_policy_kernel,
)
from aios.core.approvals import ApprovalStore
from aios.core.autonomy import AutonomyLedger
from aios.core.metrics import CONTENT_TYPE_LATEST, generate_latest, get_collector
from aios.logging_config import get_logger
from aios.memory.db import get_connection
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.security.audit_logger import init_audit_db, log_action, verify_chain
from aios.security.gateway import classify

logger = get_logger(__name__)

router = APIRouter()

#: Process-wide metrics collector (get_collector() returns the module singleton
#: from aios.core.metrics, so this is the SAME object main's middleware uses).
_METRICS = get_collector()

#: Stateless DB wrapper over the shared episodic store (same DB as main's
#: ``_EPISODIC``; every call opens a fresh connection).
_EPISODIC = EpisodicMemory()


# --------------------------------------------------------------------------- #
# Request/response models
# --------------------------------------------------------------------------- #
class ClassifyRequest(BaseModel):
    """Body for ``/security/classify``."""

    command: str = Field(..., description="Action payload to classify.")


class IntentPreviewRequest(BaseModel):
    """Body for ``/api/v1/intent/preview`` — a lightweight rule-based prediction
    of what the operator is about to ask, so the UI can hint the dock before the
    turn is even sent. No LLM call; deterministic and cheap."""

    text: str = Field(..., max_length=2000, description="Operator's current draft.")


class IntentPreviewResponse(BaseModel):
    """Predicted intent class for the command dock."""

    intent: str = Field(..., description="chat | code | browse | swarm | command")
    confidence: float = Field(..., ge=0, le=1)
    tool: Optional[str] = Field(None, description="Primary tool if intent is actionable.")


class OnboardingStateResponse(BaseModel):
    """Read-only view of which product milestones the operator has reached."""

    firstDirective: bool
    firstApproval: bool
    firstVerify: bool
    firstCloudRoute: bool
    firstAutonomy: bool


# --------------------------------------------------------------------------- #
# Liveness + metrics
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok", "version": aios.__version__}


@router.get("/metrics")
def metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> Response:
    """Prometheus scrapable operational metrics."""
    _METRICS.update(
        tracker.summary(),
        approvals.grant_count(),
        autonomy.earned_count(),
        audit_db_path=config.AUDIT_DB_PATH,
    )
    return Response(
        content=generate_latest(_METRICS.registry),
        media_type=CONTENT_TYPE_LATEST,
    )


# --------------------------------------------------------------------------- #
# Intent preview
# --------------------------------------------------------------------------- #
def _classify_intent(text: str) -> IntentPreviewResponse:
    """Rule-based intent preview for the command dock."""
    t = text.lower().strip()
    if not t:
        return IntentPreviewResponse(intent="chat", confidence=1.0, tool=None)
    if re.search(r"https?://|^(browse|search|look\s+up)\b", t):
        return IntentPreviewResponse(intent="browse", confidence=0.92, tool="browse")
    if re.search(r"\b(swarm|workers|plan\s+(out|it)|decompose|multi-agent)\b", t):
        return IntentPreviewResponse(intent="swarm", confidence=0.9, tool="swarm")
    if re.match(r"^(run|execute|install|pip|npm|git|python|bash|sh)\b", t):
        return IntentPreviewResponse(intent="command", confidence=0.85, tool="execute")
    if re.match(r"^(write|build|create|make|code|implement|fix|add|generate)\b", t):
        return IntentPreviewResponse(intent="code", confidence=0.9, tool="edit_file")
    return IntentPreviewResponse(intent="chat", confidence=0.8, tool=None)


@router.post("/api/v1/intent/preview")
def intent_preview(req: IntentPreviewRequest) -> IntentPreviewResponse:
    """Return a cheap, deterministic intent preview for the current draft."""
    return _classify_intent(req.text)


# --------------------------------------------------------------------------- #
# Onboarding milestones
# --------------------------------------------------------------------------- #
def _has_any_approval_grant(store: ApprovalStore) -> bool:
    """True if any approval has ever been redeemed (cross-session)."""
    if store.db_path is not None:
        with store._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM approval_grants").fetchone()
            return int(row["n"]) > 0
    with store._lock:
        return any(store._grants.values())


def _has_verified_success() -> bool:
    """True if any development event has outcome verified_success."""
    with get_connection(config.MEMORY_DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM development_events WHERE outcome = ?",
            ("verified_success",),
        ).fetchone()
        return int(row["n"]) > 0


def _has_cloud_route() -> bool:
    """True if a cloud-route audit entry has been recorded."""
    init_audit_db(config.AUDIT_DB_PATH)
    conn = sqlite3.connect(str(config.AUDIT_DB_PATH), timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tamper_audit_trail WHERE actor = ?",
            ("cloud-route",),
        ).fetchone()
        return int(row["n"]) > 0
    finally:
        conn.close()


@router.get("/api/v1/onboarding/state")
def onboarding_state(
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> OnboardingStateResponse:
    """Return which first-run milestones have been reached."""
    ledger = autonomy.ledger_map()
    return OnboardingStateResponse(
        firstDirective=_EPISODIC.count(None) > 0,
        firstApproval=_has_any_approval_grant(approvals),
        firstVerify=_has_verified_success(),
        firstCloudRoute=_has_cloud_route(),
        firstAutonomy=ledger["summary"]["earned"] > 0,
    )


# --------------------------------------------------------------------------- #
# Security classification + audit-chain verification
# --------------------------------------------------------------------------- #
@router.post("/api/v1/security/classify")
def security_classify(req: ClassifyRequest) -> dict[str, Any]:
    """Deterministic, fail-closed security-zone classification."""
    result = classify(req.command)
    return {
        "zone": result.zone.value,
        "confidence": result.confidence,
        "reason": result.reason,
    }


@router.get("/api/v1/audit/verify")
def audit_verify(from_entry: int = 1, to_entry: Optional[int] = None) -> dict[str, Any]:
    """Verify the tamper-evident audit hash chain over an optional id range."""
    status = verify_chain(from_id=from_entry, to_id=to_entry)
    if not status.valid:
        logger.critical(
            "Audit hash-chain verification failed",
            broken_at=status.broken_at,
            reason=status.reason,
            total_entries=status.total_entries,
        )
        _METRICS.record_audit_verify_failure()
    return asdict(status)


# --------------------------------------------------------------------------- #
# System config + restart
# --------------------------------------------------------------------------- #

#: Real, persisted operator-facing settings — provider/autonomy/theme.
_SETTINGS_PATH = config.DATA_DIR / "system_settings.json"
_DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "Ollama",
    "autonomy": True,
}


class SystemConfigRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    autonomy: bool


def _read_settings() -> dict[str, Any]:
    if not _SETTINGS_PATH.exists():
        return dict(_DEFAULT_SETTINGS)
    try:
        return {**_DEFAULT_SETTINGS, **json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_SETTINGS)


@router.get("/api/v1/system/config")
def get_system_config() -> dict[str, Any]:
    """Return the real, currently-persisted operator settings merged with env."""
    db_settings = _read_settings()
    
    # Determine autonomy source and effective value
    autonomy_in_env = "AIOS_EARNED_AUTONOMY" in os.environ
    autonomy_val = config.EARNED_AUTONOMY_ENABLED if autonomy_in_env else db_settings.get("autonomy", True)
    
    # Determine provider source and effective value
    # We check if cloud tasks are enabled, etc. For simplicity, since provider is usually
    # controlled by AIOS_ROUTER_PREFER_LOCAL or AIOS_LLM_MODEL, we can just check if
    # the environment imposes a specific provider, or assume DB if no explicit override.
    # Currently, UI implies it's controlled by env. We'll mark it as env if AIOS_LLM_MODEL exists.
    provider_in_env = any(k in os.environ for k in ("AIOS_LLM_MODEL", "AIOS_BEDROCK_MODEL", "AIOS_GEMINI_MODEL"))
    provider_val = db_settings.get("provider", "Ollama")
    
    return {
        "provider": provider_val,
        "provider_source": "env" if provider_in_env else "db",
        "autonomy": autonomy_val,
        "autonomy_source": "env" if autonomy_in_env else "db"
    }


@router.get("/api/v1/system/runtime-profile")
def get_runtime_profile() -> dict[str, Any]:
    """Return the active runtime profile and its resolved decisions.

    Read-only surface: no mutation endpoint is exposed in this slice. The active
    profile is selected by ``AIOS_RUNTIME_PROFILE`` (or persisted state) and
    enforced by ``PolicyKernel``.
    """
    return get_policy_kernel().runtime_profile_decisions()


@router.post("/api/v1/system/config")
def set_system_config(req: SystemConfigRequest) -> dict[str, Any]:
    """Persist operator settings to disk, ignoring env-hardcoded overrides."""
    current = get_system_config()
    payload = req.model_dump()
    
    # Ignore attempts to persist if environmentally hardcoded
    if current["provider_source"] == "env":
        payload["provider"] = current["provider"]
    if current["autonomy_source"] == "env":
        payload["autonomy"] = current["autonomy"]
        
    _SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log_action("operator", f"updated system config: {payload}", "YELLOW")
    return {"status": "saved", **payload}


class SystemRestartRequest(BaseModel):
    confirm: bool = Field(False, description="Must be explicitly true; this restarts the live server process.")


def _reexec_after_delay(delay_seconds: float) -> None:
    """Re-exec the current process image after *delay_seconds*.

    Runs in a daemon thread so the HTTP response for this request has time
    to flush to the client before the process is replaced. ``os.execv``
    replaces the process image IN PLACE (same PID) — the same technique
    used to reload a service inside a container without the container
    itself restarting.

    MUST re-invoke with an explicit ``-m aios``, not
    ``[sys.executable] + sys.argv``: under ``python -m aios``, Python's
    runpy sets ``sys.argv[0]`` to the resolved *path* of
    ``aios/__main__.py``, not a literal ``-m aios`` token. Re-execing that
    path directly (``python aios/__main__.py``) is normal script execution,
    which sets ``sys.path[0]`` to ``aios/`` itself rather than the project
    root — breaking ``aios/__main__.py``'s own ``from aios import config``
    with ``ModuleNotFoundError`` (verified: this was shipped broken and
    would crash the server on every restart click, with no supervisor to
    bring it back on the documented bare-shell launch path). ``sys.argv[1:]``
    is unaffected by how argv[0] degrades — it always holds just the real
    CLI flags (e.g. ``--reload``) — so rebuilding as
    ``[sys.executable, "-m", "aios"] + sys.argv[1:]`` reproduces the
    original ``-m aios <flags>`` invocation exactly, faithful whether
    launched via ``python -m aios`` or Docker's ``CMD ["python", "-m",
    "aios"]`` (verified empirically: sys.argv[1:] correctly holds only the
    trailing flags under -m launch, confirmed with a throwaway package).
    """
    time.sleep(delay_seconds)
    os.execv(sys.executable, [sys.executable, "-m", "aios"] + sys.argv[1:])


@router.post("/api/v1/system/restart")
def restart_system(req: SystemRestartRequest) -> dict[str, Any]:
    """Restart the live backend process.

    Fail-closed on the confirmation flag (ConstitutionEnforcer.check_command
    is for classifying real shell commands against gateway's allowlist, not
    abstract operator actions — using it here would permanently 403 this
    endpoint, since "restart" isn't and shouldn't be an auto-execute shell
    command). Restarting drops every in-flight request and in-memory-only
    state; anything durable is already on disk (SQLite/JSON stores), so this
    is a clean restart, not a reset.
    """
    if not req.confirm:
        raise HTTPException(status_code=422, detail="confirm must be true to restart the server")

    log_action("operator", "restarting server process (self-exec)", "RED")
    threading.Thread(target=_reexec_after_delay, args=(0.5,), daemon=True).start()
    return {"status": "restarting", "etaSeconds": 0.5}
