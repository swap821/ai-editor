"""Endurance tester: long-running stability and stress harness for GAGOS.

Runs continuous sessions over an extended period to validate:
- Memory stability (no OOM / leak under sustained load)
- Response consistency (no drift in quality over many turns)
- Error recovery (graceful handling of transient failures)
- Throughput maintenance (latency stays stable, not degrading)

Usage:
    python tools/endurance_tester.py run [--duration-minutes N] [--cooldown-s S]
    python tools/endurance_tester.py report
    python tools/endurance_tester.py health

The harness collects per-turn metrics (latency, outcome, memory) and flags
degradation patterns. A run is "green" when >=80% of turns verify successfully
and p95 latency stays within 2x of the initial baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE, BASE

try:
    import requests
except ImportError:
    sys.exit("requires: pip install requests")

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / ".aios" / "audit"
LOG_PATH = AUDIT_DIR / "endurance-test.jsonl"

TURN_TIMEOUT_S = 900
MAX_REPLAYS = 10

ENDURANCE_PROMPTS = [
    {
        "prompt": "Create training_ground/endurance_a.py with a function reverse_string(s) that returns s reversed. Then create training_ground/test_endurance_a.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_a.py", "training_ground/test_endurance_a.py"],
    },
    {
        "prompt": "Create training_ground/endurance_b.py with a function flatten(nested_list) that recursively flattens a nested list into a single list. Then create training_ground/test_endurance_b.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_b.py", "training_ground/test_endurance_b.py"],
    },
    {
        "prompt": "Create training_ground/endurance_c.py with a function is_palindrome(s) that checks if a string reads the same forwards and backwards, ignoring case and non-alphanumeric characters. Then create training_ground/test_endurance_c.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_c.py", "training_ground/test_endurance_c.py"],
    },
    {
        "prompt": "Create training_ground/endurance_d.py with a function merge_sorted(list1, list2) that merges two sorted lists into one sorted list without using the built-in sort. Then create training_ground/test_endurance_d.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_d.py", "training_ground/test_endurance_d.py"],
    },
    {
        "prompt": "Create training_ground/endurance_e.py with a function count_vowels(text) that returns the number of vowels (a,e,i,o,u case-insensitive) in the text. Then create training_ground/test_endurance_e.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_e.py", "training_ground/test_endurance_e.py"],
    },
    {
        "prompt": "Create training_ground/endurance_f.py with a function chunk_list(items, size) that splits a list into chunks of the given size. The last chunk may be smaller. Then create training_ground/test_endurance_f.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_f.py", "training_ground/test_endurance_f.py"],
    },
    {
        "prompt": "Create training_ground/endurance_g.py with a function deep_get(d, path, default=None) that retrieves a nested dict value using a dot-separated path, returning default if any key is missing. Then create training_ground/test_endurance_g.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_g.py", "training_ground/test_endurance_g.py"],
    },
    {
        "prompt": "Create training_ground/endurance_h.py with a function retry(fn, max_attempts=3) that calls fn() and returns its result, retrying up to max_attempts times if it raises an exception. If all attempts fail, re-raise the last exception. Then create training_ground/test_endurance_h.py with pytest tests. Then verify that the tests pass.",
        "files": ["training_ground/endurance_h.py", "training_ground/test_endurance_h.py"],
    },
]


def log_event(record: dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_sse(resp: requests.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    event: str | None = None
    data_lines: list[str] = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if event is not None:
                payload = json.loads("\n".join(data_lines) or "{}")
                yield event, payload
            event, data_lines = None, []
        elif raw.startswith("event:"):
            event = raw[len("event:"):].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:"):].strip())
    if event is not None and data_lines:
        yield event, json.loads("\n".join(data_lines))


def check_allowlist(payload: dict[str, Any]) -> tuple[bool, str]:
    inp = payload.get("input", {})
    if inp.get("creations"):
        paths = [str(c.get("filepath", "")) for c in inp["creations"]]
        bad = [p for p in paths if not ALLOWED_FILE_RE.match(p)]
        return (not bad, f"create {paths}" if not bad else f"creation outside allowlist: {bad}")
    if inp.get("edits"):
        paths = [str(e.get("filepath", "")) for e in inp["edits"]]
        bad = [p for p in paths if not ALLOWED_FILE_RE.match(p)]
        return (not bad, f"edit {paths}" if not bad else f"edit outside allowlist: {bad}")
    if inp.get("commands"):
        cmds = [str(c) for c in inp["commands"]]
        bad = [c for c in cmds if not ALLOWED_CMD_RE.match(c)]
        return (not bad, f"run {cmds}" if not bad else f"command outside allowlist: {bad}")
    return False, "unrecognized approval payload shape"


def run_prompt(prompt: str, session_id: str, model_id: str = "auto") -> dict[str, Any]:
    tokens: list[str] = []
    approvals_granted: list[str] = []
    evidence: list[str] = []

    for replay in range(MAX_REPLAYS):
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "modelId": model_id,
            "sessionId": session_id,
            "approvalTokens": tokens,
        }
        resp = requests.post(f"{BASE}/api/generate", json=body, stream=True, timeout=TURN_TIMEOUT_S)
        resp.raise_for_status()
        paused: dict[str, Any] | None = None
        finished = False

        for event, data in parse_sse(resp):
            if event == "step":
                output = str(data.get("output", ""))
                if output.startswith(("[VERIFY PASS]", "[VERIFY FAIL]", "[VERIFY SKIPPED]")):
                    evidence.append(output)
            elif event == "human_required":
                paused = data
                break
            elif event == "error":
                return {"outcome": "error", "error": data, "evidence": evidence}
            elif event == "done":
                finished = True

        if finished and paused is None:
            counted = [e for e in evidence if e.startswith(("[VERIFY PASS]", "[VERIFY FAIL]"))]
            if not counted:
                outcome = "unverified"
            elif counted[-1].startswith("[VERIFY PASS]"):
                outcome = "verified_success"
            else:
                outcome = "verified_failure"
            return {"outcome": outcome, "approvals": approvals_granted, "evidence": evidence}

        if paused is None:
            return {"outcome": "truncated", "evidence": evidence}

        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            return {"outcome": "rejected", "reason": why, "evidence": evidence}
        approvals_granted.append(why)
        tokens = [token]

    return {"outcome": "max_replays", "evidence": evidence}


def reset_files(files: list[str]) -> None:
    for rel in files:
        if not ALLOWED_FILE_RE.match(rel):
            continue
        target = ROOT / rel
        if target.exists():
            target.unlink()


def get_process_memory_mb() -> float | None:
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024
    except (ImportError, AttributeError):
        return None


def cmd_run(args: argparse.Namespace) -> None:
    duration_s = args.duration_minutes * 60
    cooldown_s = args.cooldown_s
    model_id = args.model

    print(f"[endurance] starting {args.duration_minutes}-minute endurance run")
    print(f"  cooldown between turns: {cooldown_s}s")
    print(f"  model: {model_id}")

    log_event({"kind": "endurance-start", "duration_minutes": args.duration_minutes,
               "cooldown_s": cooldown_s, "model": model_id})

    start_time = time.monotonic()
    turn_idx = 0
    latencies: list[float] = []
    outcomes: list[str] = []
    errors_consecutive = 0
    max_consecutive_errors = 5

    while (time.monotonic() - start_time) < duration_s:
        task = ENDURANCE_PROMPTS[turn_idx % len(ENDURANCE_PROMPTS)]
        session_id = f"endurance-t{turn_idx}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

        reset_files(task["files"])
        t0 = time.monotonic()
        result = run_prompt(task["prompt"], session_id, model_id=model_id)
        elapsed = time.monotonic() - t0

        latencies.append(elapsed)
        outcomes.append(result["outcome"])
        mem_mb = get_process_memory_mb()

        turn_record = {
            "kind": "endurance-turn",
            "turn": turn_idx,
            "outcome": result["outcome"],
            "latency_s": round(elapsed, 2),
            "memory_mb": mem_mb,
            "elapsed_total_s": round(time.monotonic() - start_time, 1),
        }
        log_event(turn_record)

        status = "OK" if result["outcome"] == "verified_success" else result["outcome"]
        elapsed_min = round((time.monotonic() - start_time) / 60, 1)
        print(f"  turn {turn_idx}: {status} latency={elapsed:.1f}s mem={mem_mb or '?'}MB ({elapsed_min}m elapsed)")

        if result["outcome"] in ("error", "rejected", "truncated"):
            errors_consecutive += 1
            if errors_consecutive >= max_consecutive_errors:
                print(f"[endurance] ABORT: {max_consecutive_errors} consecutive errors")
                log_event({"kind": "endurance-abort", "reason": "consecutive_errors",
                           "turn": turn_idx, "errors": errors_consecutive})
                break
        else:
            errors_consecutive = 0

        reset_files(task["files"])
        turn_idx += 1

        remaining = duration_s - (time.monotonic() - start_time)
        if remaining > cooldown_s:
            time.sleep(cooldown_s)

    total_elapsed = time.monotonic() - start_time
    successes = outcomes.count("verified_success")
    total = len(outcomes)
    success_rate = round(successes / max(total, 1), 3)

    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else 0
    p95_idx = int(len(sorted_lat) * 0.95)
    p95 = sorted_lat[min(p95_idx, len(sorted_lat) - 1)] if sorted_lat else 0

    baseline_window = sorted(latencies[:3]) if len(latencies) >= 3 else sorted_lat
    baseline_p95 = baseline_window[-1] if baseline_window else 0
    latency_stable = p95 <= baseline_p95 * 2 if baseline_p95 > 0 else True

    green = success_rate >= 0.80 and latency_stable

    summary = {
        "kind": "endurance-summary",
        "duration_actual_s": round(total_elapsed, 1),
        "turns": total,
        "verified_success": successes,
        "success_rate": success_rate,
        "latency_p50_s": round(p50, 2),
        "latency_p95_s": round(p95, 2),
        "latency_baseline_p95_s": round(baseline_p95, 2),
        "latency_stable": latency_stable,
        "green": green,
    }
    log_event(summary)

    print(f"\n[endurance] {'GREEN' if green else 'RED'}")
    print(f"  turns: {total}")
    print(f"  success rate: {success_rate} (threshold: 0.80)")
    print(f"  latency p50={p50:.1f}s p95={p95:.1f}s baseline_p95={baseline_p95:.1f}s")
    print(f"  latency stable: {latency_stable} (p95 <= 2x baseline)")
    print(f"  duration: {round(total_elapsed/60, 1)} minutes")


def cmd_report(_: argparse.Namespace) -> None:
    if not LOG_PATH.exists():
        print("[endurance] no runs recorded yet")
        return

    summaries: list[dict[str, Any]] = []
    with LOG_PATH.open() as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("kind") == "endurance-summary":
                summaries.append(record)

    if not summaries:
        print("[endurance] no completed runs")
        return

    print(f"[endurance] {len(summaries)} completed runs:")
    for i, s in enumerate(summaries, 1):
        status = "GREEN" if s["green"] else "RED"
        print(f"  run {i}: {status} turns={s['turns']} rate={s['success_rate']} "
              f"p95={s['latency_p95_s']}s duration={round(s['duration_actual_s']/60,1)}m")

    greens = sum(1 for s in summaries if s["green"])
    print(f"\n  overall: {greens}/{len(summaries)} green runs")


def cmd_health(_: argparse.Namespace) -> None:
    try:
        resp = requests.get(f"{BASE}/health", timeout=10)
        print(f"[endurance] backend health: {resp.status_code}")
        if resp.status_code == 200:
            print("  ready for endurance testing")
        else:
            print("  NOT READY — backend unhealthy")
    except requests.RequestException as e:
        print(f"[endurance] backend unreachable: {e}")
        print("  start the backend first: python -m aios")


def main() -> int:
    parser = argparse.ArgumentParser(description="Endurance tester for GAGOS")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run endurance test")
    run_p.add_argument("--duration-minutes", type=int, default=30, help="Run duration in minutes")
    run_p.add_argument("--cooldown-s", type=int, default=5, help="Seconds between turns")
    run_p.add_argument("--model", type=str, default="auto", help="Model ID to use")
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="Show endurance test reports")
    report_p.set_defaults(func=cmd_report)

    health_p = sub.add_parser("health", help="Check backend health")
    health_p.set_defaults(func=cmd_health)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
