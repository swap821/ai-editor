"""Clerk benchmark v1: which model is the best clerk, measured on real clerk jobs.

The qualification suite (r15-v3) is pass/fail and saturated: every installed
local model scored 22/22 on 2026-10-12, so it cannot pick the best one. This
benchmark grades QUALITY on 54 synthetic clerk jobs, 6 for each of 9 job
profiles (`docs/clerk/clerk_benchmark_v1.json`):
- longer texts, distractors and near-duplicates;
- "no skill fits" cases;
- prompt injection inside the data.

How it stays honest:
- **Independent author.** The jobs and their answers were written by Claude,
  which is not one of the tested models, so no model sits its own exam.
- **No model judges.** Grading is deterministic:
  - structured answers are compared exactly: labels, fields, groups, missing
    fields and skill choice;
  - free text is checked for the facts it must keep and the facts it must not
    invent.
- **The production path.** Every model runs through the production clerk
  runtime (`StructuredClericalRuntime.execute_job`), with its validation and
  retries:
  - local models are called with think=false, as the clerk calls them (#481);
  - cloud models go through the gateway's chat adapter, plus a JSON extractor
    the cloud clerk will also need (a chat reply may wrap the object in prose).
- **No operator data.** Every job is synthetic, so a cloud run sends nothing
  of the operator's.

    python tools/clerk_benchmark.py --models ollama.qwen2.5-coder:7b,ollama.granite4.2:8b \
        --out docs/clerk/clerk_benchmark_v1_result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

JOBS = REPO_ROOT / "docs" / "clerk" / "clerk_benchmark_v1.json"
_NULLS = (None, "null", "none", "")


def load_jobs(path: Path = JOBS) -> tuple[list[dict], str]:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return json.loads(raw)["jobs"], hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ grading


def _norm(value: Any) -> str:
    return str(value).strip().lower()


def _name(value: Any) -> str:
    return _norm(value).replace(" ", "_").replace("-", "_")


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected or _norm(actual) == _norm(expected)
    if isinstance(expected, (int, float)):
        got = _number(actual)
        return got is not None and abs(got - float(expected)) < 1e-9
    return _norm(actual) == _norm(expected)


def grade(job: dict, output: dict | None) -> tuple[bool, list[str]]:
    """(correct, failed checks). Correct only if EVERY check passes."""
    if not isinstance(output, dict):
        return False, ["no valid output"]
    expect, failed = job["expect"], []
    for field, value in expect.get("exact", {}).items():
        if not _same(value, output.get(field)):
            failed.append(f"{field}: expected {value!r}, got {output.get(field)!r}")
    for field in expect.get("null", []):
        if output.get(field) not in _NULLS:
            failed.append(f"{field}: expected null, got {output.get(field)!r}")
    for field, values in expect.get("set", {}).items():
        got = output.get(field)
        got_set = {_name(v) for v in got} if isinstance(got, list) else None
        if got_set != {_name(v) for v in values}:
            failed.append(f"{field}: expected {sorted(values)}, got {got!r}")
    if "groups" in expect:
        spec = expect["groups"]
        got = output.get(spec["field"])
        if not isinstance(got, list) or not all(isinstance(g, list) for g in got):
            failed.append(f"{spec['field']}: not a list of groups: {got!r}")
        else:
            got_groups = {frozenset(_name(i) for i in g) for g in got if len(g) >= 2}
            want = {frozenset(_name(i) for i in g) for g in spec["value"]}
            if got_groups != want:
                failed.append(f"{spec['field']}: expected {spec['value']}, got {got!r}")
    if "facts" in expect:
        spec = expect["facts"]
        text = _norm(output.get(spec["field"], ""))
        for alternatives in spec.get("all", []):
            if not any(a.lower() in text for a in alternatives):
                failed.append(f"missing fact: one of {alternatives}")
        for banned in spec.get("none", []):
            if banned.lower() in text:
                failed.append(f"invented or contradicted: {banned!r}")
        limit = expect.get("max_chars")
        if limit and len(text) > limit:
            failed.append(f"too long: {len(text)} > {limit} chars")
    return not failed, failed


# ------------------------------------------------------------------ clients


class _JsonFromChat:
    """A cloud chat reply may wrap the JSON object in prose or a code fence."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        raw = self.inner.complete(prompt, system=system, json_mode=json_mode)
        start, end = raw.find("{"), raw.rfind("}")
        return raw[start : end + 1] if start != -1 and end > start else raw


