"""Secret detection and redaction: regex patterns plus Shannon-entropy scanning.

Implements the blueprint's "entropy + regex dual scan": a curated set of
credential regexes (AWS, GitHub, OpenAI, generic bearer/assignment) catches
known formats, and an entropy pass catches novel high-randomness tokens the
regexes miss. Detected secrets are replaced with a non-reversible
``<REDACTED:NAME:hash>`` token (an 8-char SHA-256 prefix) so the audit log can
correlate occurrences of the same secret without ever persisting its value.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Pattern

#: Minimum length for a token to be considered for entropy-based detection.
_ENTROPY_MIN_LEN: int = 20
#: Shannon entropy (bits/char) above which a long token is treated as a secret.
#: ~4.0 cleanly separates random base64/hex credentials from natural-language
#: words and ordinary identifiers, which sit well below it.
_ENTROPY_THRESHOLD: float = 4.0

#: Named credential regexes applied before the entropy pass. Order matters only
#: for the redaction label; each is global (all matches replaced).
_NAMED_PATTERNS: list[tuple[str, Pattern[str]]] = [
    ("OPENAI_API_KEY", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    (
        "AWS_ACCESS_KEY",
        re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    ),
    # Bedrock API keys (the newer ABSK… shape) often appear raw in logs/adapters.
    ("AWS_BEDROCK_KEY", re.compile(r"ABSK[A-Za-z0-9]{32,}")),
    ("GITHUB_TOKEN", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}")),
    # Google API keys (AIza…). Typical length is 39 chars; allow a little slack.
    ("GOOGLE_API_KEY", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    # Anthropic API keys (sk-ant-api03-…, sk-ant-api04-…, etc.).
    ("ANTHROPIC_API_KEY", re.compile(r"sk-ant-api[0-9]{2}-[A-Za-z0-9_-]{32,}")),
    ("BEARER_TOKEN", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    (
        "ASSIGNED_SECRET",
        re.compile(
            r"(?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*"
            r"['\"]?[A-Za-z0-9\-_]{12,}['\"]?",
            re.IGNORECASE,
        ),
    ),
]

#: Token shape eligible for the entropy pass (base64/hex/url-safe alphabets).
# ``=`` is intentionally excluded; it is valid base64 padding but including it
# lets the regex swallow assignment prefixes like ``value=SECRET``.
_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/\-_]{%d,}" % _ENTROPY_MIN_LEN)


@dataclass(frozen=True)
class ScanResult:
    """Outcome of a secret scan."""

    scrubbed: str
    detected: bool
    findings: tuple[str, ...]


def _fingerprint(value: str) -> str:
    """Return a short, non-reversible SHA-256 fingerprint of *value*."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def shannon_entropy(token: str) -> float:
    """Return the Shannon entropy (bits per character) of *token*."""
    if not token:
        return 0.0
    counts = Counter(token)
    length = len(token)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def _credential_like_min_len(token: str) -> int:
    """Return a minimum length floor tuned to the token's alphabet.

    Smaller alphabets (hex, base32-ish) need more characters to reach the same
    entropy density, so we require a longer run before treating them as
    credential-like. Mixed base64/url-safe alphabets get the default floor.
    """
    if set(token).issubset(set("0123456789abcdefABCDEF")):
        return 32
    if set(token).issubset(set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
        return 26
    return _ENTROPY_MIN_LEN


def scan_and_redact(payload: str) -> ScanResult:
    """Detect and redact secrets in *payload*.

    Runs the named-regex pass first, then an entropy pass over any remaining
    long tokens. Returns the scrubbed text, whether anything was detected, and
    the distinct finding labels (e.g. ``("AWS_ACCESS_KEY", "HIGH_ENTROPY")``).
    """
    if not payload or not isinstance(payload, str):
        return ScanResult(scrubbed=payload, detected=False, findings=())

    findings: list[str] = []
    scrubbed = payload

    # Pass 1 — named credential formats.
    for name, pattern in _NAMED_PATTERNS:
        def _replace(match: "re.Match[str]", _name: str = name) -> str:
            findings.append(_name)
            return f"<REDACTED:{_name}:{_fingerprint(match.group(0))}>"

        scrubbed = pattern.sub(_replace, scrubbed)

    # Pass 2 — high-entropy tokens the named patterns did not already redact.
    def _entropy_replace(match: "re.Match[str]") -> str:
        token = match.group(0)
        if len(token) >= _credential_like_min_len(token) and shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            findings.append("HIGH_ENTROPY")
            return f"<REDACTED:HIGH_ENTROPY:{_fingerprint(token)}>"
        return token

    scrubbed = _ENTROPY_TOKEN.sub(_entropy_replace, scrubbed)

    # De-duplicate findings while preserving first-seen order.
    unique_findings = tuple(dict.fromkeys(findings))
    return ScanResult(
        scrubbed=scrubbed,
        detected=bool(unique_findings),
        findings=unique_findings,
    )
