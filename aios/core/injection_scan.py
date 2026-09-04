"""One prompt-injection predicate, shared by every channel that needs it.

Until 2026-09-03 injection detection existed at exactly two call sites, both on
text the USER typed (`aios/api/main.py` chat and voice). Content arriving as TOOL
OUTPUT -- a file the agent read, a command's stdout -- was never classified at
all: it passed through `scan_and_redact` (the SECRET scanner, a different
control) and was appended straight into the model's context at
`tool_agent.py`'s convo append.

`SECURITY.md` claimed "User and tool output is scanned for injection patterns
before being sent to the model". The tool-output half was false.

This module exists so the fix cannot drift into a second, subtly different
detector. Two callers, one derivation: a differential "do these two layers
agree?" gap is exactly the shape that has produced real containment escapes in
this repo before, and the cheapest way to not have one is to not have two
implementations.

FROZEN CORE: `aios/security/gateway.py` and `injection_shield.py` are frozen.
This module only CALLS `classify()`; it adds no pattern and changes no
threshold. What it adds is *reach* -- the same classifier, applied to a channel
that previously had none.
"""

from __future__ import annotations

from typing import Final, Optional

from aios.security.gateway import Zone, classify

#: Substrings that mark a RED classification as specifically an INJECTION rather
#: than some other RED reason. A file containing `rm -rf /` classifies RED for
#: destructiveness; that is not an injected instruction and must not be reported
#: as one, or the signal stops meaning anything.
_INJECTION_REASON_MARKERS: Final[tuple[str, ...]] = (
    "prompt-injection",
    "semantic prompt-injection",
)


def detect_injection(text: str) -> Optional[str]:
    """Return the gateway's reason if *text* is a prompt injection, else ``None``.

    Uses the public ``classify()`` API so the regex list and the optional vector
    shield are reused without editing frozen-core gateway code. Non-injection RED
    results are ignored: ordinary conversation, and ordinary source files, must
    not be reported as injections.
    """
    if not text or not isinstance(text, str):
        return None
    result = classify(text)
    if result.zone is not Zone.RED:
        return None
    reason = result.reason.lower()
    if any(marker in reason for marker in _INJECTION_REASON_MARKERS):
        return result.reason
    return None
