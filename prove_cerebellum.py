#!/usr/bin/env python3
"""Sovereignty proof: Cerebellum (Phase S1).

Demonstrates that a verified skill arc replays as a deterministic playbook
WITHOUT an LLM call, through the full security gateway.

Run:  python prove_cerebellum.py

Evidence chain:
  1. Cold start — no compiled playbooks.
  2. Insert a verified skill (simulating >=3 STRONG successes, 0 failures).
  3. Compile — the cerebellum converts the verified skill into a playbook.
  4. Match — a new user message matches the compiled playbook.
  5. Replay — the playbook executes through the dispatcher (mocked here to
     avoid real shell execution) and yields cerebellum events.
  6. Decompilation — 2 consecutive failures trigger graceful fallback.

Every assertion is a falsifiable claim.  "Sovereign" is a testable property.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure project root is on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aios.core.cerebellum import Cerebellum, _parse_step, PlaybookStep
from aios.memory.db import init_memory_db, get_connection


def _separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def _evidence(claim: str, result: bool) -> None:
    status = "PASS" if result else "FAIL"
    marker = "✓" if result else "✗"
    print(f"  [{status}] {marker} {claim}")
    if not result:
        raise AssertionError(f"Sovereignty proof failed: {claim}")


_sig_counter = 0


def _insert_verified_skill(
    db_path: Path,
    goal: str,
    steps: list[str],
    *,
    failure_count: int = 0,
    sig_v2: str | None = None,
) -> int:
    """Insert a verified skill directly into the DB."""
    global _sig_counter
    _sig_counter += 1
    sig = f"sig_{_sig_counter}"
    if sig_v2 is None:
        sig_v2 = f"sig_v2_{_sig_counter}"
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO procedural_skills
               (signature, signature_v2, goal_pattern, steps_json,
                status, success_count, failure_count)
               VALUES (?, ?, ?, ?, 'verified', 5, ?)""",
            (sig, sig_v2, goal, json.dumps(steps), failure_count),
        )
        return cur.lastrowid or 0


def _mock_dispatch_ok(name: str, args: dict) -> tuple[str, str, bool]:
    """A mock dispatcher that succeeds for all GREEN-classified tools."""
    if name in ("read_file", "read_directory"):
        return (f"[OK] {name}: contents of {args}", "ok", False)
    if name in ("execute_terminal", "verify"):
        return ("[VERIFY PASS] 3 passed", "ok", False)
    return (f"[BLOCKED] unknown tool {name}", "blocked", False)


def _mock_dispatch_blocked(name: str, args: dict) -> tuple[str, str, bool]:
    """A mock dispatcher that blocks on execute_terminal."""
    if name == "execute_terminal":
        return ("[BLOCKED] destructive command", "blocked", False)
    return (f"[OK] {name}", "ok", False)


