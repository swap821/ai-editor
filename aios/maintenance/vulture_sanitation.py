"""Read-only immune/vulture evidence scanner.

This module is deliberately outside ``aios.security``. It can detect and report
dangerous lessons, prompt-injection phrases, unsafe autonomy claims, and secret
material, but every result is proposal/evidence only. It performs no writes,
cloud calls, memory compaction, pheromone decay, policy mutation, or deletion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Pattern

from aios.security import gateway
from aios.security.secret_scanner import scan_and_redact

VultureKind = Literal[
    "security_bypass",
    "approval_bypass",
    "trusted_memory_activation",
    "unsafe_self_modification",
    "secret_material",
    "read_error",
]
VultureSeverity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class VultureRule:
    kind: VultureKind
    severity: VultureSeverity
    pattern: Pattern[str]
    evidence: str


@dataclass(frozen=True)
class VultureFinding:
    target_id: str
    kind: VultureKind
    severity: VultureSeverity
    excerpt: str
    evidence: tuple[str, ...]
    recommendation: str
    recommended_action: str = "quarantine_proposal"
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
class VultureReport:
    findings: tuple[VultureFinding, ...]
    local_only: bool = True
    writes_performed: bool = False
    cloud_calls: int = 0
    activation: str = "proposal/evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "activation": self.activation,
            "local_only": self.local_only,
            "writes_performed": self.writes_performed,
            "cloud_calls": self.cloud_calls,
            "findings": [finding.to_dict() for finding in self.findings],
        }


_RULES: tuple[VultureRule, ...] = (
    VultureRule(
        kind="security_bypass",
        severity="critical",
        pattern=re.compile(
            r"\b(ignore\s+all\s+previous\s+instructions|bypass\s+(?:the\s+)?(?:security|gateway|guardrail)|approve\s+red\s+actions?|red\s+actions?\s+(?:can|should|must)\s+auto)",
            re.IGNORECASE,
        ),
        evidence="security bypass or RED auto-approval language",
    ),
    VultureRule(
        kind="approval_bypass",
        severity="high",
        pattern=re.compile(
            r"\b(?:never\s+ask\s+approval|skip\s+human\s+approval|yellow\s+actions?.*(?:auto-run|auto\s+approve|without\s+approval)|auto-run\s+them)\b",
            re.IGNORECASE,
        ),
        evidence="human approval bypass language",
    ),
    VultureRule(
        kind="trusted_memory_activation",
        severity="high",
        pattern=re.compile(
            r"\b(?:trusted\s+memory|activate\s+(?:as\s+)?memory|store\s+.*(?:as|into)\s+trusted)\b",
            re.IGNORECASE,
        ),
        evidence="unreviewed evidence promoted to trusted memory",
    ),
    VultureRule(
        kind="unsafe_self_modification",
        severity="critical",
        pattern=re.compile(
            r"\b(?:self-modif(?:y|ication)|modify\s+the\s+frozen\s+core|frozen\s+core\s+without\s+human\s+review|without\s+human\s+review)\b",
            re.IGNORECASE,
        ),
        evidence="self-modification without the approval chain",
    ),
)

_RECOMMENDATIONS: Mapping[VultureKind, str] = {
    "security_bypass": "Quarantine the lesson/proposal for human review; security gateway remains authoritative.",
    "approval_bypass": "Quarantine and require explicit operator review before reuse.",
    "trusted_memory_activation": "Keep as evidence only until an existing memory authority accepts it.",
    "unsafe_self_modification": "Convert to a proposal and route through controlled self-modification review.",
    "secret_material": "Redact before persistence and review the source for credential exposure.",
    "read_error": "Treat unreadable target as incomplete evidence, not as a clean scan.",
}


class VultureScanner:
    """Local-only scanner that emits proposal findings without side effects."""

    def scan_targets(self, targets: Mapping[str, str]) -> VultureReport:
        findings: list[VultureFinding] = []
        for target_id in sorted(targets):
            findings.extend(self._scan_text(target_id, targets[target_id]))
        return VultureReport(findings=tuple(findings))

    def scan_files(
        self,
        paths: Iterable[Path | str],
        *,
        memory_store: object = None,
        pheromone_store: object = None,
        policy_engine: object = None,
    ) -> VultureReport:
        """Read files and scan them without touching supplied mutable systems.

        The subsystem parameters are intentional guardrails for callers: this
        method accepts them so tests and integrations can prove they are not
        invoked by the read-only phase.
        """

        del memory_store, pheromone_store, policy_engine
        targets: dict[str, str] = {}
        findings: list[VultureFinding] = []
        for raw_path in sorted((Path(p) for p in paths), key=lambda p: p.as_posix()):
            try:
                targets[raw_path.as_posix()] = raw_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as exc:
                findings.append(
                    VultureFinding(
                        target_id=raw_path.as_posix(),
                        kind="read_error",
                        severity="medium",
                        excerpt=_clip(str(exc)),
                        evidence=("local file read failed",),
                        recommendation=_RECOMMENDATIONS["read_error"],
                    )
                )
        findings.extend(self.scan_targets(targets).findings)
        return VultureReport(findings=tuple(findings))

    def _scan_text(self, target_id: str, payload: str) -> tuple[VultureFinding, ...]:
        if not payload:
            return ()

        redaction = scan_and_redact(payload)
        scrubbed = redaction.scrubbed
        findings: list[VultureFinding] = []
        if redaction.detected:
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind="secret_material",
                    severity="critical",
                    excerpt=_clip(scrubbed),
                    evidence=redaction.findings,
                    recommendation=_RECOMMENDATIONS["secret_material"],
                )
            )

        for rule in _RULES:
            match = rule.pattern.search(scrubbed)
            if match is None:
                continue
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind=rule.kind,
                    severity=rule.severity,
                    excerpt=_excerpt(scrubbed, match.start(), match.end()),
                    evidence=(rule.evidence,),
                    recommendation=_RECOMMENDATIONS[rule.kind],
                )
            )

        classification = gateway.classify(scrubbed)
        if (
            classification.zone is gateway.Zone.RED
            and "Prompt-injection pattern" in classification.reason
            and not any(f.kind == "security_bypass" for f in findings)
        ):
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind="security_bypass",
                    severity="critical",
                    excerpt=_clip(scrubbed),
                    evidence=(classification.reason,),
                    recommendation=_RECOMMENDATIONS["security_bypass"],
                )
            )

        return tuple(findings)


def scan_vulture_targets(targets: Mapping[str, str]) -> VultureReport:
    return VultureScanner().scan_targets(targets)


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
    "VultureFinding",
    "VultureReport",
    "VultureScanner",
    "scan_vulture_targets",
]
