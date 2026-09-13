"""R11's packaged proof: which file actually built the store, at runtime.

WHY THIS FILE EXISTS. R11 ("One Memory Authority") claims memory access routes
through `MemoryAuthority`, with `aios/application/memory/bootstrap.py` the one
place a physical store may be constructed. Its row in the convergence ledger has
read "Packaged runtime proof stays open" for two months, and the reason it never
closed is that **the proof obligation had no definition** -- nobody had written
down what would satisfy it.

Two mechanisms were standing in for it, and both answer a different question:

* `test_memory_architecture.py::test_legacy_memory_construction_is_explicitly_
  quarantined` is a STATIC AST scan matching `ast.Name` only. Measured
  2026-09-13, four of six ways to construct a store walk straight past it --
  `skills.SkillMemory()`, an aliased import, `getattr(m, "SkillMemory")()`, and
  factory indirection. That is the same blind spot found in the governed-wiring
  ratchet the week before, in a different file.
* `runtime_proof.py`'s `memory_provenance` probe constructs `MemoryAuthority`
  itself on a scratch database and tests the authority's OWN semantics. It
  proves the authority works. It cannot prove the deployed system uses it.

Both ask "does a file NAME a constructor". R11 asks whether a RUNNING system
routes through the authority. Artefact-exists versus behaviour-happens -- the
exact distinction that turned 54 green organs into 13 the same week.

THE DEFINITION, stated so it can be closed:

    In a real run, every physical memory store constructed must have been built
    by `bootstrap.py`, and that is read from the run itself rather than from
    source text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aios.memory import construction_ledger as ledger


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """A private data dir, so a test never reads the developer's real ledger."""
    monkeypatch.setenv("AIOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AIOS_MEMORY_CONSTRUCTION_LEDGER", "1")
    ledger.reset()
    yield tmp_path
    ledger.reset()


def test_the_shapes_the_static_scan_cannot_see_are_recorded(isolated) -> None:
    """THE BAR. Four of these are invisible to the AST quarantine scan.

    The scan matches `ast.Name` only, so a store reached through a module
    attribute, an alias, `getattr`, or a factory is constructed without any
    source file appearing to name it. At runtime there is no such hiding place:
    the constructor runs, so the construction is recorded.
    """
    from aios.memory import skills
    from aios.memory.skills import SkillMemory as Aliased

    def factory(cls):
        return cls()

    skills.SkillMemory()
    Aliased()
    factory(skills.SkillMemory)

    recorded = ledger.entries()

    assert recorded, "no construction was recorded at all"
    assert all(entry["type"] == "SkillMemory" for entry in recorded)
    # Every one is a violation: none came from the composition root.
    assert len(ledger.violations()) == len(recorded)


def test_a_factory_is_attributed_to_the_frame_that_built_it(isolated) -> None:
    """Attribution must name who actually constructed, not who asked.

    A helper that builds on someone else's behalf IS the construction site; that
    is the honest answer and the one that makes a violation actionable.
    """
    from aios.memory import skills

    def build_it():
        return skills.SkillMemory()

    build_it()

    origins = {entry["origin"] for entry in ledger.entries()}
    assert any(
        origin.endswith("test_memory_construction_ledger.py") for origin in origins
    )


def test_the_real_bootstrap_path_has_no_violations(isolated) -> None:
    """R11's PASS CONDITION, on the real composition root.

    This is the positive half of the proof: building the authority the way the
    application builds it must construct stores ONLY from bootstrap.py.
    """
    from aios.application.memory.bootstrap import build_memory_authority

    build_memory_authority()

    recorded = ledger.entries()
    violations = ledger.violations()

    assert recorded, "bootstrap constructed nothing -- the tripwire is not wired"
    assert not violations, (
        "a physical memory store was built outside the composition root: "
        f"{[(v['type'], v['origin'], v['line']) for v in violations]}"
    )
    assert all(entry["origin"] == ledger.BOOTSTRAP_ORIGIN for entry in recorded)


def test_the_flag_turns_it_off(isolated, monkeypatch) -> None:
    """An always-on audit needs an off switch that genuinely stops the writing."""
    monkeypatch.setenv("AIOS_MEMORY_CONSTRUCTION_LEDGER", "0")
    from aios.memory import skills

    skills.SkillMemory()

    assert ledger.entries() == []


def test_the_flag_is_read_live_not_at_import(isolated, monkeypatch) -> None:
    """Capturing the flag at import would make it untestable.

    A test setting the variable would have had to win a race against module
    import, so the value is read per call instead.
    """
    monkeypatch.setenv("AIOS_MEMORY_CONSTRUCTION_LEDGER", "0")
    from aios.memory import skills

    skills.SkillMemory()
    assert ledger.entries() == []

    monkeypatch.setenv("AIOS_MEMORY_CONSTRUCTION_LEDGER", "1")
    skills.SkillMemory()
    assert ledger.entries(), "re-enabling the flag did not resume recording"


def test_a_broken_ledger_never_breaks_a_constructor(isolated, monkeypatch) -> None:
    """A tripwire that can raise is worse than no tripwire.

    It would convert an audit feature into an outage on a hot path. Point it at
    an unwritable location and the store must still construct.
    """
    monkeypatch.setattr(
        ledger, "ledger_path", lambda: Path("\x00nonexistent") / "x.jsonl"
    )
    from aios.memory import skills

    store = skills.SkillMemory()  # must not raise

    assert store is not None


def test_recorded_lines_are_machine_readable(isolated) -> None:
    """A packaged proof reads this file from another process.

    It must therefore be parseable without importing anything from the writer.
    """
    from aios.memory import skills

    skills.SkillMemory()

    raw = (isolated / "memory-construction.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]

    assert rows
    for row in rows:
        assert set(row) == {"type", "origin", "line", "pid"}
        assert isinstance(row["pid"], int) and row["pid"] == os.getpid()
