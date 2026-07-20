"""Secret isolation policy for Council Runtime workers and reasoning calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from aios.security.secret_scanner import scan_and_redact

SECRET_ENV_NAMES: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AZURE_OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "TOKEN",
        "SECRET",
        "PASSWORD",
    }
)


@dataclass(frozen=True)
class SecretDecision:
    scrubbed: str
    detected: bool
    findings: tuple[str, ...]
    cloud_allowed: bool


class SecretPolicy:
    """Redact persisted reasoning text and keep secrets away from workers."""

    def inspect_text(self, payload: str) -> SecretDecision:
        scanned = scan_and_redact(payload)
        return SecretDecision(
            scrubbed=scanned.scrubbed,
            detected=scanned.detected,
            findings=scanned.findings,
            cloud_allowed=not scanned.detected,
        )

    def redact_text(self, payload: str) -> str:
        return scan_and_redact(payload).scrubbed

    def worker_environment(self, env: Mapping[str, str]) -> dict[str, str]:
        return {
            name: value
            for name, value in env.items()
            if name.upper() not in SECRET_ENV_NAMES
            and not self._looks_secret_name(name)
        }

    def _looks_secret_name(self, name: str) -> bool:
        upper = name.upper()
        return any(
            marker in upper
            for marker in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")
        )


__all__ = ["SECRET_ENV_NAMES", "SecretDecision", "SecretPolicy"]
