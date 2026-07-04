"""Automated organic experience accumulation harness.

Drives the GAGOS supervised chat loop through diverse capability domains
(coding, reasoning, memory recall, tool use, multi-step planning) to build
genuine experience entries in the memory system. Each session exercises a
different skill facet so the organism develops breadth, not just depth.

Usage:
    python tools/experience_accumulator.py run [--sessions N] [--domain DOMAIN]
    python tools/experience_accumulator.py status
    python tools/experience_accumulator.py domains

Domains exercised:
    coding       — create/edit files with verification
    reasoning    — multi-step logic problems
    memory       — recall from prior conversations
    tool_use     — file search, grep, navigation
    planning     — decompose complex tasks into steps
    refactoring  — improve existing code quality
"""
from __future__ import annotations

import argparse
import json
import random
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
LOG_PATH = AUDIT_DIR / "experience-accumulator.jsonl"

TURN_TIMEOUT_S = 900
MAX_REPLAYS = 10

DOMAINS: dict[str, list[dict[str, Any]]] = {
    "coding": [
        {
            "prompt": "Create training_ground/fibonacci.py with a function fib(n) that returns the nth Fibonacci number using iteration (not recursion). Then create training_ground/test_fibonacci.py with pytest tests covering fib(0), fib(1), fib(10), and fib(20). Then verify that the tests pass.",
            "files": ["training_ground/fibonacci.py", "training_ground/test_fibonacci.py"],
        },
        {
            "prompt": "Create training_ground/stack.py with a Stack class that has push(item), pop(), peek(), and is_empty() methods. pop() and peek() should raise IndexError when empty. Then create training_ground/test_stack.py with pytest tests covering all methods and edge cases. Then verify that the tests pass.",
            "files": ["training_ground/stack.py", "training_ground/test_stack.py"],
        },
        {
            "prompt": "Create training_ground/csv_parser.py with a function parse_csv(text) that splits a CSV string into a list of lists, handling quoted fields correctly. Then create training_ground/test_csv_parser.py with pytest tests covering normal fields, quoted fields with commas, and empty fields. Then verify that the tests pass.",
            "files": ["training_ground/csv_parser.py", "training_ground/test_csv_parser.py"],
        },
        {
            "prompt": "Create training_ground/binary_search.py with a function binary_search(sorted_list, target) that returns the index of target or -1 if not found. Then create training_ground/test_binary_search.py with pytest tests covering found, not found, empty list, and single element. Then verify that the tests pass.",
            "files": ["training_ground/binary_search.py", "training_ground/test_binary_search.py"],
        },
        {
            "prompt": "Create training_ground/lru_cache.py with an LRUCache class that accepts a capacity and has get(key) and put(key, value) methods. get returns -1 for missing keys. Evict the least recently used entry when capacity is exceeded. Then create training_ground/test_lru_cache.py with pytest tests. Then verify that the tests pass.",
            "files": ["training_ground/lru_cache.py", "training_ground/test_lru_cache.py"],
        },
    ],
    "reasoning": [
        {
            "prompt": "Create training_ground/matrix_rotate.py with a function rotate_90(matrix) that rotates a square 2D list 90 degrees clockwise in-place. Then create training_ground/test_matrix_rotate.py with pytest tests covering 1x1, 2x2, 3x3, and 4x4 matrices. Then verify that the tests pass.",
            "files": ["training_ground/matrix_rotate.py", "training_ground/test_matrix_rotate.py"],
        },
        {
            "prompt": "Create training_ground/parentheses.py with a function is_balanced(s) that checks if a string of brackets ()[]{}  is properly nested and balanced. Then create training_ground/test_parentheses.py with pytest tests covering balanced, unbalanced, nested, and empty strings. Then verify that the tests pass.",
            "files": ["training_ground/parentheses.py", "training_ground/test_parentheses.py"],
        },
        {
            "prompt": "Create training_ground/roman_numerals.py with functions to_roman(n) and from_roman(s) that convert between integers (1-3999) and Roman numeral strings. Then create training_ground/test_roman_numerals.py with pytest tests covering boundaries and round-trip conversion. Then verify that the tests pass.",
            "files": ["training_ground/roman_numerals.py", "training_ground/test_roman_numerals.py"],
        },
    ],
    "tool_use": [
        {
            "prompt": "Create training_ground/word_freq.py with a function word_frequencies(text) that returns a dict mapping each lowercase word to its count, ignoring punctuation. Then create training_ground/test_word_freq.py with pytest tests covering normal text, punctuation, and empty input. Then verify that the tests pass.",
            "files": ["training_ground/word_freq.py", "training_ground/test_word_freq.py"],
        },
        {
            "prompt": "Create training_ground/path_utils.py with functions normalize_path(p) that collapses .. and . components, and common_prefix(paths) that returns the longest shared directory prefix of a list of paths. Then create training_ground/test_path_utils.py with pytest tests. Then verify that the tests pass.",
            "files": ["training_ground/path_utils.py", "training_ground/test_path_utils.py"],
        },
    ],
    "planning": [
        {
            "prompt": "Create training_ground/task_scheduler.py with a class TaskScheduler that has add_task(name, duration, dependencies) and schedule() methods. schedule() returns tasks in valid topological order respecting dependencies, or raises ValueError for circular deps. Then create training_ground/test_task_scheduler.py with pytest tests. Then verify that the tests pass.",
            "files": ["training_ground/task_scheduler.py", "training_ground/test_task_scheduler.py"],
        },
        {
            "prompt": "Create training_ground/state_machine.py with a StateMachine class that accepts a dict of {state: {event: next_state}} transitions, has a current_state property, and a send(event) method that transitions or raises ValueError for invalid events. Then create training_ground/test_state_machine.py with pytest tests. Then verify that the tests pass.",
            "files": ["training_ground/state_machine.py", "training_ground/test_state_machine.py"],
        },
    ],
    "refactoring": [
        {
            "prompt": "Create training_ground/ugly_code.py with a function process_data(data) that filters even numbers, squares them, sorts descending, and returns top 5 — written as one long nested expression. Then create training_ground/clean_code.py that reimplements it readably. Then create training_ground/test_refactor.py asserting both produce identical output. Then verify that the tests pass.",
            "files": ["training_ground/ugly_code.py", "training_ground/clean_code.py", "training_ground/test_refactor.py"],
        },
        {
            "prompt": "Create training_ground/string_ops.py with functions: reverse_words(s) reverses word order, title_case(s) capitalizes first letter of each word, and truncate(s, max_len) cuts at max_len with '...' suffix if too long. Then create training_ground/test_string_ops.py with pytest tests. Then verify that the tests pass.",
            "files": ["training_ground/string_ops.py", "training_ground/test_string_ops.py"],
        },
    ],
}


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
    answer_parts: list[str] = []
    log_event({"kind": "turn-start", "session": session_id, "prompt": prompt, "model": model_id})

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
            elif event == "text_chunk":
                answer_parts.append(str(data.get("text", "")))
            elif event == "human_required":
                paused = data
                break
            elif event == "error":
                log_event({"kind": "turn-error", "session": session_id, "replay": replay, "error": data})
                return {"outcome": "error", "error": data, "evidence": evidence, "replays": replay}
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
            result = {
                "outcome": outcome,
                "replays": replay,
                "approvals": approvals_granted,
                "evidence": evidence,
                "answer_preview": "".join(answer_parts)[:400],
            }
            log_event({"kind": "turn-done", "session": session_id, **result})
            return result

        if paused is None:
            return {"outcome": "truncated", "replays": replay, "evidence": evidence}

        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            log_event({"kind": "approval-rejected", "session": session_id, "reason": why})
            return {"outcome": "rejected", "reason": why, "replays": replay, "evidence": evidence}
        approvals_granted.append(why)
        tokens = [token]

    return {"outcome": "max_replays", "replays": MAX_REPLAYS, "evidence": evidence}


