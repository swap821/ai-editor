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

#: The HARD tier (added 2026-10-11 after six models scored 30/30 on TASKS):
#: fixed and committed before its first run, answer key verified the same way.
TASKS_HARD: tuple[Task, ...] = (
    Task(
        "hc01-class-attr",
        "coding",
        _code(
            "class A:\n    items = []\n    def __init__(self):\n        self.items.append(len(self.items))\n\n"
            "a, b = A(), A()\nprint(a.items, b.items is a.items)"
        ),
        exact("[0, 1] True"),
    ),
    Task(
        "hc02-gen-send",
        "coding",
        _code(
            "def g():\n    x = yield 1\n    y = yield x * 2\n    yield x + y\n\n"
            "it = g()\nprint(next(it), it.send(5), it.send(10))"
        ),
        exact("1 10 15"),
    ),
    Task(
        "hc03-mro",
        "coding",
        _code(
            'class A:\n    def who(self):\n        return "A"\n\n'
            'class B(A):\n    def who(self):\n        return "B" + super().who()\n\n'
            'class C(A):\n    def who(self):\n        return "C" + super().who()\n\n'
            'class D(B, C):\n    def who(self):\n        return "D" + super().who()\n\n'
            "print(D().who())"
        ),
        exact("DBCA"),
    ),
    Task(
        "hc04-slice-assign",
        "coding",
        _code(
            'xs = [0, 1, 2, 3, 4, 5]\nxs[1:5:2] = ["a", "b"]\ndel xs[::3]\nprint(xs)'
        ),
        exact("['a', 2, 4, 5]"),
    ),
    Task(
        "hc05-groupby",
        "coding",
        _code(
            'from itertools import groupby\n\ns = "aaabccaa"\n'
            "print([(k, len(list(g))) for k, g in groupby(s)])"
        ),
        exact("[('a', 3), ('b', 1), ('c', 2), ('a', 2)]"),
    ),
    Task(
        "hc06-finally-order",
        "coding",
        _code(
            "out = []\n\ndef f():\n    try:\n        out.append(1)\n        raise ValueError\n"
            "    except ValueError:\n        out.append(2)\n        return 3\n    finally:\n"
            "        out.append(4)\n\nr = f()\nprint(r, out)"
        ),
        exact("3 [1, 2, 4]"),
    ),
    Task(
        "hc07-bug-mutation",
        "coding",
        "This function should remove later duplicates from the list, keeping each first "
        "occurrence. Which line number makes it misbehave on some inputs? Answer with the "
        "number only.\n\n"
        "1 def dedupe(xs):\n2     seen = set()\n3     for x in xs:\n4         if x in seen:\n"
        "5             xs.remove(x)\n6         seen.add(x)\n7     return xs",
        exact("5"),
    ),
    Task(
        "hc08-regex-ipv4",
        "coding",
        "Write a Python regular expression that fully matches a dotted IPv4 address: four "
        "decimal octets 0-255, no leading zeros (except the single digit 0), and nothing "
        "else. Give only the pattern as the answer.",
        regex_fullmatch(
            ["0.0.0.0", "255.255.255.255", "192.168.1.10", "10.0.0.1"],
            ["256.1.1.1", "01.2.3.4", "1.2.3", "1.2.3.4.5", "192.168.1.1a", "1..2.3"],
        ),
    ),
    Task(
        "hc09-json-aggregate",
        "coding",
        "Given these orders, give the total amount per customer as a JSON object mapping "
        'customer to total.\n\n[{"c": "ann", "amt": 5}, {"c": "bob", "amt": 3}, '
        '{"c": "ann", "amt": 7}, {"c": "cy", "amt": 0}]',
        json_equals({"ann": 12, "bob": 3, "cy": 0}),
    ),
    Task(
        "hc10-zip-star",
        "coding",
        _code(
            "pairs = [(1, 'a'), (2, 'b'), (3, 'c')]\nnums, letters = zip(*pairs)\n"
            "print(sum(nums), ''.join(reversed(letters)))"
        ),
        exact("6 cba"),
    ),
    Task(
        "hr01-trailing-zeros",
        "reasoning",
        "How many trailing zeros does 125! (125 factorial) have?",
        number(31),
    ),
    Task(
        "hr02-clock",
        "reasoning",
        "A clock shows 3:15. What is the smaller angle between the hour hand and the minute hand, in degrees?",
        number(7.5),
    ),
    Task(
        "hr03-level",
        "reasoning",
        "How many distinct arrangements of the letters of the word LEVEL are there?",
        number(30),
    ),
    Task(
        "hr04-dice",
        "reasoning",
        "Two fair six-sided dice are rolled. What is the probability that the sum is 8? Answer as a fraction a/b in lowest terms.",
        exact("5/36"),
    ),
    Task(
        "hr05-monty",
        "reasoning",
        "In the classic Monty Hall problem with 3 doors, if you always switch, what is the probability you win the car? Answer as a fraction a/b.",
        exact("2/3"),
    ),
    Task(
        "hr06-nines",
        "reasoning",
        "If you write out every integer from 1 to 100, how many times do you write the digit 9?",
        number(20),
    ),
    Task(
        "hr07-snail",
        "reasoning",
        "A snail climbs 3 m up a 10 m wall each day and slips back 2 m each night. On which day does it first reach the top?",
        number(8),
    ),
    Task(
        "hr08-remainder",
        "reasoning",
        "What is the smallest positive integer that leaves remainder 1 when divided by each of 2, 3, 4, 5 and 6, and is divisible by 7?",
        number(301),
    ),
    Task(
        "hr09-round-table",
        "reasoning",
        "In how many ways can 8 people be seated around a round table, if rotations of the same seating count as one?",
        number(5040),
    ),
    Task(
        "hr10-boxes",
        "reasoning",
        "Three boxes are labelled Apples, Oranges and Mixed, and every label is wrong. You draw one fruit from the box "
        "labelled Mixed and it is an apple. What does the box labelled Oranges contain: apples, oranges or mixed?",
        exact("mixed", "mixed fruit", "mixed fruits"),
    ),
)

