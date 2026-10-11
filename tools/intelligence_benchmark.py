"""Which model is actually best at this operator's work? Measured, not named.

    python tools/intelligence_benchmark.py --models bedrock:qwen.qwen3-coder-480b-a35b-v1:0 ollama:qwen2.5:3b
    python tools/intelligence_benchmark.py --preset h8 --out release/intelligence/benchmark.json

The router ranks cloud models by heuristics over their names (catalog.py).
This measures instead: 30 fixed tasks -- 15 coding, 15 reasoning -- each with
an answer a checker decides mechanically, asked of every model through
production's own clients (BedrockClient, OllamaClient, OpenAICompatClient), so
the privacy filter and every client behaviour are the real ones.

Honesty rules:

* the task set is fixed in this file and committed BEFORE any run;
* no model-written code is executed; regex answers are applied to fixed
  strings in a child process with a timeout;
* a call that errored is an ERROR, never a wrong answer, and never a right one:
  accuracy is reported over answered tasks AND over all tasks;
* every result carries a 95% Wilson interval -- 15 tasks per category is
  enough to separate strong from weak, not near-equals.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SYSTEM = (
    "Answer the question. You may reason first. Then end your reply with one "
    "final line exactly in the form: ANSWER: <answer>"
)

# --------------------------------------------------------------------------- #
# Checkers
# --------------------------------------------------------------------------- #


def _norm(text: str) -> str:
    text = text.strip().strip("`").strip().strip("'\"").strip()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(".").strip().lower()


def exact(*accepted: str) -> Callable[[str], bool]:
    wanted = {_norm(a) for a in accepted}
    return lambda answer: _norm(answer) in wanted


def number(value: float) -> Callable[[str], bool]:
    def check(answer: str) -> bool:
        found = re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", "").replace("$", ""))
        return bool(found) and abs(float(found[0]) - value) < 1e-6

    return check


def json_equals(expected: Any) -> Callable[[str], bool]:
    def check(answer: str) -> bool:
        raw = answer.strip().strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        try:
            return json.loads(raw) == expected
        except (json.JSONDecodeError, ValueError):
            return False

    return check


_REGEX_CHILD = r"""
import json, re, sys
pattern, good, bad = json.loads(sys.stdin.read())
rx = re.compile(pattern)
ok = all(rx.fullmatch(s) for s in good) and not any(rx.fullmatch(s) for s in bad)
print("yes" if ok else "no")
"""


def regex_fullmatch(good: list[str], bad: list[str]) -> Callable[[str], bool]:
    """Apply the model's regex to fixed strings -- in a child, with a timeout,
    so a catastrophic pattern cannot hang the benchmark."""

    def check(answer: str) -> bool:
        pattern = answer.strip().strip("`").strip()
        if pattern.startswith(("r'", 'r"')):
            pattern = pattern[1:]
        pattern = pattern.strip("'\"")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _REGEX_CHILD],
                input=json.dumps([pattern, good, bad]),
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return False
        return proc.stdout.strip() == "yes"

    return check


# --------------------------------------------------------------------------- #
# The tasks -- fixed before any run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Task:
    task_id: str
    category: str  # coding | reasoning
    prompt: str
    check: Callable[[str], bool] = field(repr=False, compare=False)


def _code(snippet: str) -> str:
    return f"What exactly does this Python 3.12 program print?\n\n```python\n{snippet}\n```"


TASKS: tuple[Task, ...] = (
    Task(
        "c01-genexpr",
        "coding",
        _code("xs = [1, 2, 3, 4, 5, 6]\nprint(sum(x * x for x in xs if x % 2 == 0))"),
        exact("56"),
    ),
    Task(
        "c02-late-binding",
        "coding",
        _code("fs = [lambda: i for i in range(3)]\nprint([f() for f in fs])"),
        exact("[2, 2, 2]"),
    ),
    Task(
        "c03-mutable-default",
        "coding",
        _code(
            "def add(item, bucket=[]):\n    bucket.append(item)\n    return len(bucket)\n\nadd(1)\nadd(2)\nprint(add(3))"
        ),
        exact("3"),
    ),
    Task("c04-floor-mod", "coding", _code("print(-7 // 2, -7 % 2)"), exact("-4 1")),
    Task("c05-slice", "coding", _code('s = "abcdefgh"\nprint(s[::-2])'), exact("hfdb")),
    Task(
        "c06-finally",
        "coding",
        _code(
            'def f():\n    try:\n        return "try"\n    finally:\n        return "finally"\n\nprint(f())'
        ),
        exact("finally"),
    ),
    Task(
        "c07-dict-merge",
        "coding",
        _code('d = {"a": 1, "b": 2}\nd |= {"a": 3, "c": 4}\nprint(list(d.items()))'),
        exact("[('a', 3), ('b', 2), ('c', 4)]"),
    ),
    Task(
        "c08-generator",
        "coding",
        _code("g = (x for x in range(4))\nprint(sum(g), sum(g))"),
        exact("6 0"),
    ),
    Task(
        "c09-sort-key",
        "coding",
        _code(
            'words = ["bb", "a", "ccc", "dd"]\nprint(sorted(words, key=lambda w: (-len(w), w)))'
        ),
        exact("['ccc', 'bb', 'dd', 'a']"),
    ),
    Task(
        "c10-bug-mean",
        "coding",
        "This function should return the arithmetic mean of a non-empty list. Which line number has the bug? Answer with the number only.\n\n"
        "1 def mean(xs):\n2     total = 0\n3     for x in xs:\n4         total += x\n5     return total / len(xs) - 1",
        exact("5"),
    ),
    Task(
        "c11-bug-bsearch",
        "coding",
        "This binary search should return the index of target in the sorted list xs, or -1. Which line number has the bug? Answer with the number only.\n\n"
        "1 def find(xs, target):\n2     lo, hi = 0, len(xs) - 1\n3     while lo < hi:\n4         mid = (lo + hi) // 2\n5         if xs[mid] == target:\n6             return mid\n"
        "7         if xs[mid] < target:\n8             lo = mid + 1\n9         else:\n10            hi = mid - 1\n11    return -1",
        exact("3"),
    ),
    Task(
        "c12-regex-time",
        "coding",
        "Write a Python regular expression that fully matches a 24-hour time HH:MM from 00:00 to 23:59 (two-digit hour and minute) and nothing else. Give only the pattern as the answer.",
        regex_fullmatch(
            ["00:00", "09:30", "23:59", "12:05"],
            ["24:00", "23:60", "9:30", "12:5", "1234", "ab:cd"],
        ),
    ),
    Task(
        "c13-regex-date",
        "coding",
        "Write a Python regular expression that fully matches a date YYYY-MM-DD where the month is 01-12 and the day is 01-31 (no calendar check needed), and nothing else. Give only the pattern as the answer.",
        regex_fullmatch(
            ["2024-01-31", "1999-12-01", "2000-06-15"],
            [
                "2024-13-01",
                "2024-00-10",
                "2024-01-32",
                "24-01-01",
                "2024-1-01",
                "2024-01-00",
            ],
        ),
    ),
    Task(
        "c14-json-filter",
        "coding",
        'Given this JSON list of users, give the names of users OLDER than 30, sorted alphabetically, as a JSON array.\n\n[{"name": "Zoe", "age": 31}, {"name": "Adam", "age": 45}, {"name": "Bea", "age": 30}, {"name": "Cal", "age": 29}]',
        json_equals(["Adam", "Zoe"]),
    ),
    Task(
        "c15-set-ops",
        "coding",
        _code("a = {1, 2, 3, 4}\nb = {3, 4, 5}\nprint(sorted(a ^ b), len(a & b))"),
        exact("[1, 2, 5] 2"),
    ),
    Task(
        "r01-trip",
        "reasoning",
        "A train leaves at 09:40 and arrives at 13:15 the same day. How many minutes does the trip take?",
        number(215),
    ),
    Task(
        "r02-walls",
        "reasoning",
        "If 3 workers build 3 walls in 3 days, how many days do 6 workers need to build 6 walls at the same rate?",
        number(3),
    ),
    Task(
        "r03-youngest",
        "reasoning",
        "Alice is older than Bob. Carol is younger than Bob. Dave is older than Alice. Who is the youngest?",
        exact("carol"),
    ),
    Task(
        "r04-sequence",
        "reasoning",
        "What is the next number in the sequence 2, 6, 12, 20, 30, ...?",
        number(42),
    ),
    Task(
        "r05-bat-ball",
        "reasoning",
        "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How many cents does the ball cost?",
        number(5),
    ),
    Task(
        "r06-divisible",
        "reasoning",
        "How many positive integers below 100 are divisible by 3 or by 5?",
        number(46),
    ),
    Task(
        "r07-coin",
        "reasoning",
        "A fair coin is flipped 3 times. What is the probability of exactly two heads? Answer as a fraction a/b in lowest terms.",
        exact("3/8"),
    ),
    Task(
        "r08-weekday",
        "reasoning",
        "Today is Wednesday. What day of the week is it 100 days from today?",
        exact("friday"),
    ),
    Task(
        "r09-rectangle",
        "reasoning",
        "A rectangle's perimeter is 30 and its length is twice its width. What is its area?",
        number(50),
    ),
    Task(
        "r10-handshakes",
        "reasoning",
        "Five people each shake hands with every other person exactly once. How many handshakes happen?",
        number(10),
    ),
    Task(
        "r11-median",
        "reasoning",
        "What is the median of these numbers: 7, 3, 9, 1, 5, 8?",
        number(6),
    ),
    Task(
        "r12-race",
        "reasoning",
        "In a race you overtake the person in second place. What place are you in now? Answer with a number.",
        number(2),
    ),
    Task("r13-arithmetic", "reasoning", "What is 17 * 23 - 19 * 11?", number(182)),
    Task(
        "r14-discount",
        "reasoning",
        "A store discounts an $80 item by 25%, then adds 10% tax on the discounted price. What is the final price in dollars?",
        number(66),
    ),
    Task(
        "r15-knights",
        "reasoning",
        "On an island, knights always tell the truth and knaves always lie. A says: 'B is a knave.' B says: 'A and I are the same kind.' Is A a knight or a knave?",
        exact("knight", "a is a knight"),
    ),
)

# --------------------------------------------------------------------------- #
# Asking a model
# --------------------------------------------------------------------------- #


def final_answer(text: str) -> Optional[str]:
    """The last ``ANSWER:`` line; None when the model never gave one."""
    found = re.findall(r"ANSWER:\s*(.+)", text or "")
    return found[-1].strip() if found else None


def client_for(spec: str) -> tuple[Any, str]:
    provider, _, model = spec.partition(":")
    if provider == "bedrock":
        from aios import config
        from aios.core.bedrock import BedrockClient

        return BedrockClient(
            model=model, region=config.BEDROCK_REGION or "ap-south-1"
        ), model
    if provider == "ollama":
        from aios.core.llm import OllamaClient

        return OllamaClient(), model
    if provider == "openai":
        from aios.core.openai_compat import OpenAICompatClient

        return OpenAICompatClient(), model
    raise ValueError(f"unknown provider in {spec!r} (bedrock: | ollama: | openai:)")


@dataclass
class Outcome:
    task_id: str
    category: str
    passed: Optional[bool]  # None = the call errored: not measured
    answer: Optional[str]
    seconds: float
    error: Optional[str] = None


def ask(client: Any, model: str, task: Task) -> Outcome:
    started = time.monotonic()
    try:
        reply = client.chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": task.prompt},
            ],
            model=model,
        )
        text = str((reply or {}).get("content") or "")
    except Exception as exc:  # noqa: BLE001 - an error is recorded, never scored
        return Outcome(
            task.task_id,
            task.category,
            None,
            None,
            time.monotonic() - started,
            f"{type(exc).__name__}: {str(exc)[:160]}",
        )
    answer = final_answer(text)
    passed = bool(answer is not None and task.check(answer))
    return Outcome(
        task.task_id,
        task.category,
        passed,
        (answer or "")[:120],
        time.monotonic() - started,
    )


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for category in ("coding", "reasoning", "all"):
        rows = [o for o in outcomes if category == "all" or o.category == category]
        answered = [o for o in rows if o.passed is not None]
        wins = sum(1 for o in answered if o.passed)
        low, high = wilson(wins, len(rows))
        summary[category] = {
            "passed": wins,
            "tasks": len(rows),
            "errors": len(rows) - len(answered),
            "accuracy": round(wins / len(rows), 3) if rows else 0.0,
            "ci95": [round(low, 3), round(high, 3)],
        }
    seconds = [o.seconds for o in outcomes if o.passed is not None]
    summary["median_seconds"] = (
        round(statistics.median(seconds), 1) if seconds else None
    )
    return summary


def run_model(spec: str, *, workers: int) -> dict[str, Any]:
    client, model = client_for(spec)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(lambda task: ask(client, model, task), TASKS))
    return {
        "model": spec,
        "summary": summarise(outcomes),
        "outcomes": [asdict(o) for o in outcomes],
    }


PRESET_H8 = (
    "bedrock:qwen.qwen3-coder-480b-a35b-v1:0",
    "bedrock:moonshotai.kimi-k2.5",
    "bedrock:global.moonshotai.kimi-k3",
    "bedrock:moonshot.kimi-k2-thinking",
    "bedrock:deepseek.v3.2",
    "bedrock:zai.glm-5",
    "bedrock:mistral.mistral-large-3-675b-instruct",
    "bedrock:mistral.devstral-2-123b",
    "bedrock:qwen.qwen3-235b-a22b-2507-v1:0",
    "bedrock:minimax.minimax-m2.5",
    "bedrock:openai.gpt-oss-120b-1:0",
    "ollama:qwen2.5:3b",
    "ollama:qwen2.5-coder:7b",
    "ollama:qwen2.5:7b",
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--preset", choices=["h8"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    specs = list(args.models) + (list(PRESET_H8) if args.preset == "h8" else [])
    if not specs:
        parser.error("name models with --models or --preset")
    results = []
    for spec in specs:
        local = spec.startswith("ollama:")
        result = run_model(spec, workers=1 if local else 4)
        results.append(result)
        s = result["summary"]
        print(
            f"{spec:<50} coding {s['coding']['passed']:>2}/15  reasoning {s['reasoning']['passed']:>2}/15  "
            f"all {s['all']['passed']:>2}/30 {s['all']['ci95']}  errors {s['all']['errors']}  "
            f"median {s['median_seconds']}s",
            flush=True,
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [{"task_id": t.task_id, "category": t.category} for t in TASKS],
        "system_prompt": SYSTEM,
        "results": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
