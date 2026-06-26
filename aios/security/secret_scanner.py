"""Secret detection and redaction: regex patterns plus Shannon-entropy scanning.

Implements the blueprint's "entropy + regex dual scan": a curated set of
credential regexes (AWS, GitHub, OpenAI, generic bearer/assignment) catches
known formats, and an entropy pass catches novel high-randomness tokens the
regexes miss. Detected secrets are replaced with a non-reversible
``<REDACTED:NAME:hash>`` token (an 8-char SHA-256 prefix) so the audit log can
correlate occurrences of the same secret without ever persisting its value.

Hardened (A+) — includes pattern-based detection for structured secrets,
sliding-window entropy for Base64 evasion, and contextual filtering.
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

#: Sliding-window entropy check catches Base64-encoded secrets that span
#: whitespace/token boundaries.  Window size (min, max) characters.
_SLIDE_WINDOW_MIN: int = 20
_SLIDE_WINDOW_MAX: int = 80
#: Fraction of window chars that must be in the base64 alphabet to qualify.
_SLIDE_BASE64_RATIO: float = 0.80

#: Keywords that strengthen confidence when found near a candidate secret.
_CONTEXT_SECRET_KEYWORDS: tuple[str, ...] = (
    "secret", "token", "key", "password", "credential", "auth",
    "api", "private", "access", "bearer", "connect",
)

#: Named credential regexes applied before the entropy pass. Order matters only
#: for the redaction label; each is global (all matches replaced).
#:
#: Hardened patterns — ordered most-specific first to avoid shadowing.
_NAMED_PATTERNS: list[tuple[str, Pattern[str]]] = [
    # ── Private Keys (PEM/SSH) ──────────────────────────────────────────────
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    # ── JWT Tokens (header.payload.signature) ───────────────────────────────
    (
        "JWT_TOKEN",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b"
        ),
    ),
    # ── Stripe API Keys ─────────────────────────────────────────────────────
    (
        "STRIPE_API_KEY",
        re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_]{24,}\b"),
    ),
    # ── OpenAI API Keys ─────────────────────────────────────────────────────
    ("OPENAI_API_KEY", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    # ── AWS Access Keys ─────────────────────────────────────────────────────
    (
        "AWS_ACCESS_KEY",
        re.compile(
            r"\b(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\b"
        ),
    ),
    # ── Bedrock API keys (the newer ABSK… shape) ────────────────────────────
    ("AWS_BEDROCK_KEY", re.compile(r"\bABSK[A-Za-z0-9]{32,}\b")),
    # ── GitHub Tokens ───────────────────────────────────────────────────────
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    # ── Slack Tokens ────────────────────────────────────────────────────────
    (
        "SLACK_TOKEN",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9_-]+\b"),
    ),
    # ── Google API keys (AIza…). Typical length is 39 chars; allow slack. ───
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    # ── Anthropic API keys (sk-ant-api03-…, sk-ant-api04-…, etc.). ──────────
    ("ANTHROPIC_API_KEY", re.compile(r"\bsk-ant-api[0-9]{2}-[A-Za-z0-9_-]{32,}\b")),
    # ── Bearer tokens ───────────────────────────────────────────────────────
    ("BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*")),
    # ── AWS Secret Keys (40-char base64; only flagged with AWS context).
    #: Placed AFTER more specific provider patterns so it only acts as a
    #: catch-all fallback for genuine AWS secret material.
    (
        "AWS_SECRET_KEY",
        re.compile(
            r"\b[A-Za-z0-9/+=]{40}\b"
        ),
    ),
    # ── Database URLs with embedded credentials ─────────────────────────────
    (
        "DATABASE_URL",
        re.compile(
            r"\b(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@\b",
            re.IGNORECASE,
        ),
    ),
    # ── Generic connection strings with embedded credentials ────────────────
    (
        "CONNECTION_STRING",
        re.compile(
            r"\b[A-Za-z]+(?:\+\w+)?://[^:]+:[^@]+@\b"
        ),
    ),
    # ── Generic API-key assignment patterns ─────────────────────────────────
    (
        "ASSIGNED_SECRET",
        re.compile(
            r"\b(?:password|passwd|secret|api[_-]?key|apikey|token)\s*[=:]\s*"
            r"['\"]?[A-Za-z0-9\-_]{12,}['\"]?",
            re.IGNORECASE,
        ),
    ),
]

#: Token shape eligible for the entropy pass (base64/hex/url-safe alphabets).
# ``=`` is intentionally excluded; it is valid base64 padding but including it
# lets the regex swallow assignment prefixes like ``value=SECRET``.
_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/\-_]{%d,}" % _ENTROPY_MIN_LEN)

#: Base64 alphabet (used by the sliding-window pass).
_BASE64_ALPHABET: set[str] = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


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


def _has_secret_context(payload: str, position: int, radius: int = 50) -> bool:
    """Return *True* if secret-related keywords appear near *position*.

    Checks the substring within *radius* chars before and after *position*
    (clamped to string bounds) for contextual keywords that indicate a real
    secret rather than a false positive.
    """
    start = max(0, position - radius)
    end = min(len(payload), position + radius)
    context = payload[start:end].lower()
    return any(kw in context for kw in _CONTEXT_SECRET_KEYWORDS)


def _has_aws_context(payload: str, position: int, radius: int = 100) -> bool:
    """Return *True* if AWS-related keywords appear near *position*.

    Used to gate the broad 40-char AWS_SECRET_KEY pattern so it only fires
    when there is genuine AWS context nearby.
    """
    start = max(0, position - radius)
    end = min(len(payload), position + radius)
    context = payload[start:end].lower()
    aws_keywords = ("ak", "aws", "amazon", "access", "secret", "bedrock",
                    "s3", "ec2", "lambda", "region", "arn")
    return any(kw in context for kw in aws_keywords)


def _is_false_positive_base64(token: str) -> bool:
    """Heuristic to exclude common non-secret base64-looking strings."""
    # CSS data URIs, SVG path data, etc.
    if token.startswith("data:") or token.startswith("image/"):
        return True
    # Common MIME-type prefixes inside base64
    if "text/" in token or "application/" in token or "image/" in token:
        return True
    return False


def _sliding_window_entropy_scan(payload: str) -> list[tuple[int, int, str]]:
    """Return a list of (start, end, label) for secrets found via sliding window.

    Scans 20–80 character windows across *payload* looking for high-entropy
    clusters that are mostly base64-alphabet characters.  This catches
    Base64-encoded secrets that span whitespace or token boundaries.
    """
    found: list[tuple[int, int, str]] = []
    if len(payload) < _SLIDE_WINDOW_MIN:
        return found

    n = len(payload)
    # Step size: every 5 chars is a good balance between coverage and speed.
    step = 5

    for i in range(0, n - _SLIDE_WINDOW_MIN + 1, step):
        for window_size in range(_SLIDE_WINDOW_MIN, _SLIDE_WINDOW_MAX + 1, step):
            j = i + window_size
            if j > n:
                break
            window = payload[i:j]
            # Extract only base64-alphabet characters.
            b64_chars = [c for c in window if c in _BASE64_ALPHABET]
            ratio = len(b64_chars) / window_size
            if ratio < _SLIDE_BASE64_RATIO:
                continue
            candidate = "".join(b64_chars)
            if len(candidate) < _ENTROPY_MIN_LEN:
                continue
            if _is_false_positive_base64(candidate):
                continue
            if shannon_entropy(candidate) >= _ENTROPY_THRESHOLD:
                # Require contextual confirmation to reduce false positives.
                if _has_secret_context(payload, i):
                    found.append((i, j, "HIGH_ENTROPY"))
                    # Skip past this window to avoid overlapping matches.
                    break
    return found


def _redacted_spans(text: str) -> list[tuple[int, int]]:
    """Return the (start, end) spans of all ``<REDACTED:...>`` markers in *text*."""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"<REDACTED:[A-Za-z0-9_]+:[a-f0-9]{8}>", text):
        spans.append((m.start(), m.end()))
    return spans


def _is_inside_redacted(pos: int, spans: list[tuple[int, int]]) -> bool:
    """Return *True* if *pos* falls inside any of the *spans*."""
    for start, end in spans:
        if start <= pos < end:
            return True
    return False


def scan_and_redact(payload: str) -> ScanResult:
    """Detect and redact secrets in *payload*.

    Runs the named-regex pass first, then an entropy pass over any remaining
    long tokens, then a sliding-window pass for Base64 secrets that span
    token boundaries.  Contextual filtering reduces false positives while
    maintaining detection of real secrets.

    Returns the scrubbed text, whether anything was detected, and the
    distinct finding labels (e.g. ``("AWS_ACCESS_KEY", "HIGH_ENTROPY")``).
    """
    if not payload or not isinstance(payload, str):
        return ScanResult(scrubbed=payload, detected=False, findings=())

    findings: list[str] = []
    scrubbed = payload

    # Pass 1 — named credential formats.
    for name, pattern in _NAMED_PATTERNS:
        def _replace(match: "re.Match[str]", _name: str = name) -> str:
            # For the broad AWS_SECRET_KEY pattern, require AWS context.
            if _name == "AWS_SECRET_KEY":
                if not _has_aws_context(payload, match.start()):
                    return match.group(0)
            findings.append(_name)
            return f"<REDACTED:{_name}:{_fingerprint(match.group(0))}>"

        scrubbed = pattern.sub(_replace, scrubbed)

    # After Pass 1, record where the redacted markers are so Pass 2 never
    # re-processes the hash fingerprints inside them.
    redacted_spans = _redacted_spans(scrubbed)

    # Pass 2 — high-entropy tokens the named patterns did not already redact.
    def _entropy_replace(match: "re.Match[str]") -> str:
        # Skip if this match is inside an already-redacted marker.
        if _is_inside_redacted(match.start(), redacted_spans):
            return match.group(0)
        token = match.group(0)
        if len(token) >= _credential_like_min_len(token) and shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            findings.append("HIGH_ENTROPY")
            return f"<REDACTED:HIGH_ENTROPY:{_fingerprint(token)}>"
        return token

    scrubbed = _ENTROPY_TOKEN.sub(_entropy_replace, scrubbed)

    # Pass 3 — sliding-window entropy for Base64 spanning token boundaries.
    # Refresh the redacted spans after Pass 2 before running Pass 3.
    redacted_spans = _redacted_spans(scrubbed)
    slide_matches = _sliding_window_entropy_scan(payload)
    if slide_matches:
        # Build a new scrubbed string by processing original payload with
        # sliding-window matches merged with named-pattern/entropy matches.
        result_parts: list[str] = []
        last_idx = 0
        for start, end, label in slide_matches:
            if start < last_idx:
                continue
            # Check if this region overlaps with an already-redacted segment.
            if any(s < end and start < e for s, e in redacted_spans):
                continue
            result_parts.append(scrubbed[last_idx:start])
            original_region = payload[start:end]
            findings.append(label)
            result_parts.append(f"<REDACTED:{label}:{_fingerprint(original_region)}>")
            last_idx = end
        result_parts.append(scrubbed[last_idx:])
        scrubbed = "".join(result_parts)

    # De-duplicate findings while preserving first-seen order.
    unique_findings = tuple(dict.fromkeys(findings))
    return ScanResult(
        scrubbed=scrubbed,
        detected=bool(unique_findings),
        findings=unique_findings,
    )
