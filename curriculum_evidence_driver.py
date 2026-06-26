"""Operator-authorized driver for the live curriculum evidence run.

Drives the REAL supervised chat loop (``POST /api/generate``) through the
small human-reviewed curriculum in ``curriculum_seed.json``. The driver acts
as the operator's explicitly-delegated approver with a hard allowlist:

* it approves ONLY ``create_file``/``edit_file`` actions whose filepath is a
  ``.py`` file directly inside ``training_ground/``, and ONLY ``verify``
  commands of the shape ``python -m pytest "training_ground/<file>.py" -q``;
* anything else is rejected through ``/api/v1/approval/req`` and the run
  aborts (fail-closed);
* every approval, rejection, verifier marker, and curriculum-state diff is
  appended verbatim to ``.aios/audit/curriculum-evidence-run.jsonl`` so the
  evidence report can cite raw records rather than narration.

The driver never writes to the product database directly: all progression
flows through the same HTTP surface the human UI uses.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE, BASE

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "curriculum_seed.json"
AUDIT_DIR = ROOT / ".aios" / "audit"
LOG_PATH = AUDIT_DIR / "curriculum-evidence-run.jsonl"

MAX_REPLAYS = 10
TURN_TIMEOUT_S = 900


def log_event(record: dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def parse_sse(resp: requests.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (event, payload) frames from a text/event-stream response."""
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
    """Validate a human_required payload against the operator allowlist."""
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


def reject_and_abort(token: str | None, session_id: str, reason: str, payload: dict[str, Any]) -> None:
    if token:
        try:
            requests.post(
                f"{BASE}/api/v1/approval/req",
                json={"approvalToken": token, "sessionId": session_id, "approve": False},
                timeout=60,
            )
        except requests.RequestException:
            pass
    log_event({"kind": "approval-rejected", "session": session_id, "reason": reason, "payload": payload})
    sys.exit(f"FAIL-CLOSED: rejected out-of-allowlist action — {reason}")


def run_prompt(
    prompt: str, session_id: str, model_id: str = "auto", *, role_pass: bool = False
) -> dict[str, Any]:
    """Run one supervised turn to completion, replaying through approvals."""
    tokens: list[str] = []
    approvals_granted: list[str] = []
    evidence: list[str] = []
    answer_parts: list[str] = []
    log_event({"kind": "turn-start", "session": session_id, "prompt": prompt,
               "model": model_id, "role_pass": role_pass})
    for replay in range(MAX_REPLAYS):
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "modelId": model_id,
            "sessionId": session_id,
            "approvalTokens": tokens,
            "rolePass": role_pass,
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
                    print(f"    {output[:120]}")
                log_event({"kind": "step", "session": session_id, "replay": replay, "step": data})
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
                # Mirrors the server: the turn's outcome is its FINAL verdict.
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
            log_event({"kind": "turn-done", "session": session_id, "prompt": prompt, **result})
            return result
        if paused is None:
            log_event({"kind": "turn-truncated", "session": session_id, "replay": replay})
            return {"outcome": "truncated", "replays": replay, "evidence": evidence}
        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            reject_and_abort(token, session_id, why, paused)
        approvals_granted.append(why)
        log_event({
            "kind": "approval-granted",
            "session": session_id,
            "replay": replay,
            "action": why,
            "diff": paused.get("input", {}).get("diff", ""),
        })
        print(f"    approved[{replay}]: {why}")
        tokens = [token]
    sys.exit(f"FAIL-CLOSED: exceeded {MAX_REPLAYS} replays without done for session {session_id}")


def get_curriculum() -> list[dict[str, Any]]:
    resp = requests.get(f"{BASE}/api/v1/development/curriculum", timeout=60)
    resp.raise_for_status()
    return resp.json()["tasks"]


