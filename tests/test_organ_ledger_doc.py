"""The organ-status prose must be generated from the machine ledger.

Regression suite for the 2026-08-02 drift: PRs #185-#187 moved eight organs to
green in `.aios/state/ORGAN_GREEN_LEDGER.json` and left
`docs/architecture/GAGOS_54_ORGANS.md` claiming 38 green / 16 yellow. CI stayed
green throughout, because the only guard on that file was the manifest hash pin
-- which proves the file has not changed, not that it is true.

These tests are written to be hard to pass vacuously, because the obvious
version of this suite ("run --check, assert it returns 0") would also pass if
the generator were a no-op that never read the ledger at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_organ_ledger_doc.py"

sys.path.insert(0, str(REPO_ROOT))

from scripts.build_organ_ledger_doc import (  # noqa: E402
    BEGIN_MARKER,
    END_MARKER,
    apply_block,
    load_rows,
    render_block,
)


def _counts(rows):
    green = sum(1 for r in rows if r["status"] == "green")
    return green, len(rows) - green


def test_generated_region_is_current_against_the_ledger():
    """--check passes at HEAD: the committed prose matches the machine ledger."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_fails_when_the_ledger_moves_ahead_of_the_prose():
    """The guard actually fires -- this is the 2026-08-02 drift, reproduced.

    Without this case the suite above would pass even if `--check` returned 0
    unconditionally, which is precisely the failure mode being regressed: a
    check that never fails is indistinguishable from no check.
    """
    rows = load_rows()
    doc_text = (REPO_ROOT / "docs/architecture/GAGOS_54_ORGANS.md").read_text(
        encoding="utf-8"
    )
    current_block = render_block(rows, ledger_digest="x" * 64)

    # Simulate a merged PR that flipped one organ's status in the JSON only.
    #
    # This used to require a non-green organ to exist in the shipped ledger and
    # raised StopIteration on 2026-08-19, when organ 23 went green and the ledger
    # reached 54/54. The property under test is that the renderer READS `status`
    # -- it never depended on which colour was scarce, so it no longer asks.
    moved = [dict(r) for r in rows]
    victim = next((r for r in moved if r["status"] != "green"), None)
    if victim is None:
        victim = moved[0]
        victim["status"] = "yellow"
    else:
        victim["status"] = "green"
    moved_block = render_block(moved, ledger_digest="x" * 64)

    assert moved_block != current_block, (
        "flipping an organ's status in the ledger must change the rendered prose; "
        "if it does not, the generator is not reading `status`"
    )
    assert apply_block(doc_text, moved_block) != doc_text


def test_rendered_counts_match_the_ledger_exactly():
    """The counts in the prose are computed, not transcribed."""
    rows = load_rows()
    green, yellow = _counts(rows)
    block = render_block(rows, ledger_digest="x" * 64)

    assert f"{green} green / {yellow} yellow / {len(rows)} total" in block
    assert f"### Green ({green})" in block
    assert f"### Yellow ({yellow})" in block


def test_every_organ_appears_exactly_once():
    """No organ can be silently dropped from the generated tables."""
    rows = load_rows()
    block = render_block(rows, ledger_digest="x" * 64)
    table_rows = [ln for ln in block.splitlines() if ln.startswith("| ")]
    ids = [ln.split("|")[1].strip() for ln in table_rows]
    ids = [i for i in ids if i.isdigit()]

    assert sorted(map(int, ids)) == sorted(int(r["organ_id"]) for r in rows)
    assert len(ids) == len(set(ids)), "an organ was rendered twice"


