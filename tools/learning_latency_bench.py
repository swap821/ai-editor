#!/usr/bin/env python3
"""What learning costs a turn: whole-turn latency with a populated, signed store.

Plan Phase 4c-3 (``docs/learning/PHASE4_DESIGN.md``): the learning loop's
hardening -- signed provenance verified on every recall (3c), principal scoping
(4c-1, 4c-2), the recall envelope (4a) -- must not make a turn noticeably
slower. The model dominates a live turn by seconds, so what is measured here is
everything else: a real ``/api/generate`` turn, through the real app and the
production memory authority, with the model replaced by an instant recorder.

Each run is one child process in a throwaway root, built by the learning
red-team runner's ``Harness`` (same app, same keys pinned, same isolation), so
the SAME tool can run on an older tree -- the runner's shims absorb the API
differences -- and the trees can be compared on one machine:

    python tools/learning_latency_bench.py run --out report.json

The store is seeded through each tree's own authority adapters, as the harness's
operator, so every row is signed and recall does its real work: N verified
lessons, N approved facts, N verified memories and K activated skills. Then
warm-up turns, then T timed turns whose questions overlap what was seeded.

Wall-clock numbers are this machine's. They are evidence for a budget, not a
budget: ``tests/test_learning_latency_budget.py`` holds the parts that do not
depend on the machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import learning_redteam_runner as reel  # noqa: E402

#: The topics seeded and asked about: every question overlaps several rows on
#: every channel, so recall retrieves, verifies and scopes on each turn.
TOPICS = (
    "release build",
    "parser tests",
    "router module",
    "database migration",
    "auth tokens",
    "frontend bundle",
    "cache layer",
    "deploy script",
)


def _seed(h: Any, rows: int, skills: int) -> dict[str, int]:
    """Signed rows on every learned channel, as the harness's operator."""
    from aios.core.verification_strength import VerificationStrength

    principal = h.principal_id
    seeded = {"lessons": 0, "facts": 0, "memories": 0, "skills": 0}
    lessons = h.slot("lessons")
    facts = h.slot("facts")
    semantic = h.slot("semantic")
    for i in range(rows):
        topic = TOPICS[i % len(TOPICS)]
        record = dict(
            task_id=f"bench-task-{i}",
            error_type=f"bench_{i}",
            root_cause=f"the {topic} needed step {i}",
            fix_applied=f"check the {topic} step {i}",
            lesson_text=f"When working on the {topic}, check step {i} first.",
            confidence_delta=-0.1,
            failed_command="",
        )
        reel._learn_lesson(lessons, record, principal, promote=True)
        seeded["lessons"] += 1
        reel._scoped(
            facts.add_fact,
            principal,
            topic.replace(" ", "_"),
            f"needs_step_{i}",
            f"step {i}",
            approved_by="operator:bench",
        )
        seeded["facts"] += 1
        mem = reel._scoped(
            semantic.add,
            principal,
            f"The {topic} uses convention {i}.",
            memory_type="fact",
            verification_status="verified",
        )
        reel._scoped(semantic.promote, principal, mem)
        seeded["memories"] += 1
    library = h.slot("skills")
    for i in range(skills):
        topic = TOPICS[i % len(TOPICS)]
        goal = f"inspect the {topic} notes {i}"
        for _ in range(3):
            reel._scoped(
                library.record_attempt,
                principal,
                goal,
                ["read_file: filepath=README.md"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        (record,) = [
            r for r in library.repository.list_skills() if r.problem_signature == goal
        ]
        library.repository.transition_state(
            record.skill_id, record.version, "human_reviewed"
        )
        library.repository.transition_state(record.skill_id, record.version, "active")
        reel._sign_activation(h, library, record)
        seeded["skills"] += 1
    h.cerebellum().try_compile_all()
    return seeded


def _questions(turns: int) -> list[str]:
    return [
        f"How should I approach the {TOPICS[i % len(TOPICS)]} this time?"
        for i in range(turns)
    ]


def run_child(
    root: Path,
    out: Path,
    rows: int,
    skills: int,
    turns: int,
    profile: Optional[Path] = None,
) -> int:
    harness = reel.Harness(root)
    try:
        started = time.perf_counter()
        seeded = _seed(harness, rows, skills)
        seed_s = time.perf_counter() - started
        for i, question in enumerate(_questions(3)):
            harness.turn(f"warmup-{i}", question, session=f"bench-warm-{i}")
        latencies = []
        profiler = None
        if profile is not None:
            import cProfile

            profiler = cProfile.Profile()
            profiler.enable()
        for i, question in enumerate(_questions(turns)):
            t0 = time.perf_counter()
            harness.turn(f"turn-{i}", question, session=f"bench-{i}")
            latencies.append((time.perf_counter() - t0) * 1000.0)
        if profiler is not None:
            profiler.disable()
            profiler.dump_stats(str(profile))
        statuses = sorted(set(harness.status.values()))
        recalled = sum(
            1
            for label, prompt in harness.chat.calls
            if label.startswith("turn-")
            and ("RELEVANT LESSONS" in prompt or "VERIFIED TRUSTED MEMORY" in prompt)
        )
    finally:
        harness.close()
    out.write_text(
        json.dumps(
            {
                "seeded": seeded,
                "seed_seconds": round(seed_s, 2),
                "turn_ms": [round(x, 2) for x in latencies],
                "http_status": statuses,
                "turns_with_recall": recalled,
            }
        ),
        encoding="utf-8",
    )
    return 0


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return ordered[k]


def run(rows: int, skills: int, turns: int, timeout_s: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lbench-") as tmp:
        root = Path(tmp)
        out = root / "bench.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "_child",
                "--root",
                str(root),
                "--out",
                str(out),
                "--rows",
                str(rows),
                "--skills",
                str(skills),
                "--turns",
                str(turns),
            ],
            cwd=str(REPO_ROOT),
            env={
                **reel.child_environment(root),
                # Seeding is not what is measured: the Phase 6b write cap
                # (60 a minute per table) would refuse it partway.
                "AIOS_LEARNING_WRITE_CAP_PER_MINUTE": "100000",
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        if not out.is_file():
            raise RuntimeError(
                f"bench child exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout)[-800:]}"
            )
        child = json.loads(out.read_text(encoding="utf-8"))
    ms = child["turn_ms"]
    return {
        "schema": "learning-latency-bench/1",
        "commit": reel._git("rev-parse", "HEAD"),
        "aios_tree": reel._git("rev-parse", "HEAD:aios"),
        "aios_dirty": bool(reel._git("status", "--porcelain", "--", "aios")),
        "bench_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(reel.__file__).read_bytes()).hexdigest(),
        "python": sys.version.split()[0],
        "rows_per_channel": rows,
        "skills": skills,
        **child,
        "p50_ms": round(statistics.median(ms), 1),
        "p95_ms": round(_percentile(ms, 0.95), 1),
        "max_ms": round(max(ms), 1),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    go = sub.add_parser("run", help="measure this tree")
    go.add_argument("--rows", type=int, default=50, help="rows per channel")
    go.add_argument("--skills", type=int, default=8, help="activated skills")
    go.add_argument("--turns", type=int, default=20, help="timed turns")
    go.add_argument("--timeout", type=int, default=1800)
    go.add_argument("--out", type=Path)
    child = sub.add_parser("_child")
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--out", type=Path, required=True)
    child.add_argument("--rows", type=int, required=True)
    child.add_argument("--skills", type=int, required=True)
    child.add_argument("--turns", type=int, required=True)
    child.add_argument("--profile", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "_child":
        return run_child(
            args.root, args.out, args.rows, args.skills, args.turns, args.profile
        )
    report = run(args.rows, args.skills, args.turns, args.timeout)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(
        f"{report['commit'][:12]}  rows/channel={args.rows} skills={args.skills} "
        f"turns={args.turns}  p50={report['p50_ms']} ms  p95={report['p95_ms']} ms  "
        f"max={report['max_ms']} ms  recall-in-turns={report['turns_with_recall']}"
        f"/{args.turns}  http={report['http_status']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