def _mock_dispatch_fail(name: str, args: dict) -> tuple[str, str, bool]:
    """A mock dispatcher where execute_terminal fails."""
    if name == "execute_terminal":
        return ("error: command failed", "ok", True)
    return (f"[OK] {name}", "ok", False)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "memory.db"
        init_memory_db(db_path)

        # ── 1. Step parsing ──────────────────────────────────────────
        _separator("1. Step Parsing — tool descriptions → structured calls")

        step = _parse_step("read_file: src/main.py")
        _evidence(
            "read_file step parses correctly",
            step is not None
            and step.tool_name == "read_file"
            and step.args == {"filepath": "src/main.py"},
        )

        step = _parse_step("execute_terminal: python -m pytest tests/")
        _evidence(
            "execute_terminal step parses correctly",
            step is not None
            and step.tool_name == "execute_terminal"
            and step.args == {"command": "python -m pytest tests/"},
        )

        step = _parse_step("verify: python -m pytest tests/test_foo.py")
        _evidence(
            "verify step parses correctly",
            step is not None
            and step.tool_name == "verify"
            and step.args == {"command": "python -m pytest tests/test_foo.py"},
        )

        step = _parse_step("edit_file: foo.py")
        _evidence("edit_file is NOT compilable (returns None)", step is None)

        step = _parse_step("create_file: bar.py")
        _evidence("create_file is NOT compilable (returns None)", step is None)

        # ── 2. Cold start ────────────────────────────────────────────
        _separator("2. Cold Start — no compiled playbooks")

        cb = Cerebellum(db_path)
        _evidence("compiled_count() == 0 on cold start", cb.compiled_count() == 0)

        match = cb.match("read and verify the foo module")
        _evidence("match() returns None when nothing compiled", match is None)

        # ── 3. Skill insertion + compilation ─────────────────────────
        _separator("3. Compilation — verified skill → compiled playbook")

        skill_id = _insert_verified_skill(
            db_path,
            goal="read and verify the foo module",
            steps=[
                "read_file: src/foo.py",
                "execute_terminal: python -m pytest tests/test_foo.py",
                "verify: python -m pytest tests/test_foo.py",
            ],
        )
        _evidence(f"verified skill inserted (id={skill_id})", skill_id > 0)

        compiled = cb.try_compile_all()
        _evidence(f"try_compile_all() compiled {compiled} playbook(s)", compiled == 1)
        _evidence("compiled_count() == 1", cb.compiled_count() == 1)

        pmap = cb.playbook_map()
        _evidence("playbook_map() returns 1 entry", len(pmap) == 1)
        _evidence(
            "playbook has 3 steps",
            pmap[0]["step_count"] == 3,
        )

        # ── 4. Compilation guards ────────────────────────────────────
        _separator("4. Compilation Guards — what does NOT compile")

        # Skill with failures
        failed_id = _insert_verified_skill(
            db_path,
            goal="a skill with failures",
            steps=["read_file: a.py"],
            failure_count=1,
            sig_v2="failed_sig",
        )
        compiled2 = cb.try_compile_all()
        _evidence(
            "skill with failures does NOT compile",
            compiled2 == 0,
        )

        # Skill with edit_file step
        edit_id = _insert_verified_skill(
            db_path,
            goal="a skill with edit steps",
            steps=["read_file: a.py", "edit_file: a.py"],
            sig_v2="edit_sig",
        )
        compiled3 = cb.try_compile_all()
        _evidence(
            "skill with edit_file step does NOT compile",
            compiled3 == 0,
        )

        # ── 5. Matching ─────────────────────────────────────────────
        _separator("5. Matching — user message → compiled playbook")

        match = cb.match("read and verify the foo module")
        _evidence(
            "exact goal text matches",
            match is not None and match.goal_pattern == "read and verify the foo module",
        )

        match = cb.match("verify the foo module please")
        _evidence(
            "partial overlap matches (lexical relevance)",
            match is not None,
        )

        match = cb.match("completely unrelated quantum physics question")
        _evidence(
            "unrelated message does NOT match",
            match is None,
        )

        # ── 6. Replay — successful ───────────────────────────────────
        _separator("6. Replay — successful cerebellum execution (no LLM)")

        match = cb.match("read and verify the foo module")
        assert match is not None

        events = list(cb.replay(match, dispatch_fn=_mock_dispatch_ok))
        event_types = [e["type"] for e in events]
        print(f"  Events emitted: {event_types}")

        _evidence(
            "replay emits cerebellum_step events",
            "cerebellum_step" in event_types,
        )
        _evidence(
            "replay emits cerebellum_step_done events",
            "cerebellum_step_done" in event_types,
        )
        _evidence(
            "replay does NOT emit cerebellum_abort",
            "cerebellum_abort" not in event_types,
        )
        _evidence(
            "3 cerebellum_step events (one per tool call)",
            event_types.count("cerebellum_step") == 3,
        )
        _evidence(
            "3 cerebellum_step_done events (all succeeded)",
            event_types.count("cerebellum_step_done") == 3,
        )

        # Check replay_count incremented
        cb._refresh_cache()
        pb = cb._cache[match.id]
        _evidence(
            f"replay_count == 1 after success (got {pb.replay_count})",
            pb.replay_count == 1,
        )

        # ── 7. Replay — abort on blocked step ────────────────────────
        _separator("7. Replay Abort — blocked step → graceful fallback")

        match2 = cb.match("read and verify the foo module")
        assert match2 is not None

        events2 = list(cb.replay(match2, dispatch_fn=_mock_dispatch_blocked))
        event_types2 = [e["type"] for e in events2]
        print(f"  Events emitted: {event_types2}")

        _evidence(
            "blocked replay emits cerebellum_abort",
            "cerebellum_abort" in event_types2,
        )
        abort_event = next(e for e in events2 if e["type"] == "cerebellum_abort")
        _evidence(
            f"abort reason is 'blocked' (got '{abort_event.get('reason')}')",
            abort_event.get("reason") == "blocked",
        )

        # ── 8. Decompilation — 2 consecutive failures ────────────────
        _separator("8. Decompilation — 2 consecutive failures → fallback")

        # First failure was from step 7. Second failure:
        match3 = cb.match("read and verify the foo module")
        assert match3 is not None
        list(cb.replay(match3, dispatch_fn=_mock_dispatch_blocked))

        cb._refresh_cache()
        _evidence(
            "playbook decompiled after 2 consecutive failures",
            cb.compiled_count() == 0,
        )

        match4 = cb.match("read and verify the foo module")
        _evidence(
            "decompiled playbook does NOT match",
            match4 is None,
        )

        # ── Summary ──────────────────────────────────────────────────
        _separator("SOVEREIGNTY PROOF — PHASE S1 COMPLETE")
        print("  The cerebellum compiles verified skills into playbooks")
        print("  that replay WITHOUT an LLM call, through the full")
        print("  security gateway. Compilation guards prevent unsafe")
        print("  arcs. Decompilation on failure ensures graceful fallback.")
        print()
        print("  Every assertion above is a falsifiable claim.")
        print('  "Sovereign" is a testable property. ✓')
        print()


if __name__ == "__main__":
    main()