def test_yellow_rows_carry_their_real_residual():
    """A yellow organ must show the ledger's own known_blockers, not a placeholder.

    The drift was not only in the counts: organs 33 and 35 were still blamed on
    "no Ollama" after live Ollama evidence landed. Rendering residuals from the
    ledger is what makes that class of staleness impossible.
    """
    rows = load_rows()

    # A SYNTHETIC yellow, always present, so the property is tested whatever
    # colour the shipped ledger happens to be. This asserted "expected at least
    # one yellow organ with a blocker" and failed on 2026-08-19, when organ 23
    # went green and the ledger reached 54/54 -- the renderer had not changed,
    # the fixture had simply run out. A guard that can only fire while the repo
    # is imperfect stops guarding the moment it succeeds.
    probe_rows = [dict(r) for r in rows]
    probe_rows[0]["status"] = "yellow"
    probe_rows[0]["known_blockers"] = [
        "SYNTHETIC RESIDUAL for the ledger-doc renderer, never shipped"
    ]

    for source in (probe_rows, rows):
        block = render_block(source, ledger_digest="x" * 64)
        yellows = [
            r
            for r in source
            if r["status"] != "green" and (r.get("known_blockers") or [])
        ]
        for row in yellows:
            first = " ".join(str(row["known_blockers"][0]).split())
            # Compare on a distinctive prefix; the renderer flattens whitespace.
            probe = first[:40].replace("|", "\\|")
            assert probe in block, (
                f"organ {row['organ_id']} residual missing from prose"
            )

    # And the synthetic case must genuinely have exercised the loop above.
    assert any(r["status"] != "green" for r in probe_rows)


def test_history_above_the_region_is_never_rewritten():
    """The append-only narrative is preserved byte for byte.

    The generator owns one delimited region. If it ever reflowed the whole file
    it would destroy the dated evidence the doc's own convention protects.
    """
    doc_text = (REPO_ROOT / "docs/architecture/GAGOS_54_ORGANS.md").read_text(
        encoding="utf-8"
    )
    start = doc_text.find(BEGIN_MARKER)
    assert start != -1, "generated region marker is missing from the ledger doc"

    history = doc_text[:start]
    rewritten = apply_block(doc_text, render_block(load_rows(), ledger_digest="y" * 64))
    assert rewritten[:start] == history

    # And the hand-written reconciliation record survives.
    assert "Prose-to-ledger reconciliation (appended 2026-08-04)" in rewritten


def test_refuses_to_guess_when_a_marker_is_missing():
    """A half-present region is an error, not a silent append."""
    with pytest.raises(SystemExit):
        apply_block(f"intro\n{BEGIN_MARKER}\nbody without an end\n", "block")

    with pytest.raises(SystemExit):
        apply_block(f"intro\nbody\n{END_MARKER}\n", "block")


def test_generator_is_idempotent():
    """Running it twice changes nothing the second time."""
    rows = load_rows()
    block = render_block(rows, ledger_digest="z" * 64)
    doc_text = (REPO_ROOT / "docs/architecture/GAGOS_54_ORGANS.md").read_text(
        encoding="utf-8"
    )
    once = apply_block(doc_text, block)
    assert apply_block(once, block) == once


def test_ledger_json_is_the_only_status_source():
    """The script must not carry a hardcoded organ count or status table.

    A generator with the answers baked in would satisfy every test above while
    reintroducing exactly the hand-maintained duplicate this replaces.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    rows = load_rows()
    green, yellow = _counts(rows)

    body = source.split('"""', 2)[-1]  # ignore the module docstring's history notes

    # Count-SHAPED literals only. A bare `str(len(rows))` check matches "54" in
    # the filename GAGOS_54_ORGANS.md and fails on a correct generator -- which
    # is what this assertion did on first run.
    for literal in (f"{green} green", f"{yellow} yellow", f"{len(rows)} total"):
        assert literal not in body, (
            f"{literal!r} appears as a literal in the generator body; counts must "
            "be derived from the ledger"
        )


def test_ledger_path_matches_the_manifest_tracked_doc():
    """The generated doc is the same file the release manifest hash-pins."""
    manifest = json.loads(
        (REPO_ROOT / "release" / "organ-proof-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    # The manifest is written with OS-native separators, so normalise before
    # comparing -- asserting on forward slashes alone passes on Linux CI and
    # fails on the Windows host this repo is developed on.
    tracked = {p.replace("\\", "/") for p in manifest.get("files", {})}
    assert "docs/architecture/GAGOS_54_ORGANS.md" in tracked, (
        "the manifest no longer pins the generated doc; the generation guard and "
        "the tamper guard must cover the same file"
    )
