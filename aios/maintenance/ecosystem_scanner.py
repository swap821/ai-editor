"""Local-only ecosystem evidence scanner.

Phase 3 intentionally starts outside ``aios.security``. It inspects local
manifests, API response strings, optional git logs, and local model metadata,
then emits proposal findings. It does not fetch vulnerability feeds, open
network sockets, write files, mutate policy, or authorize action.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Pattern

from aios.security import gateway
from aios.security.secret_scanner import scan_and_redact

EcosystemKind = Literal[
    "untrusted_dependency_source",
    "install_script_network",
    "secret_material",
    "prompt_injection",
    "model_metadata_remote_endpoint",
    "read_error",
]
EcosystemSeverity = Literal["low", "medium", "high", "critical"]

_MAX_TEXT_BYTES = 512_000

_MANIFEST_NAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-optional.txt",
        "uv.lock",
        "yarn.lock",
        "Pipfile",
        "Pipfile.lock",
    }
)
_MANIFEST_SUFFIXES: tuple[str, ...] = (
    ".requirements.txt",
    ".lock",
)
_MODEL_METADATA_NAMES: frozenset[str] = frozenset(
    {
        "models.json",
        "ollama_models.json",
        "model_metadata.json",
    }
)
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)


@dataclass(frozen=True)
class EcosystemRule:
    kind: EcosystemKind
    severity: EcosystemSeverity
    pattern: Pattern[str]
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class EcosystemFinding:
    target_id: str
    kind: EcosystemKind
    severity: EcosystemSeverity
    excerpt: str
    evidence: tuple[str, ...]
    recommendation: str
    recommended_action: str = "review_proposal"
    authority: str = "proposal/evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target_id,
            "kind": self.kind,
            "severity": self.severity,
            "excerpt": self.excerpt,
            "evidence": list(self.evidence),
            "recommendation": self.recommendation,
            "recommended_action": self.recommended_action,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class EcosystemReport:
    findings: tuple[EcosystemFinding, ...]
    local_only: bool = True
    writes_performed: bool = False
    cloud_calls: int = 0
    network_calls: int = 0
    activation: str = "proposal/evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "activation": self.activation,
            "local_only": self.local_only,
            "writes_performed": self.writes_performed,
            "cloud_calls": self.cloud_calls,
            "network_calls": self.network_calls,
            "findings": [finding.to_dict() for finding in self.findings],
        }


_MANIFEST_RULES: tuple[EcosystemRule, ...] = (
    EcosystemRule(
        kind="untrusted_dependency_source",
        severity="high",
        pattern=re.compile(
            r"(?im)(?:--extra-index-url\s+http://|git\+http://|https?://[^\s\"']+\.(?:tar\.gz|zip|whl)\b)"
        ),
        evidence="dependency manifest references a direct or plaintext remote source",
        recommendation="Review the dependency source before install; keep as evidence until an existing policy accepts it.",
    ),
    EcosystemRule(
        kind="install_script_network",
        severity="high",
        pattern=re.compile(
            r"(?i)\b(?:postinstall|preinstall|prepare|install)\b[^\n]*(?:curl|wget|Invoke-WebRequest|iwr|http://|https://)"
        ),
        evidence="install script appears to fetch or execute remote material",
        recommendation="Review install scripts before running dependency installation.",
    ),
)

_MODEL_RULES: tuple[EcosystemRule, ...] = (
    EcosystemRule(
        kind="model_metadata_remote_endpoint",
        severity="medium",
        pattern=re.compile(r"(?i)\bendpoint\b[^,\n{}]*https?://|https?://[^\s\"'}]+"),
        evidence="local model metadata references a remote endpoint",
        recommendation="Treat remote model metadata as egress evidence; router policy remains authoritative.",
    ),
)

_INJECTION_RECOMMENDATION = (
    "Treat the response as untrusted evidence; do not execute embedded instructions."
)
_SECRET_RECOMMENDATION = (
    "Redact before persistence and review the local source for credential exposure."
)
_READ_ERROR_RECOMMENDATION = (
    "Treat unreadable target as incomplete evidence, not as a clean scan."
)


class EcosystemScanner:
    """Read-only scanner for local environmental evidence."""

    def scan_directory(
        self,
        root: Path | str,
        *,
        include_git_history: bool = False,
    ) -> EcosystemReport:
        root_path = Path(root).resolve()
        findings: list[EcosystemFinding] = []
        for path in self._iter_known_files(root_path):
            findings.extend(self._scan_file(path, root_path=root_path))

        if include_git_history:
            findings.extend(self.scan_git_history(root_path).findings)
        return EcosystemReport(findings=tuple(findings))

    def scan_api_response(self, target_id: str, payload: str) -> EcosystemReport:
        return EcosystemReport(
            findings=tuple(self._scan_text(target_id, payload, context="api_response"))
        )

    def scan_git_history(self, root: Path | str) -> EcosystemReport:
        root_path = Path(root).resolve()
        logs_root = root_path / ".git" / "logs"
        findings: list[EcosystemFinding] = []
        if not logs_root.exists():
            return EcosystemReport(findings=())
        for path in sorted(p for p in logs_root.rglob("*") if p.is_file()):
            findings.extend(self._scan_file(path, root_path=root_path, context="git_history"))
        return EcosystemReport(findings=tuple(findings))

    def scan_targets(self, targets: Mapping[str, str]) -> EcosystemReport:
        findings: list[EcosystemFinding] = []
        for target_id in sorted(targets):
            findings.extend(
                self._scan_text(target_id, targets[target_id], context="generic")
            )
        return EcosystemReport(findings=tuple(findings))

    def _iter_known_files(self, root: Path) -> Iterable[Path]:
        if root.is_file():
            yield root
            return
        if not root.exists():
            return
        for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
            if not path.is_file() or _is_skipped(path, root):
                continue
            if _is_manifest(path) or _is_model_metadata(path):
                yield path

    def _scan_file(
        self,
        path: Path,
        *,
        root_path: Path,
        context: str | None = None,
    ) -> tuple[EcosystemFinding, ...]:
        target_id = _target_id(path, root_path)
        try:
            payload = _read_bounded_text(path)
        except OSError as exc:
            return (
                EcosystemFinding(
                    target_id=target_id,
                    kind="read_error",
                    severity="medium",
                    excerpt=_clip(str(exc)),
                    evidence=("local file read failed",),
                    recommendation=_READ_ERROR_RECOMMENDATION,
                ),
            )
        scan_context = context or ("model_metadata" if _is_model_metadata(path) else "manifest")
        return tuple(self._scan_text(target_id, payload, context=scan_context))

    def _scan_text(
        self,
        target_id: str,
        payload: str,
        *,
        context: str,
    ) -> tuple[EcosystemFinding, ...]:
        if not payload:
            return ()

        redaction = scan_and_redact(payload)
        scrubbed = redaction.scrubbed
        findings: list[EcosystemFinding] = []
        if redaction.detected:
            findings.append(
                EcosystemFinding(
                    target_id=target_id,
                    kind="secret_material",
                    severity="critical",
                    excerpt=_clip(scrubbed),
                    evidence=redaction.findings,
                    recommendation=_SECRET_RECOMMENDATION,
                )
            )

        if context in {"manifest", "generic"}:
            findings.extend(_rule_findings(target_id, scrubbed, _MANIFEST_RULES))
        if context == "model_metadata":
            findings.extend(_rule_findings(target_id, scrubbed, _MODEL_RULES))
            findings.extend(_scan_json_model_metadata(target_id, scrubbed))
        if context in {"api_response", "generic", "git_history"}:
            classification = gateway.classify(scrubbed)
            if classification.zone is gateway.Zone.RED and (
                "Prompt-injection pattern" in classification.reason
                or "injection" in classification.reason.lower()
            ):
                findings.append(
                    EcosystemFinding(
                        target_id=target_id,
                        kind="prompt_injection",
                        severity="critical",
                        excerpt=_clip(scrubbed),
                        evidence=(classification.reason,),
                        recommendation=_INJECTION_RECOMMENDATION,
                    )
                )

        return tuple(findings)


def scan_api_response(target_id: str, payload: str) -> EcosystemReport:
    return EcosystemScanner().scan_api_response(target_id, payload)


def scan_environment(root: Path | str) -> EcosystemReport:
    return EcosystemScanner().scan_directory(root)


def _rule_findings(
    target_id: str,
    payload: str,
    rules: tuple[EcosystemRule, ...],
) -> list[EcosystemFinding]:
    findings: list[EcosystemFinding] = []
    for rule in rules:
        match = rule.pattern.search(payload)
        if match is None:
            continue
        findings.append(
            EcosystemFinding(
                target_id=target_id,
                kind=rule.kind,
                severity=rule.severity,
                excerpt=_excerpt(payload, match.start(), match.end()),
                evidence=(rule.evidence,),
                recommendation=rule.recommendation,
            )
        )
    return findings


def _scan_json_model_metadata(target_id: str, payload: str) -> list[EcosystemFinding]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []

    serialized = json.dumps(parsed, sort_keys=True)
    if "http://" not in serialized and "https://" not in serialized:
        return []
    if any(
        f"{key}" in serialized.lower()
        for key in ("endpoint", "base_url", "host", "remote")
    ):
        return [
            EcosystemFinding(
                target_id=target_id,
                kind="model_metadata_remote_endpoint",
                severity="medium",
                excerpt=_clip(serialized),
                evidence=("local model metadata references a remote endpoint",),
                recommendation="Review model metadata before allowing model egress.",
            )
        ]
    return []


def _is_manifest(path: Path) -> bool:
    name = path.name
    return name in _MANIFEST_NAMES or any(name.endswith(suffix) for suffix in _MANIFEST_SUFFIXES)


def _is_model_metadata(path: Path) -> bool:
    return path.name in _MODEL_METADATA_NAMES or path.as_posix().endswith("/.ollama/models.json")


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in relative.parts)


def _read_bounded_text(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(_MAX_TEXT_BYTES + 1)
    if len(data) > _MAX_TEXT_BYTES:
        data = data[:_MAX_TEXT_BYTES]
    return data.decode("utf-8", errors="replace")


def _target_id(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _clip(text: str, limit: int = 180) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 3]}..."


def _excerpt(text: str, start: int, end: int, radius: int = 70) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return _clip(text[lo:hi])


__all__ = [
    "EcosystemFinding",
    "EcosystemReport",
    "EcosystemScanner",
    "scan_api_response",
    "scan_environment",
]
