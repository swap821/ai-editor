"""D12: choose the local student by a rule, before practice and before judging.

Each candidate runs the calibration targets (never judged) with NO memory, the
judged harness's own OFF arm (`learning_payoff.run_arm` with no context), one
sample each. The candidate that earns the most is the student. Ties: the
smaller model on disk, then the faster median sample.

Why: Phase 8 found qwen2.5-coder:7b at the floor (1 to 2 of 18 earned). A
student that cannot earn without memory leaves memory nothing to lift.

    python tools/calibrate_local_student.py \
        --models ollama.qwen2.5-coder:7b,ollama.qwen3.5:9b@nothink,ollama.granite4.2:8b
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import learning_payoff as lp  # noqa: E402
from tools.reverse_engineer_gagos import (  # noqa: E402
    NOTHINK,
    resolve_client,
    run_self_check,
)
from tools.self_corpus import CorpusError, self_corpus  # noqa: E402
from tools.self_corpus_targets import collect_targets  # noqa: E402

CALIBRATION = REPO_ROOT / "docs" / "learning" / "payoff_targets_calibration.txt"


def read_labels(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def ollama_sizes(host: str = "http://127.0.0.1:11434") -> dict[str, int]:
    """Bytes on disk per installed tag, for the size tie-break."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=10) as r:
            return {
                m["name"]: int(m.get("size", 0)) for m in json.loads(r.read())["models"]
            }
    except Exception:  # noqa: BLE001 - no sizes means the tie-break falls to speed
        return {}


def choose(results: dict[str, dict], sizes: dict[str, int]) -> str:
    """Most earned; then smaller on disk; then faster median sample."""

    def key(spec: str):
        r = results[spec]
        tag = spec[len("ollama.") :].removesuffix(NOTHINK)
        return (-r["earned"], sizes.get(tag, 1 << 62), r["median_seconds"])

    return min(results, key=key)


def calibrate(
    models: list[str], labels: list[str], *, corpus_dir: Path, timeout_s: int
) -> dict:
    results: dict[str, dict] = {}
    with self_corpus(REPO_ROOT, corpus_dir) as corpus:
        ok, control = run_self_check(corpus)
        if not ok:
            raise CorpusError(f"positive control failed, instrument invalid: {control}")
        by_label = {t.label: t for t in collect_targets(corpus.root)}
        missing = [label for label in labels if label not in by_label]
        if missing:
            raise CorpusError(f"calibration targets not found in the corpus: {missing}")
        for spec in models:
            client, _served = resolve_client(spec, timeout_s=timeout_s)
            rows = []
            for label in labels:
                arm = lp.run_arm(
                    corpus,
                    client,
                    by_label[label],
                    arm="off",
                    extra_context="",
                    lessons=0,
                    skills_count=0,
                )
                rows.append(
                    {
                        "target": label,
                        "earned": arm.earned,
                        "outcome": arm.outcome,
                        "reached_model": arm.reached_model,
                        "seconds": round(arm.seconds, 1),
                    }
                )
                print(f"  {spec:<36} {arm.outcome:<12} {arm.seconds:5.0f}s  {label}")
            seconds = [r["seconds"] for r in rows if r["reached_model"]]
            results[spec] = {
                "earned": sum(1 for r in rows if r["earned"]),
                "reached": sum(1 for r in rows if r["reached_model"]),
                "median_seconds": statistics.median(seconds)
                if seconds
                else float("inf"),
                "targets": rows,
            }
        corpus_sha = corpus.sha
    return {"results": results, "corpus_sha": corpus_sha, "control": control}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True, help="comma-separated ollama.<tag>[@nothink]"
    )
    parser.add_argument("--labels", type=Path, default=CALIBRATION)
    parser.add_argument("--model-timeout", type=int, default=420)
    parser.add_argument(
        "--corpus-dir", type=Path, default=REPO_ROOT.parent / "ai-editor-calib"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not all(m.startswith("ollama.") for m in models):
        print("only local models (ollama.<tag>) can be the local student")
        return 2
    labels = read_labels(args.labels)
    run = calibrate(
        models, labels, corpus_dir=args.corpus_dir, timeout_s=args.model_timeout
    )
    sizes = ollama_sizes()
    winner = choose(run["results"], sizes)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "d12-local-student",
        "rule": "most earned OFF on the calibration targets; then smaller on disk; then faster",
        "labels": str(args.labels.relative_to(REPO_ROOT).as_posix())
        if args.labels.is_relative_to(REPO_ROOT)
        else str(args.labels),
        "corpus_sha": run["corpus_sha"],
        "sizes_bytes": sizes,
        "results": run["results"],
        "student": winner,
    }
    print()
    for spec, r in run["results"].items():
        print(
            f"{spec:<36} earned {r['earned']:2d}/{len(labels)}  reached {r['reached']:2d}  "
            f"median {r['median_seconds']:.0f}s"
        )
    print(f"\nstudent: {winner}")
    if args.out:
        args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"recorded: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