SUITES = {"basic": TASKS, "hard": TASKS_HARD, "all": TASKS + TASKS_HARD}

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


def run_model(
    spec: str, *, workers: int, tasks: tuple[Task, ...] = TASKS
) -> dict[str, Any]:
    client, model = client_for(spec)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(lambda task: ask(client, model, task), tasks))
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


#: Benchmark category -> the router's task name (aios/core/model_selector.py).
ROUTER_TASKS = {"coding": "coding", "reasoning": "reasoning", "all": "general"}
#: A model is rated for a task only with at least this many ANSWERED tasks.
MIN_ANSWERED = 10


def emit_rates(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine benchmark reports into router calibration rates.

    Per model and category, over every report: passed / answered. Errored
    calls are not answers and never count; a model with fewer than
    MIN_ANSWERED answered tasks in a category is not rated for it."""
    tallies: dict[tuple[str, str, str], list[int]] = {}
    for report in reports:
        for result in report.get("results", []):
            provider, _, model = str(result["model"]).partition(":")
            for outcome in result.get("outcomes", []):
                if outcome.get("passed") is None:
                    continue
                for category in (outcome["category"], "all"):
                    key = (provider, model, ROUTER_TASKS[category])
                    passed, answered = tallies.get(key, [0, 0])
                    tallies[key] = [passed + int(bool(outcome["passed"])), answered + 1]
    rates = [
        {
            "provider": provider,
            "model": model,
            "task": task,
            "rate": round(passed / answered, 4),
            "n": answered,
        }
        for (provider, model, task), (passed, answered) in sorted(tallies.items())
        if answered >= MIN_ANSWERED
    ]
    return {
        "source": "tools/intelligence_benchmark.py",
        "measured_at": sorted(str(r.get("generated_at", "")) for r in reports)[-1:]
        or [""],
        "suites": sorted({str(r.get("suite", "basic")) for r in reports}),
        "rates": rates,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--preset", choices=["h8"])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--suite", choices=sorted(SUITES), default="basic")
    parser.add_argument(
        "--emit-rates",
        type=Path,
        default=None,
        help="write router calibration rates from --from reports, then exit",
    )
    parser.add_argument("--from", dest="sources", type=Path, nargs="*", default=[])
    args = parser.parse_args(argv)
    if args.emit_rates:
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in args.sources]
        if not reports:
            parser.error("--emit-rates needs --from REPORT [REPORT ...]")
        rated = emit_rates(reports)
        args.emit_rates.parent.mkdir(parents=True, exist_ok=True)
        args.emit_rates.write_text(json.dumps(rated, indent=2) + "\n", encoding="utf-8")
        print(f"{len(rated['rates'])} rates -> {args.emit_rates}")
        return 0
    tasks = SUITES[args.suite]
    specs = list(args.models) + (list(PRESET_H8) if args.preset == "h8" else [])
    if not specs:
        parser.error("name models with --models or --preset")
    results = []
    for spec in specs:
        local = spec.startswith("ollama:")
        result = run_model(spec, workers=1 if local else 4, tasks=tasks)
        results.append(result)
        s = result["summary"]
        print(
            f"{spec:<50} coding {s['coding']['passed']:>2}/{s['coding']['tasks']}  "
            f"reasoning {s['reasoning']['passed']:>2}/{s['reasoning']['tasks']}  "
            f"all {s['all']['passed']:>2}/{s['all']['tasks']} {s['all']['ci95']}  "
            f"errors {s['all']['errors']}  "
            f"median {s['median_seconds']}s",
            flush=True,
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "tasks": [{"task_id": t.task_id, "category": t.category} for t in tasks],
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
