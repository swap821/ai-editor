"""D12: launch practice workers in parallel, each fully isolated.

Each worker is `tools/organic_chain_run.py` over its own slice of the practice
ranking, with its own store, corpus worktree, trail and log, so no two share
anything a run writes. Workers are detached: they survive this process.

Cloud credentials come from the operator's keystore (Windows Credential
Manager) into each worker's environment only -- never printed, logged or
written to the launch record.

    python tools/practice_parallel.py --stream cloud --workers 3 \
        --student qwen.qwen3-coder-30b-a3b-v1:0 --teacher qwen.qwen3-coder-480b-a35b-v1:0 \
        --critic moonshotai.kimi-k3 --count 156 --out C:/d12/cloud
    python tools/practice_parallel.py --stream local --workers 1 \
        --student ollama.qwen3.5:9b@nothink --teacher ... --critic ... --count 156 --out C:/d12/local

Add --dry-run to print the plan and start nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def partition(start: int, count: int, workers: int) -> list[tuple[int, int]]:
    """Contiguous (offset, size) slices covering [start, start + count) exactly once."""
    if workers < 1 or count < 0:
        raise ValueError("workers must be >= 1 and count >= 0")
    base, extra = divmod(count, workers)
    slices, offset = [], start
    for i in range(workers):
        size = base + (1 if i < extra else 0)
        if size:
            slices.append((offset, size))
        offset += size
    return slices


def inside_repo(out: Path, corpus_prefix: str) -> str | None:
    """The first of --out / the corpus location that lies inside this repo, or None.

    Found 2026-10-12: the D12 pilots wrote their stores under the harness's
    own worktree, and organic_chain_run's containment check -- correctly --
    failed the run for "a concurrent writer" that was the run itself.
    """
    root = REPO_ROOT.resolve()
    for candidate in (out, Path(corpus_prefix).parent):
        resolved = Path(candidate).resolve()
        if resolved == root or root in resolved.parents:
            return str(candidate)
    return None


def worker_command(
    *,
    index: int,
    offset: int,
    size: int,
    student: str,
    teacher: str,
    critic: str | None,
    retries: int,
    model_timeout: int,
    out: Path,
    corpus_prefix: str,
) -> list[str]:
    cmd = [
        sys.executable,
        "-u",
        str(REPO_ROOT / "tools" / "organic_chain_run.py"),
        "--models",
        f"{student},{teacher}",
        "--teacher",
        teacher,
        "--targets",
        str(size),
        "--offset",
        str(offset),
        "--retries",
        str(retries),
        "--model-timeout",
        str(model_timeout),
        "--db",
        str(out / f"w{index}.db"),
        "--corpus-dir",
        f"{corpus_prefix}{index}",
        "--trail",
        str(out / f"w{index}.jsonl"),
    ]
    if critic:
        cmd += ["--critic", critic]
    return cmd


def cloud_environment() -> dict[str, str]:
    """This process's environment plus the stored cloud keys; values never shown."""
    from aios import config
    from aios.launcher import _keystore
    from aios.operations import keystore as ks

    env = dict(os.environ)
    store = _keystore()
    if store is not None:
        env.update(ks.production_environment(store))
    if config.BEDROCK_REGION:
        env.setdefault("AIOS_BEDROCK_REGION", config.BEDROCK_REGION)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", choices=("cloud", "local"), required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--student", required=True)
    parser.add_argument("--teacher", required=True)
    parser.add_argument("--critic", default=None)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--model-timeout", type=int, default=420)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--corpus-prefix",
        default=None,
        help="corpus worktree path prefix; worker i uses <prefix><i>. Keep it short "
        "(Windows MAX_PATH); default C:/d12<stream>",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.stream == "local" and args.workers != 1:
        print("one local worker only: one local model fits in memory")
        return 2
    if args.stream == "local" and not args.student.startswith("ollama."):
        print("the local stream's student must be a local model (ollama.<tag>)")
        return 2
    prefix = args.corpus_prefix or f"C:/d12{args.stream}"
    inside = inside_repo(args.out, prefix)
    if inside:
        print(
            f"refused: {inside} is inside this repository ({REPO_ROOT}). A training "
            "run's containment check treats ANY change under the live tree as a "
            "concurrent writer and fails the run -- including the workers' own "
            "stores. Put --out and --corpus-prefix outside it."
        )
        return 2
    slices = partition(args.start, args.count, args.workers)
    commands = [
        worker_command(
            index=i,
            offset=offset,
            size=size,
            student=args.student,
            teacher=args.teacher,
            critic=args.critic,
            retries=args.retries,
            model_timeout=args.model_timeout,
            out=args.out,
            corpus_prefix=prefix,
        )
        for i, (offset, size) in enumerate(slices)
    ]
    for i, ((offset, size), cmd) in enumerate(zip(slices, commands)):
        print(f"worker {i}: offsets {offset}..{offset + size - 1} ({size} targets)")
        print("   " + " ".join(cmd[2:]))
    if args.dry_run:
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    env = cloud_environment()
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # detached, own group
    launched = []
    for i, cmd in enumerate(commands):
        log = (args.out / f"w{i}.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        launched.append({"worker": i, "pid": proc.pid, "argv": cmd[2:]})
        print(f"launched worker {i}: pid {proc.pid}")
        time.sleep(5)  # `git worktree add` takes a repository lock
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stream": args.stream,
        "student": args.student,
        "teacher": args.teacher,
        "critic": args.critic,
        "workers": launched,
    }
    (args.out / "launch.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(f"launch record: {args.out / 'launch.json'} (no credentials in it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
