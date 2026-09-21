#!/usr/bin/env python3
"""Evidence that self-corpus training cannot touch the live tree.

Follows the house `tools/prove_*.py` pattern: run it, read the verdict, cite
the audit row. The unit tests in `tests/test_self_corpus_isolation.py` prove
the isolation against scratch repositories; this proves it against the ACTUAL
repository, which is the only claim that matters before a real training run.

It asserts, in order:

1. the live tree's fingerprint before the run;
2. a worktree is provisioned at a pinned sha, OUTSIDE the live tree;
3. the executor's scope points at that worktree and nothing else;
4. the declared suite selection is green in the worktree (the baseline without
   which a later red is unattributable);
5. the worktree is removed;
6. **the live tree's fingerprint is unchanged** — byte-identical status and HEAD.

Any failure raises. There is no partial credit: a run that disturbed the live
tree has produced evidence nobody can attribute to either tree.

    python tools/prove_self_corpus.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.self_corpus import (  # noqa: E402
    CorpusError,
    assert_isolated,
    fingerprint,
    require_green_baseline,
    self_corpus,
)

TRAIL = REPO_ROOT / ".aios" / "audit" / "self-corpus-proof.jsonl"
#: Small, fast, and dependency-free — the baseline is proving the MECHANISM
#: works, not re-proving the suite. A real training run declares its own
#: selection, matched to the module under study.
DEFAULT_SELECTION = ["tests/test_code_chunking.py"]


def main() -> int:
    repo = REPO_ROOT
    dest = repo.parent / "ai-editor-selfcorpus"
    if dest.exists():
        print(f"FAIL  destination {dest} already exists — remove it first")
        return 1

    before = fingerprint(repo)
    record: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint_before": before,
        "selection": DEFAULT_SELECTION,
    }
    print(f"live tree before   : {before[:16]}")

    try:
        with self_corpus(repo, dest) as corpus:
            record["pinned_sha"] = corpus.sha
            scope = os.environ["AIOS_SCOPE_ROOTS"]
            record["scope_roots"] = scope
            print(f"worktree           : {corpus.root}")
            print(f"pinned sha         : {corpus.sha[:12]}")
            print(f"scope during run   : {scope}")

            if Path(scope).resolve() != corpus.root.resolve():
                raise CorpusError(f"scope is not the worktree: {scope}")
            # Path containment, NOT substring containment. `str(repo) in scope`
            # reads as a safety check and is worse than none: the worktree
            # `…/ai-editor-selfcorpus` has `…/ai-editor` as a string prefix, so
            # the "check" fails a perfectly isolated run — and the symmetric
            # version would PASS a nested one whose path happened not to match.
            # A base/roots mismatch of exactly this shape has been a real
            # containment escape in this repository before.
            assert_isolated(repo, Path(scope))

            baseline = require_green_baseline(corpus, DEFAULT_SELECTION)
            record["baseline_passed"] = baseline.passed
            record["baseline_failed"] = baseline.failed
            print(f"baseline           : {baseline.passed} passed, 0 failed")
    except CorpusError as exc:
        record["verdict"] = "FAIL"
        record["error"] = str(exc)
        _append(record)
        print(f"FAIL  {exc}")
        return 1

    after = fingerprint(repo)
    record["fingerprint_after"] = after
    record["worktree_removed"] = not dest.exists()
    record["verdict"] = "PASS" if after == before and not dest.exists() else "FAIL"
    _append(record)

    print(f"live tree after    : {after[:16]}")
    print(f"worktree removed   : {not dest.exists()}")
    print(
        f"\n{record['verdict']}  "
        + (
            "the live tree is byte-identical and the worktree is gone"
            if record["verdict"] == "PASS"
            else "the live tree CHANGED or the worktree survived — inspect git status"
        )
    )
    return 0 if record["verdict"] == "PASS" else 1


def _append(record: dict[str, object]) -> None:
    TRAIL.parent.mkdir(parents=True, exist_ok=True)
    with TRAIL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
