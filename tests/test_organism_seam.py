"""The backend must not speak an event the organism cannot feel.

GAGOS's two halves are joined by one idea: a backend event is simultaneously an
audit record and a gesture (``aios/core/events.py`` maps SSE names to an
``EventType`` and then to an ``EventPhase``, so the governed vocabulary IS the
body's physiological vocabulary). That seam is hand-maintained in two languages
and nothing failed when it drifted.

These tests are written to be hard to pass vacuously. The obvious suite -- "run
--check, assert 0" -- would also pass if the checker never read either
vocabulary, which is the failure mode being regressed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_organism_seam.py"
BUDGET_PATH = REPO_ROOT / ".aios" / "state" / "organism_seam_budget.json"

sys.path.insert(0, str(REPO_ROOT))

from scripts.check_organism_seam import (  # noqa: E402
    SeamParseError,
    backend_canonical_events,
    backend_cognition_events,
    diff_against_budget,
    frontend_cognition_events,
    frontend_mirror_events,
    live_gaps,
    load_budget,
)

#: The seam's high-water mark on the day this check landed. This may only go
#: DOWN. Raising it to make a failing gate pass is the one move that empties
#: the whole guard of meaning.
MAX_KNOWN_UNHEARD = 7


def test_seam_matches_the_recorded_budget():
    """--check passes at HEAD."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_new_unheard_backend_event_fails_the_check():
    """The guard fires on new drift -- its entire reason to exist.

    Without this, `test_seam_matches_the_recorded_budget` would pass even if
    --check returned 0 unconditionally.
    """
    gaps = live_gaps()
    budget = load_budget()
    assert diff_against_budget(gaps, budget) == []

    drifted = {
        **gaps,
        "unheard_cognition_events": [*gaps["unheard_cognition_events"], "new-feeling"],
    }
    problems = diff_against_budget(drifted, budget)
    assert any("new-feeling" in p for p in problems)
    assert any("no way to perceive it" in p for p in problems)


def test_a_stale_budget_entry_also_fails_the_check():
    """The list may only shrink -- so a fixed gap left in the budget is an error.

    `tools/thesis_audit.py` shipped a one-directional check by accident and it
    let docs rot in the unguarded direction. This asserts the seam budget cannot
    rot the same way.
    """
    gaps = live_gaps()
    budget = load_budget()
    stale = {
        **budget,
        "unheard_cognition_events": [*budget["unheard_cognition_events"], "verify"],
    }
    problems = diff_against_budget(gaps, stale)
    assert any("'verify' is listed as unheard" in p for p in problems)
    assert any("may only" in p and "shrink" in p for p in problems)


def test_budget_never_exceeds_the_high_water_mark():
    """The ratchet, mirroring tests/test_condition_proof_ratchet.py."""
    budget = load_budget()
    total = sum(len(v) for v in budget.values())
    assert total <= MAX_KNOWN_UNHEARD, (
        f"the seam budget records {total} unheard events, above the "
        f"{MAX_KNOWN_UNHEARD} high-water mark; this list may only shrink"
    )


def test_live_gap_never_exceeds_the_recorded_budget():
    """The second half of the ratchet: reality may not outrun the record."""
    live_total = sum(len(v) for v in live_gaps().values())
    budget_total = sum(len(v) for v in load_budget().values())
    assert live_total <= budget_total


def test_backend_vocabularies_are_read_from_the_enums():
    """The checker reads real enums, not a transcription that can go stale."""
    from aios.core.events import CanonicalEventType, EventType

    assert backend_cognition_events() == {e.value for e in EventType}
    assert backend_canonical_events() == {e.value for e in CanonicalEventType}


def test_frontend_parsers_return_plausible_vocabularies():
    """Guard the guard: a regex that stops matching must not read as 'no gaps'.

    The first version of the union parser matched the declaration before
    stripping comments and truncated at a semicolon inside a doc comment,
    returning 7 of 22 members. It raised instead of silently reporting a clean
    seam, which is the behaviour pinned here.
    """
    cognition = frontend_cognition_events()
    mirror = frontend_mirror_events()

    assert len(cognition) >= 20, f"union parse looks truncated: {sorted(cognition)}"
    assert len(mirror) >= 40, f"registry parse looks truncated: {len(mirror)} keys"

    # Spot-check members that live on both sides of the semicolon that broke
    # the first parser, so a re-truncation cannot pass.
    assert {"directive", "route", "verify", "hesitation"} <= cognition


def test_parser_raises_rather_than_reporting_an_empty_vocabulary(tmp_path):
    """A file the parser cannot read is an error, never an empty set."""
    empty = tmp_path / "cognitionBus.ts"
    empty.write_text("export type Something = 'a' | 'b';\n", encoding="utf-8")
    with pytest.raises(SeamParseError):
        frontend_cognition_events(empty)

    tiny = tmp_path / "livingMirrorRegistry.ts"
    tiny.write_text("export const R = {\n  'turn.started': {},\n};\n", encoding="utf-8")
    with pytest.raises(SeamParseError):
        frontend_mirror_events(tiny)


def test_budget_entries_are_real_backend_events():
    """The budget cannot excuse an event the backend cannot even emit."""
    budget = load_budget()
    assert set(budget["unheard_cognition_events"]) <= backend_cognition_events()
    assert set(budget["unheard_canonical_events"]) <= backend_canonical_events()


def test_budget_carries_a_reason_and_a_measurement_commit():
    """A bare list of names would not survive contact with a future reader."""
    data = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    assert len(data.get("note", "")) > 200, "the budget must explain itself"
    assert len(data.get("measured_at_commit", "")) == 40
    assert "only" in data["note"].lower() and "shrink" in data["note"].lower()
