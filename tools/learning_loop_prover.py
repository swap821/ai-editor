"""Learning-loop prover: the Product-Phase-2 demo artifact generator.

Drives the FULL learning chain end-to-end against a live backend and records
machine-checkable evidence for every link:

  failure -> reflection lesson (Mistake DB)          [reflect-* step]
          -> same-run fix + exact-command success    [verify-* confirm step]
          -> next-turn lesson recall                 [lesson-recall step]
  repeat  -> skill promotion at the strength floor   [/development/skills]
          -> compiled playbook                       [cerebellum compile]
  match   -> reflex replay, no LLM consultation      [cerebellum_match/_done]

Plus one MINIMAL VERIFICATION-CONFIDENCE MUTATION PROBE (see the
verification-confidence design spec): a deliberately broken test file MUST
fail verification. If the verify path reports PASS on broken code, the whole
prover run fails loudly — the checks are not checking.

Design constraints baked in (from the cerebellum compilation guards):
  * Only read_file/read_directory/execute_terminal/verify steps compile, so
    the reflex phase uses a verify-only task (no writes).
  * A skill compiles only with a PERFECT lifetime record and >=3 STRONG
    successes, so the reflex phase pre-seeds a deterministically passing
    test file and repeats the identical prompt with fresh sessions.
  * Lesson promotion requires the EXACT failed command string to succeed
    later in the same run, so prompts pin the verify command verbatim.

Usage:
    python tools/learning_loop_prover.py run [--model auto] [--lenient]
                                             [--allow-stale] [--keep-seeds]
    python tools/learning_loop_prover.py report

The run aborts (non-zero exit) if the serving backend is PROVABLY older than the
current HEAD commit (the backend-staleness gotcha); pass --allow-stale to
override. An inconclusive staleness check warns and is recorded in the
artifact. Results append to .aios/audit/learning-loop-runs.jsonl — the
demo artifact the README's Product Phase 2 references.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE, BASE

try:
    import requests
except ImportError:
    sys.exit("requires: pip install requests")

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / ".aios" / "audit"
LOG_PATH = AUDIT_DIR / "learning-loop-runs.jsonl"

TURN_TIMEOUT_S = 900
MAX_REPLAYS = 10
#: SkillMemory promotion floor (min_successes=3); reps must match or exceed it.
REFLEX_REPS = 3
#: Small retry window for the skills endpoint to reflect the final promotion.
PROMOTION_POLL_TRIES = 5
PROMOTION_POLL_DELAY_S = 2.0


# --------------------------------------------------------------------------- #
# Artifact + SSE plumbing (same shapes as golden_mission_runner)
# --------------------------------------------------------------------------- #
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
    """One supervised turn. Returns outcome + every observable the chain emits.

    Beyond golden_mission_runner's outcome classification this also captures
    the learning-chain markers: step ids (reflect-*, verify-*, lesson-recall,
    skill-recall), write-tool usage, and cerebellum_* SSE events.
    """
    tokens: list[str] = []
    approvals_granted: list[str] = []
    evidence: list[str] = []
    step_ids: list[str] = []
    step_tools: list[str] = []
    cerebellum_events: list[str] = []

    for _replay in range(MAX_REPLAYS):
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
                step_ids.append(str(data.get("id", "")))
                step_tools.append(str(data.get("tool", "")))
                output = str(data.get("output", ""))
                if output.startswith(("[VERIFY PASS]", "[VERIFY FAIL]", "[VERIFY SKIPPED]")):
                    evidence.append(output)
            elif event.startswith("cerebellum_"):
                cerebellum_events.append(event)
            elif event == "human_required":
                paused = data
                break
            elif event == "error":
                return {"outcome": "error", "error": data, "evidence": evidence,
                        "step_ids": step_ids, "step_tools": step_tools,
                        "cerebellum_events": cerebellum_events}
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
            return {"outcome": outcome, "approvals": approvals_granted, "evidence": evidence,
                    "step_ids": step_ids, "step_tools": step_tools,
                    "cerebellum_events": cerebellum_events}

        if paused is None:
            return {"outcome": "truncated", "evidence": evidence, "step_ids": step_ids,
                    "step_tools": step_tools, "cerebellum_events": cerebellum_events}

        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            return {"outcome": "rejected", "reason": why, "evidence": evidence,
                    "step_ids": step_ids, "step_tools": step_tools,
                    "cerebellum_events": cerebellum_events}
        approvals_granted.append(why)
        tokens = [token]

    return {"outcome": "max_replays", "evidence": evidence, "step_ids": step_ids,
            "step_tools": step_tools, "cerebellum_events": cerebellum_events}


# --------------------------------------------------------------------------- #
# Pre-flight: reachability + the backend-staleness gotcha
# --------------------------------------------------------------------------- #
def preflight(allow_stale: bool) -> dict[str, Any]:
    """Reachability + serving-process freshness vs the HEAD commit.

    The uvicorn backend has no --reload: after a commit it serves OLD code
    until restarted. Evidence from a stale backend is worthless, so a
    PROVABLY stale process aborts the run. An inconclusive check (no psutil,
    permissions, port owner not found) warns and is recorded in the artifact.
    """
    try:
        health = requests.get(f"{BASE}/health", timeout=10)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - report any reachability failure plainly
        sys.exit(f"[prover] backend unreachable at {BASE}: {exc}")

    result: dict[str, Any] = {"backend": BASE, "staleness": "inconclusive"}
    try:
        commit_epoch = int(subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip())
        result["head_commit_epoch"] = commit_epoch
    except Exception:  # noqa: BLE001 - not a git checkout: nothing to compare against
        print("[prover] WARNING: cannot read HEAD commit time; staleness unverified")
        return result

    port = urlparse(BASE).port or 8000
    proc_start: Optional[float] = None
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN" and conn.pid:
                proc_start = psutil.Process(conn.pid).create_time()
                result["serving_pid"] = conn.pid
                break
    except Exception:  # noqa: BLE001 - psutil missing/permission-denied: stay inconclusive
        proc_start = None

    if proc_start is None:
        print("[prover] WARNING: could not identify the serving process "
              f"on port {port}; staleness unverified (install psutil, or check "
              "manually per the backend-staleness gotcha in RESUME.md)")
        return result

    result["serving_process_start_epoch"] = int(proc_start)
    if proc_start < commit_epoch:
        result["staleness"] = "STALE"
        msg = ("[prover] backend process predates HEAD commit — it is serving OLD code. "
               "Restart the backend, or pass --allow-stale to override.")
        if allow_stale:
            print(msg + " (OVERRIDDEN by --allow-stale)")
        else:
            log_event({"kind": "prover-abort", "reason": "stale_backend", **result})
            sys.exit(msg)
    else:
        result["staleness"] = "fresh"
    return result


# --------------------------------------------------------------------------- #
# Seed files (deterministic sandbox fixtures owned by this harness)
# --------------------------------------------------------------------------- #
def _seed(rel: str, content: str) -> None:
    if not ALLOWED_FILE_RE.match(rel):
        raise ValueError(f"seed path outside sandbox allowlist: {rel}")
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _unlink(rel: str) -> None:
    target = ROOT / rel
    if target.exists():
        target.unlink()


def fixture_paths(run_id: str) -> dict[str, str]:
    """Pure fixture-name scheme (unit-testable against the sandbox allowlist)."""
    return {
        "buggy": f"training_ground/llp_buggy_{run_id}.py",
        "buggy_test": f"training_ground/test_llp_buggy_{run_id}.py",
        "reflex_test": f"training_ground/test_llp_reflex_{run_id}.py",
        "probe_test": f"training_ground/test_llp_probe_{run_id}.py",
    }


def verify_command(rel: str) -> str:
    """The pinned verify command for a fixture (must match ALLOWED_CMD_RE)."""
    return f"pytest {rel} -q"


def seed_files(run_id: str) -> dict[str, str]:
    """Write the deterministic fixtures and return name -> relpath."""
    files = fixture_paths(run_id)
    buggy = files["buggy"]
    buggy_test = files["buggy_test"]
    reflex_test = files["reflex_test"]
    probe_test = files["probe_test"]

    _seed(buggy, (
        "def add(a, b):\n"
        "    # BUG (planted by the learning-loop prover): subtraction, not addition.\n"
        "    return a - b\n"
    ))
    _seed(buggy_test, (
        f"from training_ground.llp_buggy_{run_id} import add\n\n\n"
        "def test_add_positive():\n"
        "    assert add(2, 3) == 5\n\n\n"
        "def test_add_zero():\n"
        "    assert add(0, 7) == 7\n"
    ))
    _seed(reflex_test, (
        "def test_reflex_one():\n"
        "    assert 1 + 1 == 2\n\n\n"
        "def test_reflex_two():\n"
        "    assert sorted([3, 1, 2]) == [1, 2, 3]\n\n\n"
        "def test_reflex_three():\n"
        "    assert 'gagos'.upper() == 'GAGOS'\n"
    ))
    _seed(probe_test, (
        "def test_probe_deliberately_broken():\n"
        "    # MUTATION PROBE (verification-confidence spec): this MUST fail.\n"
        "    # If verification reports PASS here, the checks are not checking.\n"
        "    assert 1 == 2\n"
    ))
    return files


def cleanup_files(files: dict[str, str]) -> None:
    for rel in files.values():
        _unlink(rel)


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #
class Check:
    """Accumulates named pass/fail assertions; lenient mode downgrades soft ones."""

    def __init__(self, lenient: bool) -> None:
        self.lenient = lenient
        self.results: list[dict[str, Any]] = []

    def _record(self, name: str, ok: bool, detail: str, *, soft: bool) -> None:
        downgraded = (not ok) and soft and self.lenient
        self.results.append({"check": name, "ok": ok, "detail": detail,
                             "soft": soft, "downgraded": downgraded})
        marker = "PASS" if ok else ("WARN" if downgraded else "FAIL")
        print(f"    [{marker}] {name}: {detail}")

    def hard(self, name: str, ok: bool, detail: str) -> None:
        self._record(name, ok, detail, soft=False)

    def soft(self, name: str, ok: bool, detail: str) -> None:
        """LLM-obedience-dependent: --lenient turns a failure into a warning."""
        self._record(name, ok, detail, soft=True)

    @property
    def passed(self) -> bool:
        return all(r["ok"] or r["downgraded"] for r in self.results)


def has_id(result: dict[str, Any], prefix: str) -> bool:
    return any(str(i).startswith(prefix) for i in result.get("step_ids", []))


def has_confirm_step(result: dict[str, Any]) -> bool:
    """The lesson-promotion step is tool=="reflect" with a verify-* id.

    The id prefix alone is NOT sufficient: ordinary verify tool calls also
    carry ids of the form ``verify-{index}`` (call_id = f"{name}-{index}"),
    so the reflect tool tag is the disambiguator.
    """
    return any(
        tool == "reflect" and str(sid).startswith("verify-")
        for sid, tool in zip(result.get("step_ids", []), result.get("step_tools", []))
    )


def fail_before_pass(result: dict[str, Any]) -> bool:
    kinds = [e[:13] for e in result.get("evidence", [])
             if e.startswith(("[VERIFY PASS]", "[VERIFY FAIL]"))]
    return "[VERIFY FAIL]" in kinds and kinds[-1] == "[VERIFY PASS]"


def strong_pass(result: dict[str, Any]) -> bool:
    return any(e.startswith("[VERIFY PASS]") and "strength=STRONG" in e
               for e in result.get("evidence", []))


def used_write_tools(result: dict[str, Any]) -> bool:
    return any(t in ("edit_file", "create_file") for t in result.get("step_tools", []))


def skill_promoted(marker: str) -> bool:
    """Poll /development/skills for a verified skill whose row mentions marker."""
    for _ in range(PROMOTION_POLL_TRIES):
        try:
            resp = requests.get(f"{BASE}/api/v1/development/skills",
                                params={"status": "verified"}, timeout=30)
            resp.raise_for_status()
            if marker in json.dumps(resp.json()):
                return True
        except Exception:  # noqa: BLE001 - poll again; the final verdict is the assert
            pass
        time.sleep(PROMOTION_POLL_DELAY_S)
    return False


# --------------------------------------------------------------------------- #
# The three phases
# --------------------------------------------------------------------------- #
def phase_lesson(files: dict[str, str], run_id: str, model: str, check: Check) -> None:
    """failure -> lesson -> same-run exact-command fix -> promotion -> recall."""
    cmd = verify_command(files["buggy_test"])
    session = f"ll-lesson-{run_id}"

    print("  [phase 1/3] lesson loop: failure -> reflect -> fix -> confirm -> recall")
    turn1 = run_prompt(
        f"Use the verify tool to run exactly this command: `{cmd}` — it will FAIL. "
        f"Then read {files['buggy']}, fix the bug in it with a minimal edit so the tests "
        f"pass, and verify again using exactly the same command `{cmd}`. Stop once it "
        "passes. Use that exact command string for both verifications.",
        session, model_id=model,
    )
    log_event({"kind": "turn", "phase": "lesson", "turn": 1, "run_id": run_id, **turn1})
    check.hard("lesson.turn1-verified-success", turn1["outcome"] == "verified_success",
               f"outcome={turn1['outcome']}")
    check.hard("lesson.fail-then-pass", fail_before_pass(turn1),
               "a [VERIFY FAIL] must precede the final [VERIFY PASS]")
    check.hard("lesson.reflect-step", has_id(turn1, "reflect-"),
               "failure hook recorded a structured lesson (reflect-* step)")
    check.soft("lesson.confirm-step", has_confirm_step(turn1),
               "confirm hook promoted the lesson after the exact command succeeded "
               "(reflect-tool step with a verify-* id)")

    turn2 = run_prompt(
        f"Use the verify tool to run exactly this command once: `{cmd}` and report the "
        "result. Do not create or edit any files.",
        session, model_id=model,
    )
    log_event({"kind": "turn", "phase": "lesson", "turn": 2, "run_id": run_id, **turn2})
    check.soft("lesson.recall-step", "lesson-recall" in turn2.get("step_ids", []),
               "the re-attempt turn recalled the recorded lesson (lesson-recall step)")
    check.hard("lesson.turn2-verified-success", turn2["outcome"] == "verified_success",
               f"outcome={turn2['outcome']}")


def phase_reflex(files: dict[str, str], run_id: str, model: str, check: Check) -> None:
    """3x STRONG verify-only successes -> verified skill -> compiled -> replay."""
    cmd = verify_command(files["reflex_test"])
    prompt = (
        f"Use the verify tool to run exactly this command: `{cmd}` and report the "
        "result. Do not create or edit any files."
    )

    print(f"  [phase 2/3] reflex loop: {REFLEX_REPS}x verify-only success -> playbook -> replay")
    for rep in range(1, REFLEX_REPS + 1):
        result = run_prompt(prompt, f"ll-reflex-{run_id}-r{rep}", model_id=model)
        log_event({"kind": "turn", "phase": "reflex", "rep": rep, "run_id": run_id, **result})
        check.hard(f"reflex.rep{rep}-verified-success",
                   result["outcome"] == "verified_success",
                   f"outcome={result['outcome']}")
        check.hard(f"reflex.rep{rep}-strong", strong_pass(result),
                   "promotion floor requires strength=STRONG evidence")
        check.soft(f"reflex.rep{rep}-no-writes", not used_write_tools(result),
                   "write tools would break the cerebellum compile guard")
        if result.get("cerebellum_events"):
            # An earlier compiled playbook intercepted a promotion rep — the
            # fixture name was not unique. Fatal: promotion evidence is void.
            check.hard(f"reflex.rep{rep}-no-early-replay", False,
                       "cerebellum matched BEFORE promotion completed")

    promoted = skill_promoted(f"llp_reflex_{run_id}")
    check.hard("reflex.skill-verified", promoted,
               "a verified skill row for this goal exists in /development/skills")

    replay = run_prompt(prompt, f"ll-reflex-{run_id}-replay", model_id=model)
    log_event({"kind": "turn", "phase": "reflex", "rep": "replay", "run_id": run_id, **replay})
    check.hard("reflex.cerebellum-match", "cerebellum_match" in replay["cerebellum_events"],
               f"events={replay['cerebellum_events'] or 'none'}")
    check.hard("reflex.cerebellum-done", "cerebellum_done" in replay["cerebellum_events"],
               "the compiled playbook replayed to completion")


def phase_probe(files: dict[str, str], run_id: str, model: str, check: Check) -> None:
    """Minimal verification-confidence mutation probe: broken code MUST fail."""
    cmd = verify_command(files["probe_test"])

    print("  [phase 3/3] mutation probe: deliberately broken code must FAIL verification")
    result = run_prompt(
        f"Use the verify tool to run exactly this command once: `{cmd}` and report the "
        "result honestly. Do NOT fix, edit, or create anything — reporting the result "
        "is the entire task.",
        f"ll-probe-{run_id}", model_id=model,
    )
    log_event({"kind": "turn", "phase": "probe", "run_id": run_id, **result})
    saw_fail = any(e.startswith("[VERIFY FAIL]") for e in result.get("evidence", []))
    saw_pass = any(e.startswith("[VERIFY PASS]") for e in result.get("evidence", []))
    check.hard("probe.broken-code-fails", saw_fail and not saw_pass,
               "VERIFICATION-CONFIDENCE VIOLATION: broken code did not fail verification"
               if not saw_fail or saw_pass else "verification correctly failed broken code")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    print(f"[prover] learning-loop prover run {run_id} against {BASE}")

    stale = preflight(args.allow_stale)
    log_event({"kind": "prover-start", "run_id": run_id, "model": args.model,
               "lenient": args.lenient, **stale})

    files = seed_files(run_id)
    check = Check(lenient=args.lenient)
    t0 = time.monotonic()
    try:
        phase_lesson(files, run_id, args.model, check)
        phase_reflex(files, run_id, args.model, check)
        phase_probe(files, run_id, args.model, check)
    finally:
        elapsed = round(time.monotonic() - t0, 1)
        summary = {
            "kind": "prover-summary",
            "run_id": run_id,
            "passed": check.passed,
            "elapsed_s": elapsed,
            "checks": check.results,
            "staleness": stale.get("staleness"),
        }
        log_event(summary)
        if check.passed and not args.keep_seeds:
            cleanup_files(files)
        elif not check.passed:
            print(f"[prover] seeds kept for debugging: {sorted(files.values())}")

    hard_fails = [r["check"] for r in check.results if not r["ok"] and not r["downgraded"]]
    verdict = "PASSED" if check.passed else "FAILED"
    print(f"\n[prover] {verdict} in {elapsed}s "
          f"({sum(1 for r in check.results if r['ok'])}/{len(check.results)} checks green)")
    if hard_fails:
        print(f"[prover] failing checks: {', '.join(hard_fails)}")
    print(f"[prover] artifact: {LOG_PATH}")
    sys.exit(0 if check.passed else 1)


def cmd_report(_: argparse.Namespace) -> None:
    if not LOG_PATH.exists():
        print("[prover] no runs recorded yet")
        return
    summaries: list[dict[str, Any]] = []
    with LOG_PATH.open() as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("kind") == "prover-summary":
                summaries.append(record)
    if not summaries:
        print("[prover] no completed runs")
        return
    print(f"[prover] {len(summaries)} run(s):")
    for s in summaries:
        greens = sum(1 for r in s.get("checks", []) if r.get("ok"))
        total = len(s.get("checks", []))
        print(f"  {s['run_id']}: {'PASS' if s.get('passed') else 'FAIL'} "
              f"({greens}/{total} checks, {s.get('elapsed_s', '?')}s, "
              f"staleness={s.get('staleness', '?')})")
    latest = summaries[-1]
    print(f"\n  latest: {'PASS' if latest.get('passed') else 'FAIL'} @ {latest['run_id']}"
          f" — this is the Product-Phase-2 demo artifact when green.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Learning-loop prover (P2 demo artifact)")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Drive the full learning chain and record evidence")
    run_p.add_argument("--model", type=str, default="auto", help="Model ID to use")
    run_p.add_argument("--lenient", action="store_true",
                       help="Downgrade LLM-obedience-dependent checks to warnings")
    run_p.add_argument("--allow-stale", action="store_true",
                       help="Proceed even if the backend provably serves pre-HEAD code")
    run_p.add_argument("--keep-seeds", action="store_true",
                       help="Keep the training_ground fixtures after a green run")
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="Summarize recorded prover runs")
    report_p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
