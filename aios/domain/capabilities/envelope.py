"""GAGOS's daily envelope: the operator's once-a-day authority for its missions.

The operator's decision (2026-11-11, chosen again on 2026-11-12, "Envelope via
organs 9+10"): he approves GAGOS's own work once a day, as an envelope -- the
folders it may change, the kinds of change, how many missions, delivery by PR
only -- and merging stays his. Organ 9's one-action capability is not loosened
for it. An envelope is a capability of its own kind:

* signed by a privileged operator (a recent strong re-authentication), never
  by GAGOS, so the principal that requests a mission is never the one that
  authorises it (INVARIANT III);
* holding a fixed number of slots; each GAGOS mission inside it consumes one,
  atomically, and its record names the envelope and the slot, never his click;
* ended by expiry, by his revocation, by a newer envelope, or by any
  engagement of the emergency stop after it was signed.

This module holds the terms and their rules only. It reads no store and calls
nothing; :mod:`aios.application.capabilities.envelope` is the authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from aios.domain.capabilities.digest import payload_digest

#: The kinds of change an envelope can allow. ``tests``: only test files.
#: ``code``: any file inside its folders.
KINDS = ("tests", "code")
#: The most missions one envelope may hold.
MAX_MISSIONS = 20
#: The longest an envelope may live, in hours.
MAX_HOURS = 24
#: The only delivery an envelope allows: a pull request, merged by him.
DELIVERY = "pr"
#: Never inside an envelope, whatever its folders say (lower-case prefixes).
FORBIDDEN_PREFIXES = (
    "aios/security/",
    ".git/",
    ".github/",
    ".aios/",
    "data/",
)
_TEST_FILE = re.compile(r"(\.test\.(ts|tsx|js|jsx|mjs)$)|(^test_.*\.py$)")
#: Wildcards, control characters, and what Windows reads specially: ``:``
#: (drive letters, alternate data streams), ``<>"|``, and 8.3 short names
#: (``SECURI~1``), any of which can name a path the rules below never saw.
_UNSAFE = re.compile(r"[*?\[\]\x00-\x1f:<>\"|]|~\d")


class EnvelopeError(ValueError):
    """Terms that cannot be an envelope, or a request outside one."""


def normalise_path(path: str) -> str:
    """A repo-relative POSIX path, or :class:`EnvelopeError`. Absolute paths,
    drive letters, ``..``, wildcards and control characters are refused."""
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if not text or _UNSAFE.search(text):
        raise EnvelopeError(f"not a plain repo-relative path: {path!r}")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise EnvelopeError(f"an absolute path is never inside an envelope: {path!r}")
    parts = PurePosixPath(text).parts
    if any(part in ("..", ".") for part in parts):
        raise EnvelopeError(f"a path may not climb: {path!r}")
    # Windows drops a name's trailing dots and spaces: "security." IS
    # "security", so it would slip past the forbidden prefixes.
    if any(part != part.strip() or part.endswith(".") for part in parts):
        raise EnvelopeError(f"a path segment may not end in a dot or a space: {path!r}")
    return "/".join(parts)


def forbidden(path: str) -> bool:
    """True when *path* (normalised) is never inside an envelope: the frozen
    security core, the repository's own control files, GAGOS's data, and any
    ``.env`` file."""
    lowered = path.lower()
    if any(lowered.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return True
    return any(part.startswith(".env") for part in lowered.split("/"))


def is_test_file(path: str) -> bool:
    """A test file: ``*.test.ts(x)``/``.js(x)``/``.mjs``, or ``test_*.py``."""
    return bool(_TEST_FILE.search(PurePosixPath(path).name))


def _folder(folder: str) -> str:
    path = normalise_path(folder).rstrip("/")
    if not path:
        raise EnvelopeError("the repository root is never one folder of an envelope")
    path += "/"
    if forbidden(path):
        raise EnvelopeError(f"never inside an envelope: {folder!r}")
    return path


@dataclass(frozen=True)
class EnvelopeTerms:
    """What the operator signs: folders, kinds of change, missions, hours."""

    folders: tuple[str, ...]
    kinds: tuple[str, ...]
    max_missions: int
    hours: int
    delivery: str = DELIVERY

    @classmethod
    def build(
        cls,
        *,
        folders: list[str] | tuple[str, ...],
        kinds: list[str] | tuple[str, ...],
        max_missions: int,
        hours: int,
        delivery: str = DELIVERY,
    ) -> "EnvelopeTerms":
        """Validated, normalised terms, or :class:`EnvelopeError` saying why."""
        normalised = tuple(sorted({_folder(f) for f in folders}))
        if not normalised:
            raise EnvelopeError("an envelope names at least one folder")
        chosen = tuple(sorted(set(kinds)))
        if not chosen or any(kind not in KINDS for kind in chosen):
            raise EnvelopeError(f"kinds must be some of {', '.join(KINDS)}")
        if isinstance(max_missions, bool) or not isinstance(max_missions, int):
            raise EnvelopeError("max_missions must be a whole number")
        if not 1 <= max_missions <= MAX_MISSIONS:
            raise EnvelopeError(f"max_missions must be 1 to {MAX_MISSIONS}")
        if isinstance(hours, bool) or not isinstance(hours, int):
            raise EnvelopeError("hours must be a whole number")
        if not 1 <= hours <= MAX_HOURS:
            raise EnvelopeError(f"hours must be 1 to {MAX_HOURS}")
        if delivery != DELIVERY:
            raise EnvelopeError(f"delivery is by {DELIVERY} only; merging stays his")
        return cls(normalised, chosen, max_missions, hours, delivery)

    def as_payload(self) -> dict[str, Any]:
        return {
            "folders": list(self.folders),
            "kinds": list(self.kinds),
            "max_missions": self.max_missions,
            "hours": self.hours,
            "delivery": self.delivery,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EnvelopeTerms":
        return cls.build(**payload)

    def digest(self) -> str:
        return payload_digest(self.as_payload())

    def refusal(self, files: list[str] | tuple[str, ...], kind: str) -> str | None:
        """Why a mission changing *files* as *kind* is outside these terms, or
        None when it is inside them."""
        if kind not in self.kinds:
            return f"the envelope allows {', '.join(self.kinds)}, not {kind!r}"
        if not files:
            return "a mission names at least one file"
        for raw in files:
            try:
                path = normalise_path(raw)
            except EnvelopeError as exc:
                return str(exc)
            if forbidden(path):
                return f"never inside an envelope: {path}"
            if not any(path.lower().startswith(f.lower()) for f in self.folders):
                return f"{path} is outside the envelope's folders"
            if kind == "tests" and not is_test_file(path):
                return f"{path} is not a test file, and the envelope allows tests"
        return None


def slot_digest(
    *,
    envelope_id: str,
    terms_digest: str,
    slot: int,
    mission_id: str,
    kind: str,
    files: list[str] | tuple[str, ...],
) -> str:
    """The digest a mission's approval records for the slot it consumed."""
    return payload_digest(
        {
            "envelope_id": envelope_id,
            "terms_digest": terms_digest,
            "slot": slot,
            "mission_id": mission_id,
            "kind": kind,
            "files": sorted(normalise_path(f) for f in files),
        }
    )


__all__ = [
    "DELIVERY",
    "EnvelopeError",
    "EnvelopeTerms",
    "FORBIDDEN_PREFIXES",
    "KINDS",
    "MAX_HOURS",
    "MAX_MISSIONS",
    "forbidden",
    "is_test_file",
    "normalise_path",
    "slot_digest",
]
