"""Deterministic, fail-closed three-zone security gateway.

Architectural invariants (Blueprint Section 06 / Q1):
  * **Deterministic** — the same input always yields the same zone. No LLM
    judgement is ever consulted; classification is pure pattern matching.
  * **Fail-closed** — empty input, unknown patterns, and any internal exception
    resolve to :attr:`Zone.RED`, never to a permissive zone.
  * **Independent of model confidence** — the gateway is a kernel the planner
    and executor cannot reason their way past.

Zone resolution:
  * ``GREEN``  — safe (read/search/explain); auto-execute.
  * ``YELLOW`` — caution (edit, install, git, create dirs); one-click human
    approval, rate-limited per session.
  * ``RED``    — danger (delete, network egress, env/secret mutation, prompt
    injection, embedded credentials, out-of-scope paths); blocked outright.

Classification order is strict: injection -> secret -> destructive -> network
-> env mutation -> scope -> caution -> safe. The most dangerous category that
matches wins.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Pattern

from aios import config
from aios.security.scope_lock import command_stays_in_scope
from aios.security.secret_scanner import scan_and_redact


class Zone(str, Enum):
    """The three deterministic security zones."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass(frozen=True)
class ClassificationResult:
    """Result of classifying an action payload into a zone."""

    zone: Zone
    confidence: float
    reason: str


@dataclass(frozen=True)
class GatewayDecision:
    """Final actionable decision returned to the orchestration layer."""

    status: str  # 'ALLOW' | 'REQUIRE_HUMAN' | 'BLOCK'
    zone: Zone
    reason: str


def _compile(patterns: list[str]) -> list[Pattern[str]]:
    """Compile a list of case-insensitive regex source strings."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# 1. Prompt-injection attempts to override system policy via the payload -> RED.
_INJECTION_PATTERNS = _compile([
    r"ignore\s+(all\s+)?(the\s+)?previous\s+instructions",
    r"disregard\s+(the\s+)?(system|above|prior|earlier)",
    r"you\s+are\s+now\s+(dan|in\s+developer\s+mode)",
    r"\bdo\s+anything\s+now\b",
    r"override\s+(the\s+)?security",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"bypass\s+(the\s+)?(security|guardrail|gateway)",
])

# 2. Destructive / high-risk operations -> RED.
_DESTRUCTIVE_PATTERNS = _compile([
    r"\brm\s+-[rf]{1,2}\b", r"\brm\s+--recursive", r"\brm\s+/",
    r"\bdel\s+/[sq]\b", r"\bdel\s+\*", r"\berase\s+/",
    r"\bformat\s+[a-z]:", r"\bmkfs\b", r"\bmkfs\.", r"\bdd\s+if=",
    r">\s*/dev/sd[a-z]", r"\bchmod\s+777\b", r"\bchown\b",
    r"\bremove-item\b[^\n]*-recurse", r"\bremove-item\b[^\n]*-force",
    r"\brmdir\s+/s\b", r"\brd\s+/s\b",
    r":\(\)\s*\{.*\}\s*;",  # fork bomb
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b", r"\bstop-computer\b",
    r"\bshutil\.rmtree\b", r"\bos\.remove\b", r"\bos\.unlink\b", r"\bos\.rmdir\b",
])

# 3. Network egress (data exfiltration / supply-chain risk) -> RED.
_NETWORK_PATTERNS = _compile([
    r"\bcurl\s+", r"\bwget\s+", r"\binvoke-webrequest\b", r"\binvoke-restmethod\b",
    r"\bnc\s+-", r"\bnetcat\b", r"\bscp\s+", r"\bsftp\s+", r"\bftp\s+", r"\bssh\s+",
])

# 4. Environment / secret mutation -> RED.
_ENV_MUTATION_PATTERNS = _compile([
    r"\bexport\s+\w+\s*=", r"\bsetx\b", r"\bset\s+\w+=",
    r"\$env:\w+\s*=", r"\bset-item\s+env:",
])

# 5. Shell/interpreter escape hatches -> RED. These can hide arbitrary writes,
# network access, or process launches behind an otherwise innocent executable.
_SHELL_ESCAPE_PATTERNS = _compile([
    r"(?:^|[;&|]\s*)python(?:3(?:\.\d+)?)?\s+-c\b",
    r"(?:^|[;&|]\s*)node\s+-e\b",
    r"(?:^|[;&|]\s*)(?:powershell|pwsh)\b[^\n]*\s-(?:command|encodedcommand)\b",
    r"(?:^|[;&|]\s*)cmd(?:\.exe)?\s+/c\b",
    r"(?:^|[;&|]\s*)(?:bash|sh)\s+-c\b",
])

# No shell composition is accepted, even after human approval. Executor launches
# structured argv with shell=False; rejecting metacharacters here keeps the
# classification contract aligned with that execution boundary.
_SHELL_COMPOSITION_PATTERNS = _compile([
    r"[;&|<>`]",
    r"[\r\n]",
])

# 5. Caution operations requiring human approval -> YELLOW.
_CAUTION_PATTERNS = _compile([
    r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\byarn\s+add\b",
    r"\bgit\s+(commit|push|reset|clone|checkout|merge|rebase)\b",
    r"\bset-content\b", r"\bout-file\b", r"\badd-content\b",
    r"\bnew-item\b[^\n]*-itemtype\s+file", r"\bnew-item\b[^\n]*-itemtype\s+directory",
    r"\bmkdir\b", r"\bmd\b\s", r"\bmv\s+", r"\bmove-item\b",
    r"\bcp\s+", r"\bcopy-item\b", r"\btouch\s+",
    r"open\([^)]*['\"][rwa]?\+?b?['\"]",  # python file write mode
    r"^\s*(?:(?:\.venv[\\/]+scripts[\\/]+)?python(?:\.exe)?\s+-m\s+)?pytest\b",
])

# Explicit auto-execute allowlist. Everything else that survives the RED and
# YELLOW checks is refused rather than handed to a shell by default.
_SAFE_PATTERNS = _compile([
    r"^\s*echo(?:\s+[^;&|<>`\r\n]*)?\s*$",
    r"^\s*pwd\s*$",
])


class RateLimiter:
    """Thread-safe per-session counter for sensitive (YELLOW+) actions.

    After ``max_per_session`` sensitive actions, further ones are blocked
    pending human re-authorisation. Anonymous (sessionless) actions are not
    counted, matching the legacy server contract.
    """

    def __init__(self, max_per_session: int = config.MAX_RED_ACTIONS_PER_SESSION) -> None:
        self.max_per_session = max_per_session
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def record(self, session_id: Optional[str]) -> int:
        """Increment and return the sensitive-action count for *session_id*."""
        if not session_id:
            return 1
        with self._lock:
            self._counts[session_id] = self._counts.get(session_id, 0) + 1
            return self._counts[session_id]

    def reset(self, session_id: Optional[str] = None) -> None:
        """Reset one session's counter, or all of them when *session_id* is None."""
        with self._lock:
            if session_id is None:
                self._counts.clear()
            else:
                self._counts.pop(session_id, None)