def curriculum_brief(tasks: list[dict[str, Any]]) -> list[str]:
    return [
        f"{t['skill_name']} L{t['level']} {'H' if t['held_out'] else 'T'} "
        f"#{t['id']} {t['status']} a={t['attempts']} s={t['successes']}"
        for t in tasks
    ]


def find_row(tasks: list[dict[str, Any]], prompt: str) -> dict[str, Any] | None:
    return next((t for t in tasks if t["prompt"] == prompt), None)


def cmd_seed(_: argparse.Namespace) -> None:
    seed = load_seed()
    for task in seed["tasks"]:
        resp = requests.post(
            f"{BASE}/api/v1/development/curriculum",
            json={
                "skillName": seed["skill"],
                "level": task["level"],
                "prompt": task["prompt"],
                "heldOut": task["held_out"],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"{task['key']}: id={data['id']} executed={data['executed']}")
        log_event({"kind": "seeded", "task": task["key"], "id": data["id"], "prompt": task["prompt"]})
    print("\nCurriculum state:")
    for line in curriculum_brief(get_curriculum()):
        print(f"  {line}")


def cmd_status(_: argparse.Namespace) -> None:
    tasks = get_curriculum()
    for line in curriculum_brief(tasks):
        print(f"  {line}")
    skills = requests.get(f"{BASE}/api/v1/development/skills", timeout=60).json()
    print(f"\nskills: {json.dumps(skills, indent=2)[:2000]}")
    metrics = requests.get(f"{BASE}/api/v1/development/metrics", timeout=60).json()
    print(f"\nmetrics: {json.dumps(metrics, indent=2)}")


def reset_task_files(task: dict[str, Any], rep: int) -> None:
    """Test-fixture semantics: every attempt starts from a clean sandbox slate.

    Lesson transfer between attempts must come from the product's own memory
    (mistake recall / semantic recall), not from half-finished files on disk —
    and a broken on-disk test would poison every later attempt through the
    FAIL-dominant turn classification.
    """
    for rel in task["files"]:
        if not ALLOWED_FILE_RE.match(rel):
            sys.exit(f"FAIL-CLOSED: refusing to reset non-allowlisted path {rel!r}")
        target = (ROOT / rel).resolve()
        if target.exists():
            target.unlink()
            print(f"    reset: deleted {rel}")
            log_event({"kind": "sandbox-reset", "deleted": rel, "task": task["key"], "rep": rep})


def run_one_task(task: dict[str, Any], rep: int = 0, model_id: str = "auto") -> dict[str, Any]:
    reset_task_files(task, rep)
    before = find_row(get_curriculum(), task["prompt"])
    attempt = (before or {}).get("attempts", 0)
    session_id = f"curriculum-{task['key']}-a{attempt}-r{rep}"
    print(f"\n=== {task['key']} (rep {rep}) session={session_id} model={model_id}")
    print(f"    {task['prompt'][:110]}...")
    result = run_prompt(task["prompt"], session_id, model_id=model_id)
    after = find_row(get_curriculum(), task["prompt"])
    progressed = bool(before and after and after["attempts"] > before["attempts"])
    print(f"    outcome={result['outcome']} curriculum_attempt_recorded={progressed}")
    if after:
        print(f"    row now: status={after['status']} attempts={after['attempts']} successes={after['successes']}")
    if result["outcome"] == "verified_success" and not progressed:
        print("    !! WARNING: verified success but NO curriculum increment — "
              "silent record_matching mismatch (check prompt verbatim equality)")
    log_event({
        "kind": "task-progress-check",
        "task": task["key"],
        "rep": rep,
        "outcome": result["outcome"],
        "curriculum_attempt_recorded": progressed,
        "row_before": before,
        "row_after": after,
    })
    result["progressed"] = progressed
    return result


def cmd_run(args: argparse.Namespace) -> None:
    seed = load_seed()
    wanted = [t for t in seed["tasks"] if args.task in ("all", t["key"])]
    if not wanted:
        sys.exit(f"unknown task key {args.task!r}")
    for task in wanted:
        row = find_row(get_curriculum(), task["prompt"])
        if row is None:
            sys.exit(f"{task['key']} is not seeded yet — run `seed` first")
        if row["status"] != "available":
            print(f"\n=== {task['key']} skipped (status={row['status']})")
            continue
        run_one_task(task, model_id=args.model)


def cmd_reps(args: argparse.Namespace) -> None:
    """Extra repetitions of one task to accumulate skill-promotion evidence."""
    seed = load_seed()
    plan = seed["skill_promotion_reps"]
    task = next(t for t in seed["tasks"] if t["key"] == plan["task"])
    for rep in range(1, int(plan["extra_runs"]) + 1):
        run_one_task(task, rep=rep, model_id=args.model)
    cmd_status(args)


def cmd_trails(_: argparse.Namespace) -> None:
    """Print the pheromone map: computed trail strengths, decay, reuse, lineage."""
    resp = requests.get(f"{BASE}/api/v1/development/trails", timeout=60)
    resp.raise_for_status()
    data = resp.json()
    print(f"summary: {json.dumps(data['summary'])}")
    print(f"constants: {json.dumps(data['constants'])}")
    for t in data["trails"]:
        mark = "Q" if t["quarantined"] else ("V" if t["status"] == "verified" else "c")
        print(
            f"  [{mark}] #{t['skill_id']} strength={t['strength']:.4f} "
            f"(rate={t['success_rate']:.2f} fresh={t['freshness']:.4f} "
            f"reuse={t['reuse_factor']:.4f} [{t['reuse_success_count']}+/"
            f"{t['reuse_failure_count']}-]) :: {t['goal_pattern'][:70]}"
        )
    for f in data["superseded_fragments"]:
        print(f"  [s] #{f['skill_id']} -> #{f['superseded_by']} ({f['success_count']}/{f['failure_count']})")


def cmd_plan_proof(_: argparse.Namespace) -> None:
    """Live-prove the Slice 1 foraging reward via POST /api/v1/plan."""
    seed = load_seed()
    goal = seed["plan_proof_goal"]
    resp = requests.post(f"{BASE}/api/v1/plan", json={"goal": goal}, timeout=600)
    resp.raise_for_status()
    plan = resp.json()
    print(json.dumps(plan, indent=2)[:4000])
    rewarded = [
        c for c in plan.get("calibrations", [])
        if float(c.get("skill_adjustment", 0) or 0) > 0
    ]
    print(f"\ncalibrations with skill_adjustment > 0: {len(rewarded)}")
    for c in rewarded:
        print(f"  step={c.get('step_description', '')!r} adj={c['skill_adjustment']} skills={c.get('skill_ids')}")
    log_event({"kind": "plan-proof", "goal": goal, "plan": plan, "rewarded_steps": len(rewarded)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="define the curriculum tasks (idempotent, never executes)")
    sub.add_parser("status", help="print curriculum rows, skills, and development metrics")
    p_run = sub.add_parser("run", help="run available curriculum task(s) through the live loop")
    p_run.add_argument("--task", default="all", help="task key (e.g. L1-T1) or 'all'")
    p_run.add_argument("--model", default="auto", help="modelId for the turn (e.g. ollama.llama3.1:8b)")
    p_reps = sub.add_parser("reps", help="extra runs of the promotion task (resets its sandbox files)")
    p_reps.add_argument("--model", default="auto", help="modelId for the turn (e.g. ollama.llama3.1:8b)")
    sub.add_parser("plan-proof", help="show the planner's live skill_adjustment for the proof goal")
    sub.add_parser("trails", help="print the pheromone map (computed strengths, decay, reuse, lineage)")
    args = parser.parse_args()
    {"seed": cmd_seed, "status": cmd_status, "run": cmd_run,
     "reps": cmd_reps, "plan-proof": cmd_plan_proof, "trails": cmd_trails}[args.cmd](args)


if __name__ == "__main__":
    main()
