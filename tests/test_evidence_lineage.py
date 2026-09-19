"""A squash-merged evidence sha may be re-pointed, but never backdated.

Five green organs (20, 23, 33, 37, 48) failed C12 with a real commit that is
permanently not an ancestor of HEAD: their branch was squash-merged as #344, so
the content landed and the commits did not. Re-verification cannot fix that --
the commit is gone from the lineage regardless of what the tests say.

Both rules below were got WRONG first and corrected by measurement, which is
why they are pinned here rather than left to the reader.
"""

from __future__ import annotations

import inspect

from scripts import verify_evidence_lineage as lineage


def test_spine_organs_are_skipped_by_construction() -> None:
    """`evidence_digest` covers these rows; only the operator can re-sign."""
    assert lineage.SPINE == {1, 2, 3, 4, 5}
    src = inspect.getsource(lineage.main)
    assert "if oid in SPINE:" in src and "continue" in src


def test_the_target_may_not_predate_the_verification() -> None:
    """The first rule I got wrong, caught by checking dates instead of trusting.

    Picking the globally earliest ancestor with matching entrypoint content
    re-pointed organ 23 to 2026-09-04 while its evidence was gathered
    2026-09-14 -- asserting a verification ten days before it happened. Equal
    content at an older commit does not mean the organ was verified there.
    """
    src = inspect.getsource(lineage.main)
    assert "floor = _commit_date(sha)" in src, "the evidence date must bound the search"
    cand = inspect.getsource(lineage._candidates)
    assert "--since=" in cand, "candidates must be filtered to at/after the evidence date"


def test_the_candidate_walk_is_not_path_filtered() -> None:
    """The second rule I got wrong.

    Walking only commits that TOUCHED the organ's entrypoints misses the squash
    merge entirely -- the content may have settled days earlier, so the merge
    does not modify those files -- and the search then falls through to HEAD,
    which asserts the evidence was gathered at HEAD. It was not.
    """
    cand = inspect.getsource(lineage._candidates)
    assert '"log", "--format=%H", "--reverse", f"--since={floor}", "HEAD"' in cand
    assert '"--", *paths' not in cand, "a path-filtered walk cannot see the squash merge"


def test_an_unprovable_organ_is_reported_not_repointed() -> None:
    """The asymmetry that makes this a verifier rather than a green-maker."""
    src = inspect.getsource(lineage.main)
    assert "if match is None:" in src
    assert "real staleness, re-verify rather than re-point" in src
    # The re-point must be unreachable when no matching ancestor was found.
    after = src.split("if match is None:", 1)[1]
    assert after.lstrip().startswith("unprovable.append")


def test_repointing_requires_byte_identical_entrypoints() -> None:
    """Content equality is the whole warrant for changing the sha."""
    src = inspect.getsource(lineage.main)
    assert "_fingerprint(c, paths) == want" in src