#: Process-wide default limiter used when a caller does not supply its own.
_default_rate_limiter = RateLimiter()

#: Optional embedding-similarity injection shield (the dual-layer's vector half).
#: ``None`` by default so the gateway stays pure-regex and dependency-light (no
#: torch); the API installs one at startup when ``config.INJECTION_VECTOR_SHIELD``
#: is set. Anything truthy must expose ``is_injection(text) -> bool``.
_injection_shield: object = None


def set_injection_shield(shield: object) -> None:
    """Install (or clear with ``None``) the process-wide vector injection shield."""
    global _injection_shield
    _injection_shield = shield


def classify(command: str, *, injection_shield: object = None) -> ClassificationResult:
    """Deterministically classify *command* into a security zone (fail-closed).

    Args:
        command: The action payload (shell command or code) to classify.
        injection_shield: Optional vector injection shield (``is_injection``);
            falls back to the process-wide one set via
            :func:`set_injection_shield`. ``None`` everywhere = regex-only.

    Returns:
        A :class:`ClassificationResult`. Any internal error yields ``RED``.
    """
    try:
        if not command or not isinstance(command, str) or not command.strip():
            return ClassificationResult(Zone.RED, 1.0, "Empty/invalid command (fail-closed).")

        for pat in _INJECTION_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Prompt-injection pattern: {pat.pattern}")

        # Second injection layer (Blueprint 5.2): an embedding-similarity blocklist
        # catches paraphrased injections the regex misses. Fail-safe inside the
        # shield (model error -> False), so the regex layer is never weakened.
        shield = injection_shield if injection_shield is not None else _injection_shield
        if shield is not None and shield.is_injection(command):  # type: ignore[attr-defined]
            return ClassificationResult(Zone.RED, 1.0, "Semantic prompt-injection (vector blocklist).")

        scan = scan_and_redact(command)
        if scan.detected:
            return ClassificationResult(
                Zone.RED, 1.0, f"Embedded credential(s) detected: {', '.join(scan.findings)}"
            )

        for pat in _DESTRUCTIVE_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Destructive operation: {pat.pattern}")

        for pat in _NETWORK_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Network egress blocked: {pat.pattern}")

        for pat in _ENV_MUTATION_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Environment/secret mutation: {pat.pattern}")

        for pat in _SHELL_ESCAPE_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Shell/interpreter escape blocked: {pat.pattern}")

        for pat in _SHELL_COMPOSITION_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.RED, 1.0, f"Shell composition blocked: {pat.pattern}")

        scope = command_stays_in_scope(command)
        if not scope.in_scope:
            return ClassificationResult(Zone.RED, 1.0, f"Scope violation: {scope.reason}")

        for pat in _CAUTION_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.YELLOW, 0.9, f"Caution operation requires approval: {pat.pattern}")

        for pat in _SAFE_PATTERNS:
            if pat.search(command):
                return ClassificationResult(Zone.GREEN, 1.0, "Known read-only/test command; within scope.")

        return ClassificationResult(Zone.RED, 1.0, "Unknown command is not on the auto-execute allowlist.")
    except Exception as exc:  # noqa: BLE001 - fail-closed on any classifier error
        return ClassificationResult(Zone.RED, 1.0, f"Fail-closed on classifier exception: {exc}")


def validate_command(
    command: str,
    *,
    session_id: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> GatewayDecision:
    """Classify *command* and resolve it to an actionable gateway decision.

    GREEN -> ALLOW, YELLOW -> REQUIRE_HUMAN (subject to the per-session rate
    limit, after which it becomes a RED BLOCK), RED -> BLOCK.
    """
    limiter = rate_limiter if rate_limiter is not None else _default_rate_limiter
    result = classify(command)

    if result.zone is Zone.RED:
        return GatewayDecision("BLOCK", Zone.RED, f"[SECURITY BLOCK] {result.reason}")

    if result.zone is Zone.YELLOW:
        count = limiter.record(session_id)
        if count > limiter.max_per_session:
            return GatewayDecision(
                "BLOCK",
                Zone.RED,
                f"[RATE LIMIT] {limiter.max_per_session} sensitive actions already used "
                f"this session; human re-authorisation required.",
            )
        return GatewayDecision("REQUIRE_HUMAN", Zone.YELLOW, f"[APPROVAL REQUIRED] {result.reason}")

    return GatewayDecision("ALLOW", Zone.GREEN, "Command passed the security gateway.")
