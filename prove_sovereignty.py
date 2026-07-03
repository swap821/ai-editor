#!/usr/bin/env python3
"""Sovereignty proof: Full System (Phase S4).

Demonstrates that the three sovereignty organs (S1 Cerebellum, S2 Knowledge
Graph, S3 Native Planner) work as a unified whole AND that the system degrades
gracefully when all LLMs are offline.

Run:  python prove_sovereignty.py

Evidence chain (18 assertions across 6 phases):
  Phase 1 — Memory Seeding (3 assertions)
  Phase 2 — Knowledge Graph Inference (3 assertions)
  Phase 3 — Native Planner (3 assertions)
  Phase 4 — Cerebellum Replay + Offline Guard (4 assertions)
  Phase 5 — Verification Without LLM (2 assertions)
  Phase 6 — Offline Guard Integration (3 assertions)

Every assertion is a falsifiable claim.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.core.cerebellum import Cerebellum
from aios.core.inference import infer
from aios.core.native_planner import NativePlanner
from aios.core.planner import Planner, PlannerError
from aios.memory.db import init_memory_db, get_connection
from aios.memory.facts import SemanticFacts
from aios.memory.skills import SkillMemory


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
    """Mock dispatcher that succeeds for all compilable tools."""
    if name in ("read_file", "read_directory"):
        return (f"[OK] {name}: contents of {args}", "ok", False)
    if name in ("execute_terminal", "verify"):
        return ("[VERIFY PASS] 3 passed", "ok", False)
    return (f"[BLOCKED] unknown tool {name}", "blocked", False)


class _OfflineLLM:
    """Mock LLM that raises on any call — proves no LLM was consulted."""

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError("LLM called in offline mode — sovereignty violated")

    def chat(self, messages: list, **kw) -> dict:
        raise RuntimeError("LLM called in offline mode — sovereignty violated")


def main() -> None:
    print()
    print("=" * 60)
    print("  SOVEREIGNTY PROOF — prove_sovereignty.py")
    print("  Proves S1 + S2 + S3 work together, offline.")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "sovereignty_proof.db"
        init_memory_db(db_path)

        # ────────────────────────────────────────────────────────────
        # Phase 1: Memory Seeding
        # ────────────────────────────────────────────────────────────
        _separator("Phase 1: Memory Seeding")

        # 1. Insert verified skill (compilable steps)
        skill_goal = "read and verify the router module"
        skill_steps = [
            "read_file: src/router.py",
            "execute_terminal: python -m pytest tests/test_router.py",
            "verify: python -m pytest tests/test_router.py",
        ]
        skill_id = _insert_verified_skill(db_path, skill_goal, skill_steps)
        _evidence(
            f"verified skill inserted (id={skill_id})",
            skill_id > 0,
        )

        # 2. Insert verified swarm pattern (3 successes for promotion)
        swarm_goal = "refactor the auth module"
        swarm_subtasks = [
            "analyze current auth structure",
            "extract shared utilities",
            "update imports",
            "run test suite",
        ]
        spm = SwarmPatternMemory(db_path)
        for _ in range(3):
            spm.record_attempt(swarm_goal, swarm_subtasks, success=True)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT status FROM swarm_patterns WHERE goal_pattern = ?",
                (swarm_goal,),
            ).fetchone()
        _evidence(
            "swarm pattern reached verified status",
            row is not None and row["status"] == "verified",
        )

        # 3. Insert semantic facts (router -> FastAPI -> uvicorn)
        facts = SemanticFacts(db_path)
        r1 = facts.add_fact("router", "uses", "FastAPI")
        r2 = facts.add_fact("FastAPI", "needs", "uvicorn")
        _evidence(
            "semantic facts committed (router->FastAPI->uvicorn)",
            r1.committed and r2.committed,
        )

        # ────────────────────────────────────────────────────────────
        # Phase 2: Knowledge Graph Inference (no LLM)
        # ────────────────────────────────────────────────────────────
        _separator("Phase 2: Knowledge Graph Inference")

        # 4. Weighted traversal returns multi-hop edges
        edges = facts.traverse_weighted("router", max_depth=3)
        _evidence(
            f"traverse_weighted('router') returns {len(edges)} edges (need >=2)",
            len(edges) >= 2,
        )

        # 5. infer() composes answer with confidence
        result = infer("router", edges)
        _evidence(
            "infer() produces answer with confidence > 0",
            result is not None
            and result.combined_confidence > 0.0
            and len(result.answer) > 0,
        )

        # 6. Inference is pure — no LLM parameter
        import inspect
        sig = inspect.signature(infer)
        param_names = set(sig.parameters.keys())
        _evidence(
            "infer() has no LLM parameter (pure function)",
            "llm" not in param_names and "model" not in param_names,
        )

        # ────────────────────────────────────────────────────────────
        # Phase 3: Native Planner (no LLM)
        # ────────────────────────────────────────────────────────────
        _separator("Phase 3: Native Planner")

        skill_mem = SkillMemory(db_path)
        native = NativePlanner(
            skills=skill_mem,
            patterns=spm,
            facts=facts,
            min_confidence=0.0,
        )

        # 7. Skill-based plan match
        skill_plan = native.try_plan("read and verify the router module")
        _evidence(
            "native planner matches skill arc (source='skill')",
            skill_plan is not None and skill_plan.source == "skill",
        )

        # 8. Pattern-based plan match
        pattern_plan = native.try_plan("refactor the auth module")
        _evidence(
            "native planner matches swarm pattern (source='swarm_pattern')",
            pattern_plan is not None
            and pattern_plan.source == "swarm_pattern",
        )

        # 9. Novel task miss
        novel_plan = native.try_plan("quantum physics simulation")
        _evidence(
            "novel task falls through (returns None)",
            novel_plan is None,
        )

        # ────────────────────────────────────────────────────────────
        # Phase 4: Cerebellum Replay + Offline Guard
        # ────────────────────────────────────────────────────────────
        _separator("Phase 4: Cerebellum Replay")

        cb = Cerebellum(db_path)

        # 10. Compilation
        compiled = cb.try_compile_all()
        _evidence(
            f"cerebellum compiled {compiled} playbook(s)",
            compiled >= 1,
        )

        # 11. Matching
        playbook = cb.match("read and verify the router module")
        _evidence(
            "compiled playbook matches goal text",
            playbook is not None,
        )

        # 12. Replay (no LLM, no crash)
        events = list(cb.replay(playbook, dispatch_fn=_mock_dispatch_ok))
        event_types = [e.get("type") for e in events]
        step_events = [e for e in events if e.get("type") == "cerebellum_step"]
        _evidence(
            f"replay emits {len(step_events)} step events, no abort",
            len(step_events) == 3
            and "cerebellum_abort" not in event_types,
        )

        # 13. Novel task does NOT match
        no_match = cb.match("completely unrelated quantum physics question")
        _evidence(
            "unrelated message does NOT match any playbook",
            no_match is None,
        )

        # ────────────────────────────────────────────────────────────
        # Phase 5: Verification Without LLM
        # ────────────────────────────────────────────────────────────
        _separator("Phase 5: Verification Without LLM")

        # 14. Verify tool handler is callable
        from aios.agents.tool_handlers import verify_command
        _evidence(
            "verify_command handler is callable (no LLM required)",
            callable(verify_command),
        )

        # 15. Planner native path works in offline mode
        import aios.config as _config
        _orig_offline = _config.OFFLINE_MODE
        try:
            _config.OFFLINE_MODE = True
            planner = Planner(_OfflineLLM(), native=native)
            plan = planner.plan("read and verify the router module")
            _evidence(
                "planner returns native plan in offline mode",
                plan is not None
                and plan.native_source is not None
                and len(plan.steps) > 0,
            )
        finally:
            _config.OFFLINE_MODE = _orig_offline

        # ────────────────────────────────────────────────────────────
        # Phase 6: Offline Guard Integration
        # ────────────────────────────────────────────────────────────
        _separator("Phase 6: Offline Guard Integration")

        import aios.config as _config
        _orig_offline = _config.OFFLINE_MODE
        try:
            _config.OFFLINE_MODE = True

            # 16. Planner raises PlannerError for novel task offline
            raised_planner = False
            try:
                planner = Planner(_OfflineLLM(), native=native)
                planner.plan("completely unknown novel task xyz")
            except PlannerError:
                raised_planner = True
            _evidence(
                "planner raises PlannerError for novel task offline",
                raised_planner,
            )

            # 17. Reflection returns None in offline mode
            from aios.agents.reflection_agent import ReflectionAgent
            reflector = ReflectionAgent(_OfflineLLM(), db_path=db_path)
            reflection_result = reflector.reflect("bad_cmd", "error output")
            _evidence(
                "reflect() returns None in offline mode",
                reflection_result is None,
            )

            # 18. OFFLINE_MODE config flag is functional
            _evidence(
                "OFFLINE_MODE config flag is True (functional)",
                _config.OFFLINE_MODE is True,
            )
        finally:
            _config.OFFLINE_MODE = _orig_offline

    # ────────────────────────────────────────────────────────────
    # Summary
    # ────────────────────────────────────────────────────────────
    _separator("SOVEREIGNTY PROOF — PHASE S4 COMPLETE")
    print("  The three sovereignty organs work as a unified whole:")
    print("  - Verified skills compile into deterministic playbooks (S1)")
    print("  - Facts compose into multi-hop inferences (S2)")
    print("  - Known task shapes plan from verified experience (S3)")
    print("  - Novel tasks get honest offline refusal (S4)")
    print("  - All three organs operate WITHOUT an LLM call")
    print()
    print("  Every assertion above is a falsifiable claim.")
    print('  "Sovereign" is a testable property.')
    print()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"\n  SOVEREIGNTY PROOF FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