def reset_files(files: list[str]) -> None:
    for rel in files:
        if not ALLOWED_FILE_RE.match(rel):
            continue
        target = ROOT / rel
        if target.exists():
            target.unlink()


def pick_sessions(domain: str | None, count: int) -> list[dict[str, Any]]:
    if domain and domain in DOMAINS:
        pool = [(domain, task) for task in DOMAINS[domain]]
    else:
        pool = [(d, task) for d, tasks in DOMAINS.items() for task in tasks]
    random.shuffle(pool)
    return [{"domain": d, **task} for d, task in pool[:count]]


def cmd_run(args: argparse.Namespace) -> None:
    sessions = pick_sessions(args.domain, args.sessions)
    results: list[dict[str, Any]] = []
    print(f"[accumulator] running {len(sessions)} sessions across domains")
    log_event({"kind": "run-start", "sessions": len(sessions), "domain": args.domain})

    for i, session in enumerate(sessions, 1):
        domain = session["domain"]
        files = session["files"]
        prompt = session["prompt"]
        session_id = f"experience-{domain}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{i}"

        print(f"\n[{i}/{len(sessions)}] domain={domain} session={session_id}")
        print(f"  prompt: {prompt[:100]}...")

        reset_files(files)
        t0 = time.monotonic()
        result = run_prompt(prompt, session_id, model_id=args.model)
        elapsed = time.monotonic() - t0

        result["domain"] = domain
        result["session_id"] = session_id
        result["elapsed_s"] = round(elapsed, 1)
        results.append(result)

        print(f"  outcome={result['outcome']} elapsed={result['elapsed_s']}s")
        log_event({"kind": "session-complete", **result})

        reset_files(files)
        if i < len(sessions):
            time.sleep(2)

    successes = sum(1 for r in results if r["outcome"] == "verified_success")
    failures = sum(1 for r in results if r["outcome"] == "verified_failure")
    errors = sum(1 for r in results if r["outcome"] in ("error", "rejected", "truncated"))
    summary = {
        "total": len(results),
        "verified_success": successes,
        "verified_failure": failures,
        "errors": errors,
        "success_rate": round(successes / max(len(results), 1), 3),
    }
    print(f"\n[accumulator] summary: {json.dumps(summary)}")
    log_event({"kind": "run-summary", **summary})


