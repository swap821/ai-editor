"""Derive D13's frozen target list. No model is asked; no outcome is read.

PAYOFF_PREREGISTRATION.md D13. A target is in the list when, on D12's
pre-activation store snapshot and D12's corpus commit:

1. it was never practised (``practised`` against the store's practice history,
   the harness's own rule);
2. it is not a calibration target (they chose the student);
3. production lesson recall, through the live gate for the operator, shows it
   at least one lesson (the D13 rule, ``aios/memory/relevance.py``);
4. none of those lessons is about the target itself (``about_this_target``): such
   a pair is reported apart from NOVEL, so running it measures nothing judged.

Order is the corpus ranking. The store is read through a temporary copy.

    python tools/payoff_d13_targets.py <snapshot_dir> <corpus_root> [--write]

``--write`` writes ``docs/learning/payoff_targets_d13.txt`` and the selection
report ``docs/learning/payoff_d13_selection.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools import learning_payoff as lp  # noqa: E402
from tools.self_corpus_targets import collect_targets  # noqa: E402

LEARNING = REPO / "docs" / "learning"
LIST = LEARNING / "payoff_targets_d13.txt"
REPORT = LEARNING / "payoff_d13_selection.json"
CALIBRATION = LEARNING / "payoff_targets_calibration.txt"
D12_TRAIL = LEARNING / "payoff_d12_local_trail.json"
PRINCIPAL = "operator:e2f262a7682945698e803f668c5800d1"


def _labels(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(snapshot: Path, corpus: Path) -> dict:
    from aios.memory.mistake import MistakeMemory

    tmp = Path(tempfile.mkdtemp(prefix="d13-select-"))
    try:
        copy = tmp / "aios_memory.db"
        src = sqlite3.connect(
            f"file:{(snapshot / 'aios_memory.db').as_posix()}?mode=ro", uri=True
        )
        dst = sqlite3.connect(copy)
        src.backup(dst)
        src.close()
        dst.close()
        lp.DB = copy  # the read-only provenance store the recall gate reads
        slot = lp.live_lessons_slot(MistakeMemory(copy))
        history = lp.practice_history(copy)
        if history is None:
            raise SystemExit("practice history unreadable: no selection")
        calibration = _labels(CALIBRATION)
        d12 = set(json.loads(D12_TRAIL.read_text(encoding="utf-8"))["target_labels"])
        rows = []
        for rank, target in enumerate(collect_targets(corpus)):
            lessons = slot.recall_relevant(
                lp.task_prompt(target), f"d13-select-{rank}", 5, principal=PRINCIPAL
            )
            enriched = lp.enrich_lessons(copy, lessons)
            rows.append(
                {
                    "target": target.label,
                    "novel": not lp.practised(history, target),
                    "calibration": target.label in calibration,
                    "in_d12": target.label in d12,
                    "shown": [int(item["mistake_id"]) for item in lessons],
                    "seen": any(lp.about_this_target(x, target) for x in enriched),
                }
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    chosen = [
        r
        for r in rows
        if r["novel"] and not r["calibration"] and r["shown"] and not r["seen"]
    ]
    shown = Counter(i for r in chosen for i in r["shown"])
    return {
        "rule": "PAYOFF_PREREGISTRATION.md D13: novel, not calibration, recall "
        "shows >= 1 lesson, none about the target itself",
        "store_sha256": _sha256(snapshot / "aios_memory.db"),
        "corpus_targets": len(rows),
        "novel": sum(1 for r in rows if r["novel"]),
        "novel_shown_any": sum(
            1 for r in rows if r["novel"] and not r["calibration"] and r["shown"]
        ),
        "novel_shown_seen": sum(
            1
            for r in rows
            if r["novel"] and not r["calibration"] and r["shown"] and r["seen"]
        ),
        "chosen": len(chosen),
        "chosen_from_d12_list": sum(1 for r in chosen if r["in_d12"]),
        "distinct_lesson_sets": len({tuple(sorted(r["shown"])) for r in chosen}),
        "lessons_per_target": round(
            sum(len(r["shown"]) for r in chosen) / max(len(chosen), 1), 2
        ),
        "most_shown_lessons": shown.most_common(5),
        "targets": [r["target"] for r in chosen],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    result = select(args.snapshot, args.corpus)
    print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=1))
    if args.write:
        header = [
            "# D13's judged targets, frozen (docs/learning/PAYOFF_PREREGISTRATION.md D13).",
            "#",
            "# Derived by tools/payoff_d13_targets.py, asking no model and reading no outcome:",
            "# never practised, not calibration, production recall (the D13 rule) shows",
            "# at least one lesson, and none of them is about the target itself.",
            f"# Store: D12's pre-activation snapshot, aios_memory.db sha256 {result['store_sha256'][:16]}.",
            "# Corpus: 501c25369c32, D12's. Order: the corpus ranking.",
            "",
        ]
        with LIST.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(header + result["targets"]) + "\n")
        with REPORT.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(result, indent=1) + "\n")
        print(f"wrote {LIST.relative_to(REPO).as_posix()} ({result['chosen']} targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
