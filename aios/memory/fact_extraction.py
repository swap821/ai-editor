"""Deterministic fact-candidate extraction from operator statements.

Narrative memory formation must be supervised and boring: candidates come ONLY
from the operator's own message text — never from file contents or model
output, both of which are memory-poisoning surfaces — matched by a small set
of high-precision statement patterns, capped per turn, and stored as
quarantined proposals (``SemanticFacts.propose``) that a human later approves
or rejects. False negatives are fine; a false positive costs one review click
and never reaches a prompt.
"""
from __future__ import annotations

import re

_SENTENCES = re.compile(r"([^.!?\n]+)([.!?\n]?)")

_OPERATOR_VERB = re.compile(
    r"\bi\s+(prefer|use|like|want|need)\s+(?:using\s+|to\s+use\s+)?([^,;:]{2,64})",
    re.IGNORECASE,
)
_PROJECT_VERB = re.compile(
    r"\b(?:we|this\s+project|the\s+project)\s+(uses?|runs\s+on|depends\s+on)"
    r"\s+([^,;:]{2,64})",
    re.IGNORECASE,
)
_OPERATOR_ATTR = re.compile(
    r"\bmy\s+([a-z][a-z0-9 _./-]{0,32}?)\s+is\s+([^,;:]{2,64})",
    re.IGNORECASE,
)

_VERB_NORMAL = {
    "prefer": "prefers",
    "use": "uses",
    "uses": "uses",
    "like": "likes",
    "want": "wants",
    "need": "needs",
    "runs on": "runs on",
    "depends on": "depends on",
}


def _clean_object(raw: str) -> str:
    # Stop at a trailing for-clause ("FastAPI for the backend" -> "FastAPI"),
    # collapse whitespace, and drop wrapping quotes/punctuation.
    value = re.split(r"\s+for\s+", raw.strip(), maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip(" \t\"'`.")
    return value


def extract_candidates(
    text: str, *, max_candidates: int
) -> list[tuple[str, str, str]]:
    """Return up to *max_candidates* (subject, predicate, object) candidates.

    Questions are never facts; duplicates within one text are collapsed.
    """
    limit = max(0, int(max_candidates))
    if not limit or not (text or "").strip():
        return []
    results: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(subject: str, predicate: str, obj: str) -> None:
        obj = _clean_object(obj)
        if len(obj) < 2:
            return
        key = (subject.lower(), predicate.lower(), obj.lower())
        if key in seen:
            return
        seen.add(key)
        results.append((subject, predicate, obj))

    for match in _SENTENCES.finditer(text):
        if len(results) >= limit:
            break
        sentence, terminator = match.group(1), match.group(2)
        if terminator == "?":
            continue
        for verb_match in _OPERATOR_VERB.finditer(sentence):
            verb = re.sub(r"\s+", " ", verb_match.group(1).lower())
            _add("operator", _VERB_NORMAL[verb], verb_match.group(2))
        for verb_match in _PROJECT_VERB.finditer(sentence):
            verb = re.sub(r"\s+", " ", verb_match.group(1).lower())
            _add("project", _VERB_NORMAL.get(verb, verb), verb_match.group(2))
        for attr_match in _OPERATOR_ATTR.finditer(sentence):
            name = re.sub(r"\s+", " ", attr_match.group(1).strip().lower())
            _add(f"operator.{name}", "is", attr_match.group(2))
    return results[:limit]