def cmd_status(_: argparse.Namespace) -> None:
    if not LOG_PATH.exists():
        print("[accumulator] no runs recorded yet")
        return
    summaries = []
    with LOG_PATH.open() as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("kind") == "run-summary":
                summaries.append(record)
    if not summaries:
        print("[accumulator] no completed runs")
        return
    print(f"[accumulator] {len(summaries)} completed runs:")
    total_sessions = sum(s["total"] for s in summaries)
    total_success = sum(s["verified_success"] for s in summaries)
    print(f"  total sessions: {total_sessions}")
    print(f"  verified successes: {total_success}")
    print(f"  cumulative success rate: {round(total_success / max(total_sessions, 1), 3)}")
    latest = summaries[-1]
    print(f"  latest run: {latest['total']} sessions, {latest['success_rate']} success rate")


def cmd_domains(_: argparse.Namespace) -> None:
    print("[accumulator] available domains:")
    for domain, tasks in DOMAINS.items():
        print(f"  {domain}: {len(tasks)} prompts")


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated organic experience accumulator")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run experience sessions")
    run_p.add_argument("--sessions", type=int, default=5, help="Number of sessions to run")
    run_p.add_argument("--domain", type=str, default=None, help="Limit to one domain")
    run_p.add_argument("--model", type=str, default="auto", help="Model ID to use")
    run_p.set_defaults(func=cmd_run)

    status_p = sub.add_parser("status", help="Show accumulation status")
    status_p.set_defaults(func=cmd_status)

    domains_p = sub.add_parser("domains", help="List available domains")
    domains_p.set_defaults(func=cmd_domains)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