def make_client(spec: str, *, timeout_s: int) -> Any:
    """The clerk's own client for a local model; the gateway adapter for cloud."""
    if spec.startswith("ollama."):
        from aios import config
        from aios.core.llm import OllamaClient

        return OllamaClient(
            model=spec[len("ollama.") :],
            timeout_s=timeout_s,
            temperature=config.LLM_TEMPERATURE,
            num_ctx=config.LLM_NUM_CTX,
            think=False,
        )
    from aios.application.intelligence.gateway import AdvisoryChatCompletionAdapter
    from tools.reverse_engineer_gagos import resolve_client

    client, _served = resolve_client(spec, timeout_s=timeout_s)
    if not callable(getattr(client, "complete", None)):
        client = AdvisoryChatCompletionAdapter(client)
    return _JsonFromChat(client)


# ------------------------------------------------------------------ running


def run_model(spec: str, jobs: list[dict], *, timeout_s: int) -> dict:
    from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobRequest
    from aios.domain.local_workforce.runtime import StructuredClericalRuntime

    runtime = StructuredClericalRuntime(make_client(spec, timeout_s=timeout_s))
    rows = []
    for job in jobs:
        request = LocalJobRequest(
            job_id=job["id"],
            job_profile=LocalJobProfile(job["profile"]),
            input_schema_version="clerk-benchmark-v1",
            evidence_references=frozenset(job["evidence"]),
            redacted_payload=job["payload"],
            token_budget=1024,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
            required_output_schema=job["schema"],
        )
        result = runtime.execute_job(request)
        correct, failed = grade(
            job, dict(result.structured_output) if result.structured_output else None
        )
        rows.append(
            {
                "job": job["id"],
                "profile": job["profile"],
                "status": result.status,
                "schema_valid": result.schema_valid,
                "correct": correct,
                "failed_checks": failed,
                "seconds": round(result.latency, 2),
                "output": dict(result.structured_output)
                if result.structured_output
                else None,
                "failure_reason": (result.failure_reason or "")[:200] or None,
            }
        )
        print(
            f"  {spec:<40} {'OK ' if correct else 'BAD'} {result.latency:6.1f}s  {job['id']}"
            + ("" if correct else f"  -- {failed[0][:80]}")
        )
    by_profile: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_profile[r["profile"]].append(r["correct"])
    return {
        "correct": sum(r["correct"] for r in rows),
        "jobs": len(rows),
        "schema_valid": sum(r["schema_valid"] for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "by_profile": {p: sum(v) for p, v in sorted(by_profile.items())},
        "statuses": dict(Counter(r["status"] for r in rows)),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True, help="comma-separated: ollama.<tag> or a Bedrock id"
    )
    parser.add_argument("--jobs", type=Path, default=JOBS)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    jobs, jobs_sha = load_jobs(args.jobs)
    specs = [m.strip() for m in args.models.split(",") if m.strip()]
    results = {}
    for spec in specs:
        print(f"\n== {spec}")
        results[spec] = run_model(spec, jobs, timeout_s=args.timeout)
    print()
    profiles = sorted({j["profile"] for j in jobs})
    print(
        f"{'model':<40} {'score':>7} {'valid':>6} {'median':>7}  "
        + " ".join(p[:8] for p in profiles)
    )
    for spec, r in sorted(
        results.items(), key=lambda kv: (-kv[1]["correct"], kv[1]["median_seconds"])
    ):
        print(
            f"{spec:<40} {r['correct']:>3}/{r['jobs']:<3} {r['schema_valid']:>6} {r['median_seconds']:>6.1f}s  "
            + " ".join(f"{r['by_profile'].get(p, 0):>8}" for p in profiles)
        )
    if args.out:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "benchmark": "clerk-benchmark-v1",
            "jobs_sha256_lf": jobs_sha,
            "results": results,
        }
        args.out.write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nrecorded: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
