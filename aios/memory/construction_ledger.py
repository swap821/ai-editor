"""Record WHERE each legacy memory store is actually constructed, at runtime.

WHY THIS EXISTS. R11 ("One Memory Authority") claims every memory access routes
through `MemoryAuthority`, and that `aios/application/memory/bootstrap.py` is
the one place a physical store may be built. Two things were supposed to hold
that claim up, and neither can:

* `tests/test_memory_architecture.py::test_legacy_memory_construction_is_
  explicitly_quarantined` is a STATIC AST scan matching `ast.Name` only.
  Measured 2026-09-13, four of six ways to construct a store are invisible to
  it -- `skills.SkillMemory()` (an Attribute), an aliased import,
  `getattr(m, "SkillMemory")()`, and factory indirection. It is the same blind
  spot found in the governed-wiring ratchet a week earlier, in a different file.
* `runtime_proof.py`'s `memory_provenance` probe constructs `MemoryAuthority`
  itself, on a scratch database, and tests the authority's OWN semantics. It
  proves the authority works. It cannot prove the deployed system uses it.

Both answer "does any file NAME a constructor". Neither answers R11's actual
question, which is whether a RUNNING system routes through the authority. That
distinction -- artefact exists versus behaviour happens -- is what turned 54
green organs into 13 in the same week this was written.

So: the stores record their own construction, with the file that asked for
them, and the answer is read from a real run rather than from source text.

DURABLE ON PURPOSE. The entries are appended to a file under the data
directory, not held in memory, because the process that ASKS ("was anything
constructed outside bootstrap?") is usually not the process that ANSWERED --
a packaged proof runs beside the server, not inside it.

CHEAP ON PURPOSE. `sys._getframe` rather than `inspect.stack()`: the latter
resolves source context for every frame and costs milliseconds, which is not
acceptable in a constructor. Each (type, origin) pair is recorded once per
process, so a hot path cannot grow the file without bound.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

#: The composition root. The one file permitted to build a physical store.
BOOTSTRAP_ORIGIN = "aios/application/memory/bootstrap.py"

#: Pairs already recorded in this process, so a store built per-request writes
#: one line rather than thousands.
_seen: set[tuple[str, str, int]] = set()
_lock = threading.Lock()


def _enabled() -> bool:
    """Read the flag live rather than at import.

    Import-time capture would make the tripwire untestable: a test that sets the
    variable would have needed to win a race against module import.
    """
    raw = os.environ.get("AIOS_MEMORY_CONSTRUCTION_LEDGER", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def ledger_path() -> Path:
    """Where constructions are recorded.

    Resolved per call so a test can point AIOS_DATA_DIR somewhere private, and
    so the packaged runtime and the host agree without a shared import.
    """
    base = os.environ.get("AIOS_DATA_DIR")
    root = Path(base) if base else Path(__file__).resolve().parents[2] / "data"
    return root / "memory-construction.jsonl"


def _relative(filename: str) -> str:
    """A repo-relative, forward-slashed origin, or the raw path if outside it."""
    try:
        repo = Path(__file__).resolve().parents[2]
        return Path(filename).resolve().relative_to(repo).as_posix()
    except (ValueError, OSError):
        return filename.replace("\\", "/")


def record_construction(type_name: str, *, depth: int = 2) -> None:
    """Record that *type_name* was constructed, and by which file.

    `depth` is how far back the real caller sits: 2 from inside a store's
    `__init__` (this frame, then `__init__`, then the caller). A subclass that
    chains through `super().__init__()` will report the subclass rather than the
    original caller, which is the honest answer -- that IS who constructed it.

    Never raises. A tripwire that can break a constructor is worse than no
    tripwire; it would turn an audit feature into an outage.
    """
    if not _enabled():
        return
    try:
        frame = sys._getframe(depth)
        origin = _relative(frame.f_code.co_filename)
        key = (type_name, origin, frame.f_lineno)
        with _lock:
            if key in _seen:
                return
            _seen.add(key)
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "type": type_name,
                "origin": origin,
                "line": frame.f_lineno,
                "pid": os.getpid(),
            },
            sort_keys=True,
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:  # noqa: BLE001 - see the docstring: never break a caller
        return


def entries(path: Path | None = None) -> list[dict[str, Any]]:
    """Every construction recorded so far, oldest first."""
    target = path or ledger_path()
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def violations(
    path: Path | None = None, *, allowed: tuple[str, ...] = (BOOTSTRAP_ORIGIN,)
) -> list[dict[str, Any]]:
    """Constructions that did NOT come from an allowed composition root.

    This is R11's pass condition, stated as code: in a real run, every physical
    memory store must have been built by `bootstrap.py`. A non-empty result is a
    path that reached around the authority -- which is exactly the claim the
    static scan cannot test.
    """
    return [entry for entry in entries(path) if entry.get("origin") not in allowed]


def reset(path: Path | None = None) -> None:
    """Clear the record. For a proof run that wants a clean window."""
    target = path or ledger_path()
    with _lock:
        _seen.clear()
    if target.exists():
        target.unlink()
