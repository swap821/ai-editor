"""Read-only production posture report for the local control plane."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aios import config
from aios.security.audit_logger import verify_chain

#: A backup older than this is reported as a warning, never fatal -- staleness
#: is a soft operational signal, not proof the backup is unusable.
BACKUP_STALE_AFTER_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    message: str
    required: bool


@dataclass(frozen=True, slots=True)
class DoctorReport:
    profile: str
    ok: bool
    checks: tuple[DoctorCheck, ...]
    disabled_capabilities: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "ok": self.ok,
            "checks": [asdict(check) for check in self.checks],
            "disabled_capabilities": list(self.disabled_capabilities),
            "warnings": list(self.warnings),
        }


def _check(
    name: str,
    passed: bool,
    message: str,
    *,
    required: bool,
) -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status="measured" if passed else ("fatal" if required else "warning"),
        message=message,
        required=required,
    )


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".gagos-doctor-probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _audit_check(*, production: bool) -> DoctorCheck:
    if not config.AUDIT_DB_PATH.exists():
        return _check(
            "audit_integrity",
            False,
            "audit database is not initialized",
            required=production,
        )
    try:
        status = verify_chain(db_path=config.AUDIT_DB_PATH)
    except Exception as exc:  # noqa: BLE001 - doctor must report, not crash
        return _check(
            "audit_integrity",
            False,
            f"audit verification unavailable: {exc}",
            required=True,
        )
    return _check(
        "audit_integrity",
        bool(status.valid),
        "audit hash chain verified"
        if status.valid
        else "audit hash chain failed verification",
        required=True,
    )


def newest_backup_age_seconds(backup_dir: Path) -> float | None:
    """Age of the most recent `gagos-*.tar.gz` archive in *backup_dir*, or
    `None` if the directory or an archive doesn't exist. Shared by
    `_backup_check` (reporting) and the CLI's `backup create --if-stale`
    (deciding whether a scheduled/cron invocation should actually run) so
    both use one definition of "stale"."""
    if not backup_dir.exists():
        return None
    backups = sorted(backup_dir.glob("gagos-*.tar.gz"))
    if not backups:
        return None
    newest = max(backups, key=lambda path: path.stat().st_mtime)
    return datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime


def _backup_check(*, production: bool, backup_dir: Path) -> DoctorCheck:
    """Existence is `required=production` (matching `executor`/`operator_token`'s
    dev-vs-production severity split); staleness is always a warning, never
    fatal -- a backup's age past the threshold is a soft operational signal,
    not proof the archive itself is unusable."""
    if not backup_dir.exists():
        return _check(
            "backup_freshness",
            False,
            f"no backup directory found at {backup_dir}",
            required=production,
        )
    age_seconds = newest_backup_age_seconds(backup_dir)
    if age_seconds is None:
        return _check(
            "backup_freshness",
            False,
            f"no backup archive found in {backup_dir}",
            required=production,
        )
    newest = max(
        backup_dir.glob("gagos-*.tar.gz"), key=lambda path: path.stat().st_mtime
    )
    if age_seconds > BACKUP_STALE_AFTER_SECONDS:
        age_days = int(age_seconds // 86400)
        return _check(
            "backup_freshness",
            False,
            f"most recent backup ({newest.name}) is {age_days} day(s) old",
            required=False,
        )
    return _check(
        "backup_freshness",
        True,
        f"most recent backup is {newest.name}",
        required=False,
    )


def _model_runtime_check(
    *,
    production: bool,
    probe: Callable[[], tuple[bool, tuple[str, ...]]] | None = None,
) -> DoctorCheck:
    """Report the local model runtime honestly, including when it is absent.

    Organ 53: `doctor` had NO model-runtime check at all, so it could not say
    whether Ollama was reachable either way -- an operator reading a clean
    report would reasonably infer the runtime was fine when nothing had
    looked. The plan is explicit that an unavailable runtime must read as
    degraded or unavailable, never healthy.

    `probe` is injectable so this never performs a live network call on a test
    path; the default asks the real client, which already collapses every
    failure to ``available: False`` rather than raising.
    """

    def _default_probe() -> tuple[bool, tuple[str, ...]]:
        from aios.core.llm import OllamaClient

        listing = OllamaClient().list_models()
        return bool(listing.get("available")), tuple(listing.get("models") or ())

    try:
        available, models = (probe or _default_probe)()
    except Exception as exc:  # noqa: BLE001 - an unreachable runtime is a result
        return _check(
            "model_runtime",
            False,
            f"model runtime {config.OLLAMA_HOST} is unavailable: {exc}",
            required=production,
        )

    if not available:
        return _check(
            "model_runtime",
            False,
            f"model runtime {config.OLLAMA_HOST} is unavailable "
            "(no local model can be qualified or dispatched)",
            required=production,
        )
    if not models:
        # Reachable but empty is DEGRADED, not healthy: the engine answered,
        # but there is nothing installed to run.
        return _check(
            "model_runtime",
            False,
            f"model runtime {config.OLLAMA_HOST} is reachable but no model is installed",
            required=production,
        )
    return _check(
        "model_runtime",
        True,
        f"model runtime {config.OLLAMA_HOST} is available with "
        f"{len(models)} installed model(s)",
        required=production,
    )


def doctor_report(
    *,
    profile: str | None = None,
    project_roots: tuple[Path, ...] | None = None,
    executor_probe: Callable[[], tuple[bool, str]] | None = None,
    backup_dir: Path | None = None,
    model_runtime_probe: Callable[[], tuple[bool, tuple[str, ...]]] | None = None,
) -> DoctorReport:
    """Return measured posture without starting models or changing projects."""
    resolved_profile = (
        (profile or os.getenv("AIOS_PROFILE", "development")).strip().lower()
    )
    production = resolved_profile == "production"
    checks: list[DoctorCheck] = []
    data_writable = _writable(config.DATA_DIR)
    checks.append(
        _check(
            "data_directory",
            data_writable,
            f"data directory {config.DATA_DIR} is writable"
            if data_writable
            else f"data directory {config.DATA_DIR} is not writable",
            required=True,
        )
    )
    checks.append(_audit_check(production=production))
    checks.append(
        _backup_check(
            production=production,
            backup_dir=backup_dir if backup_dir is not None else config.BACKUP_DIR,
        )
    )
    checks.append(
        _model_runtime_check(production=production, probe=model_runtime_probe)
    )

    executor_ok, executor_message = (
        executor_probe()
        if executor_probe is not None
        else (
            bool(shutil.which(config.CONTAINER_RUNTIME)),
            f"{config.CONTAINER_RUNTIME} runtime is available"
            if shutil.which(config.CONTAINER_RUNTIME)
            else f"{config.CONTAINER_RUNTIME} runtime is unavailable",
        )
    )
    checks.append(
        _check("executor", executor_ok, executor_message, required=production)
    )

    # Organ 53: Ollama local runtime check
    try:
        from aios.core.llm import OllamaClient

        client = OllamaClient()
        ollama_ok = client.is_available()
    except Exception:
        ollama_ok = False

    checks.append(
        _check(
            "ollama_runtime",
            ollama_ok,
            "Ollama local runtime is available"
            if ollama_ok
            else "Ollama local runtime is unavailable/degraded",
            required=production,
        )
    )

    roots = project_roots if project_roots is not None else config.SCOPE_ROOTS
    root_ok = bool(roots) and all(path.exists() and path.is_dir() for path in roots)
    checks.append(
        _check(
            "project_roots",
            root_ok,
            f"{sum(path.exists() and path.is_dir() for path in roots)} project root(s) available"
            if root_ok
            else "no enrolled project root is available",
            required=production,
        )
    )

    if production and not config.API_TOKEN:
        checks.append(
            _check(
                "operator_token",
                False,
                "production API token is not configured",
                required=True,
            )
        )
    else:
        checks.append(
            _check(
                "operator_token",
                True,
                "operator token posture is configured for this profile",
                required=False,
            )
        )

    disabled = [
        name
        for name, enabled in (
            ("earned_autonomy", config.EARNED_AUTONOMY_ENABLED and not production),
            ("cloud_burst", config.SWARM_CLOUD_BURST_ENABLED and not production),
            ("self_consistency", config.SELF_CONSISTENCY),
            ("documentation_routes", config.ENABLE_DOCS),
        )
        if not enabled
    ]
    warnings = tuple(check.message for check in checks if check.status == "warning")
    ok = all(check.status != "fatal" for check in checks)
    return DoctorReport(
        profile=resolved_profile,
        ok=ok,
        checks=tuple(checks),
        disabled_capabilities=tuple(disabled),
        warnings=warnings,
    )


__all__ = [
    "BACKUP_STALE_AFTER_SECONDS",
    "DoctorCheck",
    "DoctorReport",
    "doctor_report",
    "newest_backup_age_seconds",
]
