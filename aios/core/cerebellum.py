"""Compiled Experience Engine — the organism's muscle memory.

A verified skill arc (>=3 STRONG successes, >=80% rate) that additionally
passes the compilation guards is compiled into a deterministic playbook:
a literal list of (tool_name, args) steps that can be replayed without an
LLM call, through the SAME security gateway, with the SAME audit trail.

The cerebellum is injected into ToolAgent via DI.  In run(), before the
LLM chat loop, it attempts to match the user message against compiled
playbooks.  A match short-circuits the entire LLM turn — the organism
acts from compiled experience, not external consultation.

Compilation guards (beyond SkillMemory's promotion criteria):
  1. All steps must parse into compilable tool calls (read/execute/verify).
  2. All tool names must exist in the ToolAgent dispatch table.
  3. Zero failures in the skill's lifetime (not just 80% — perfect).
  4. Goal pattern must be non-empty after secret redaction.

Decompilation: 2 consecutive replay failures marks the playbook as
'decompiled'.  It cannot recompile without the underlying skill
re-earning verification from scratch (the skill must be re-promoted).

Security: Every replayed step flows through ToolAgent._dispatch(), which
calls the gateway classify(), scope_lock, audit_logger, and verifier.
The cerebellum is a tool-call SOURCE, not a gateway bypass.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance
from aios.security.secret_scanner import scan_and_redact

_COMPILABLE_TOOLS = frozenset(
    {
        "read_file",
        "read_directory",
        "execute_terminal",
        "verify",
    }
)

DispatchFn = Callable[[str, dict[str, Any]], tuple[str, str, bool]]


@dataclass(frozen=True)
class PlaybookStep:
    """One step in a compiled playbook — a structured tool call."""

    tool_name: str
    args: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "args": self.args}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaybookStep":
        return cls(
            tool_name=str(data["tool_name"]),
            args=dict(data.get("args") or {}),
        )


@dataclass
class CompiledPlaybook:
    """A compiled skill — a deterministic sequence of tool calls."""

    id: int
    skill_id: int
    goal_pattern: str
    signature_v2: str
    steps: list[PlaybookStep]
    compiled_at: str
    replay_count: int = 0
    consecutive_failures: int = 0
    status: str = "compiled"


def _parse_step(step_desc: str) -> Optional[PlaybookStep]:
    """Parse a skill step description into a structured PlaybookStep.

    Step format from SkillMemory: ``"tool_name: argument"``.
    Returns ``None`` if the step uses a tool that cannot be compiled
    (edit_file/create_file require content not stored in step summaries).
    """
    if ":" not in step_desc:
        return None
    tool_name, _, arg = step_desc.partition(":")
    tool_name = tool_name.strip().lower()
    arg = arg.strip()

    if tool_name not in _COMPILABLE_TOOLS:
        return None
    if not arg:
        return None

    if tool_name == "read_file":
        return PlaybookStep(
            tool_name="read_file", args={"filepath": _arg_value(arg, "filepath")}
        )
    if tool_name == "read_directory":
        return PlaybookStep(
            tool_name="read_directory", args={"path": _arg_value(arg, "path")}
        )
    if tool_name == "execute_terminal":
        return PlaybookStep(
            tool_name="execute_terminal", args={"command": _arg_value(arg, "command")}
        )
    if tool_name == "verify":
        return PlaybookStep(
            tool_name="verify", args={"command": _arg_value(arg, "command")}
        )
    return None


def _arg_value(arg: str, key: str) -> str:
    """Extract the bare value from a ``_workflow_step``-style ``key=value`` detail.

    ``_workflow_step`` (aios/api/main.py) serializes each tool call for skill
    recording as ``tool: key=value`` (e.g. ``verify: command=pytest x.py -q``).
    A compiled playbook must replay the BARE value; if the ``key=`` prefix is
    left on, the gateway classifies ``command=pytest ...`` as an unknown command
    (Zone.RED, "not on the auto-execute allowlist") and every replay aborts.
    Split on the first ``=`` so values that themselves contain ``=`` survive;
    tolerate the legacy bare-value form.
    """
    prefix = f"{key}="
    return arg[len(prefix) :].strip() if arg.startswith(prefix) else arg


#: A word-ish run that may name a file — path separators, dots and hyphens
#: included. Candidates are classified by :func:`_target_files`.
_TARGET_TOKEN = re.compile(r"[A-Za-z0-9_.\-][A-Za-z0-9_.\-/\\]*")

#: Well-known extensionless filenames — real concrete targets that carry no dot
#: or separator. Deliberately excludes word-like names (``notice``, ``authors``)
#: whose bare-word use would over-trigger the guard.
_BARE_FILENAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "rakefile",
        "gemfile",
        "procfile",
        "jenkinsfile",
        "vagrantfile",
        "readme",
        "license",
        "changelog",
    }
)


def _target_files(text: str) -> set[str]:
    """Extract concrete file references from *text*, normalised for comparison.

    This is a DOMAIN HEURISTIC for the cerebellum's actual playbooks (ASCII,
    forward-slash, relative ``pytest``/``read`` paths — the shape skills record),
    NOT a general free-text path parser. It is verified end-to-end by the
    learning-loop prover (the mutation probe stays red-on-broken while the reflex
    replay fires).

    **Biased toward soundness on purpose.** The two failure modes are NOT
    symmetric: under-extracting a real target lets a stale playbook replay and
    FABRICATE a verdict (the failure this guard exists to stop), whereas
    over-extracting merely makes the cerebellum fall through to the LLM, which
    still answers correctly (a missed shortcut, never a wrong verdict). So a
    token counts as a file when it bears a path separator, OR a dotted extension
    (``.env`` and ``backup.7z`` included; bare decimals like ``0.85`` excluded),
    OR is a well-known extensionless filename. Tokens are normalised — lowercased,
    ``\\``→``/``, a leading ``./`` stripped — so a Windows-native or dot-relative
    spelling of the SAME file still matches its playbook.

    Documented residuals (adversarially found; all bounded by the goal-relevance
    threshold that gates matching, and by downstream defense-in-depth — RED
    classification, approval, the verifier re-running):
      * Over-rejects (SAFE, fall through to LLM): a technology name like
        ``Node.js``; an absolute path vs the playbook's relative path.
      * Under-extracts (residual soundness gap, out of the ASCII/relative domain):
        a filename whose disambiguating prefix is split off by a space or a
        non-ASCII character (``budget report.xlsx``, ``报告.py``, ``café.py``) can
        collapse to a shared trailing segment. Free-text filename parsing cannot
        resolve this unambiguously; the realistic cerebellum domain does not
        produce such playbooks.
    """
    targets: set[str] = set()
    for raw in _TARGET_TOKEN.findall(text):
        low = raw.lower().rstrip(".,;:!?)").replace("\\", "/")
        while low.startswith("./"):
            low = low[2:]
        if not low or low == ".":
            continue
        if "/" in low:
            targets.add(low)
        elif "." in low and not all(c in "0123456789." for c in low):
            targets.add(low)
        elif low in _BARE_FILENAMES:
            targets.add(low)
    return targets


def _conflicting_targets(user_message: str, steps: list["PlaybookStep"]) -> bool:
    """True when the request names concrete target(s) the playbook does NOT touch.

    A compiled playbook replays a FIXED command sequence, but its ``goal_pattern``
    can be a generic prefix (e.g. "run exactly this command:") that lexically
    matches requests asking for a DIFFERENT concrete file. Replaying the stale
    command for such a request would FABRICATE a verdict — a passing reflex
    playbook would "verify" a broken probe (verification-confidence violation).

    So: if the request names concrete file target(s) AND the playbook's commands
    name concrete target(s) AND the two sets are DISJOINT, the request is about a
    different file — refuse the match. When the request names no concrete target
    (a paraphrase like "run the tests"), there is no conflict and lexical
    goal-matching stands unchanged (preserving paraphrase-tolerant recall).
    """
    request_targets = _target_files(user_message)
    if not request_targets:
        return False
    playbook_targets: set[str] = set()
    for step in steps:
        for value in step.args.values():
            playbook_targets |= _target_files(str(value))
    if not playbook_targets:
        return False
    return request_targets.isdisjoint(playbook_targets)


#: A clean, unambiguous target: ASCII path characters only, no whitespace.
_CLEAN_PATH = re.compile(r"^[A-Za-z0-9_.\-/\\]+$")


def _is_clean_target(value: str) -> bool:
    """True when *value* is a clean RELATIVE ASCII path — no spaces, quotes,
    non-ASCII, or absolute root. Anything else tokenises ambiguously in
    :func:`_target_files` (see its residual note) and must not become a
    replayable playbook target."""
    if not value or not value.isascii() or not _CLEAN_PATH.fullmatch(value):
        return False
    norm = value.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", value):  # absolute path
        return False
    return True


def _step_targets_are_clean(step: "PlaybookStep") -> bool:
    """Compile guard (belt-and-suspenders): every file a step names must be a
    clean relative ASCII path.

    This closes the replay-time conflict guard's residual at the SOURCE: a skill
    that operates on a spaced / non-ASCII / quoted / absolute-path filename is
    never compiled into a playbook, so such a target can never replay a stale
    verdict for a different file. Refusing to compile is safe — that skill simply
    keeps running through the LLM instead of the reflex fast-path.
    """
    if step.tool_name in ("read_file", "read_directory"):
        value = str(step.args.get("filepath") or step.args.get("path") or "")
        return _is_clean_target(value)
    if step.tool_name in ("execute_terminal", "verify"):
        command = str(step.args.get("command", ""))
        if not command.isascii() or '"' in command or "'" in command:
            return False
        for tok in command.split():
            low = tok.replace("\\", "/")
            pathish = "/" in low or (
                "." in low and not all(c in "0123456789." for c in low)
            )
            if pathish and not _is_clean_target(tok):
                return False
        return True
    return True


class Cerebellum:
    """Compiled Experience Engine.

    Watches SkillMemory for verified skills, compiles them into
    deterministic playbooks, and replays them without LLM consultation.
    """

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        match_threshold: float = 0.5,
        max_consecutive_failures: int = 2,
    ) -> None:
        self.db_path = db_path
        self.match_threshold = match_threshold
        self.max_consecutive_failures = max_consecutive_failures
        self._cache: dict[int, CompiledPlaybook] = {}

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------

    def try_compile_all(self) -> int:
        """Scan verified skills and compile any that pass guards.

        Returns the number of newly compiled playbooks.
        """
        init_memory_db(self.db_path)
        compiled = 0
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                """SELECT ps.id, ps.goal_pattern, ps.steps_json,
                          ps.success_count, ps.failure_count,
                          ps.signature_v2
                   FROM procedural_skills ps
                   WHERE ps.status = 'verified'
                     AND ps.failure_count = 0
                     AND NOT EXISTS (
                         SELECT 1 FROM compiled_playbooks cp
                         WHERE cp.skill_id = ps.id
                           AND cp.status IN ('compiled', 'decompiled')
                     )"""
            ).fetchall()
            for row in rows:
                pb = self._try_compile_one(row, conn)
                if pb is not None:
                    self._cache[pb.id] = pb
                    compiled += 1
        return compiled

    def try_compile_skill(self, skill_id: int) -> Optional[CompiledPlaybook]:
        """Attempt to compile a single skill by id.  Returns the playbook
        if compilation succeeds, else ``None``."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                """SELECT id, goal_pattern, steps_json,
                          success_count, failure_count, signature_v2
                   FROM procedural_skills
                   WHERE id = ? AND status = 'verified'""",
                (skill_id,),
            ).fetchone()
            if row is None:
                return None
            already = conn.execute(
                """SELECT 1 FROM compiled_playbooks
                   WHERE skill_id = ? AND status IN ('compiled', 'decompiled')""",
                (skill_id,),
            ).fetchone()
            if already is not None:
                return None
            pb = self._try_compile_one(row, conn)
            if pb is not None:
                self._cache[pb.id] = pb
            return pb

    def _try_compile_one(
        self,
        skill_row: Any,
        conn: Any,
    ) -> Optional[CompiledPlaybook]:
        """Attempt to compile one verified skill row.  Returns None if
        any compilation guard fails."""
        skill_id = int(skill_row["id"])
        goal = str(skill_row["goal_pattern"])
        steps_json = str(skill_row["steps_json"])
        failure_count = int(skill_row["failure_count"])
        sig_v2 = str(skill_row["signature_v2"] or "")

        if failure_count > 0:
            return None

        clean_goal = scan_and_redact(goal).scrubbed.strip()
        if not clean_goal:
            return None

        try:
            step_descs: list[str] = json.loads(steps_json)
        except (json.JSONDecodeError, TypeError):
            return None
        if not step_descs or not isinstance(step_descs, list):
            return None

        parsed: list[PlaybookStep] = []
        for desc in step_descs:
            step = _parse_step(str(desc))
            if step is None:
                return None
            parsed.append(step)

        # Compile guard (soundness belt-and-suspenders): only compile a playbook
        # whose every file target is a clean relative ASCII path, so the
        # replay-time conflict guard's free-text residual (a spaced / non-ASCII
        # filename that tokenises ambiguously) can never produce a playbook that
        # replays a stale verdict for a different file.
        if not all(_step_targets_are_clean(step) for step in parsed):
            return None

        steps_data = json.dumps([s.to_dict() for s in parsed], separators=(",", ":"))
        cur = conn.execute(
            """INSERT INTO compiled_playbooks
               (skill_id, goal_pattern, signature_v2, steps_json, status)
               VALUES (?, ?, ?, ?, 'compiled')""",
            (skill_id, clean_goal, sig_v2, steps_data),
        )
        playbook_id = cur.lastrowid
        return CompiledPlaybook(
            id=playbook_id,
            skill_id=skill_id,
            goal_pattern=clean_goal,
            signature_v2=sig_v2,
            steps=parsed,
            compiled_at="",
            replay_count=0,
            consecutive_failures=0,
            status="compiled",
        )

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(self, user_message: str) -> Optional[CompiledPlaybook]:
        """Match user message against compiled playbooks.

        Uses deterministic lexical relevance (same algorithm as skill
        recall).  Returns the best match above *match_threshold*, or
        ``None``.
        """
        self._refresh_cache()
        if not self._cache:
            return None

        best: Optional[CompiledPlaybook] = None
        best_score = 0.0

        for pb in self._cache.values():
            if pb.status != "compiled":
                continue
            score = relevance(user_message, pb.goal_pattern)
            if (
                score >= self.match_threshold
                and score > best_score
                and not _conflicting_targets(user_message, pb.steps)
            ):
                best = pb
                best_score = score

        return best

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay(
        self,
        playbook: CompiledPlaybook,
        *,
        dispatch_fn: DispatchFn,
    ) -> Iterator[dict[str, Any]]:
        """Replay a compiled playbook step by step.

        Yields typed event dicts that the SSE stream forwards to the UI.
        Each step is dispatched through the SAME security gateway as
        LLM-proposed actions.

        If any step is blocked, requires approval, or fails execution,
        the replay aborts with a ``cerebellum_abort`` event.  The caller
        should fall through to the LLM loop.

        On full success the caller should emit ``cerebellum_done``.
        """
        for i, step in enumerate(playbook.steps):
            yield {
                "type": "cerebellum_step",
                "tool": step.tool_name,
                "step_index": i,
                "step_count": len(playbook.steps),
                "args": step.args,
            }

            output, status, failed = dispatch_fn(step.tool_name, step.args)

            if status in ("blocked", "approval"):
                self._record_replay_failure(playbook.id)
                yield {
                    "type": "cerebellum_abort",
                    "step_index": i,
                    "reason": status,
                    "tool": step.tool_name,
                }
                return

            if failed:
                self._record_replay_failure(playbook.id)
                yield {
                    "type": "cerebellum_abort",
                    "step_index": i,
                    "reason": "execution_failed",
                    "tool": step.tool_name,
                    "output": (output or "")[:200],
                }
                return

            yield {
                "type": "cerebellum_step_done",
                "tool": step.tool_name,
                "step_index": i,
                "output": (output or "")[:200],
            }

        self._record_replay_success(playbook.id)

    # ------------------------------------------------------------------
    # Replay bookkeeping
    # ------------------------------------------------------------------

    def _record_replay_success(self, playbook_id: int) -> None:
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """UPDATE compiled_playbooks
                   SET replay_count = replay_count + 1,
                       consecutive_failures = 0,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (playbook_id,),
            )
        pb = self._cache.get(playbook_id)
        if pb is not None:
            pb.replay_count += 1
            pb.consecutive_failures = 0

    def _record_replay_failure(self, playbook_id: int) -> None:
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """UPDATE compiled_playbooks
                   SET consecutive_failures = consecutive_failures + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (playbook_id,),
            )
            row = conn.execute(
                "SELECT consecutive_failures FROM compiled_playbooks WHERE id = ?",
                (playbook_id,),
            ).fetchone()
            if (
                row
                and int(row["consecutive_failures"]) >= self.max_consecutive_failures
            ):
                conn.execute(
                    """UPDATE compiled_playbooks
                       SET status = 'decompiled',
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (playbook_id,),
                )
                pb = self._cache.get(playbook_id)
                if pb is not None:
                    pb.status = "decompiled"
                return
        pb = self._cache.get(playbook_id)
        if pb is not None:
            pb.consecutive_failures += 1

    def invalidate_for_skill(self, skill_id: int) -> bool:
        """Mark any compiled playbook for *skill_id* as decompiled.

        Called when the source skill is demoted from 'verified' back to
        'candidate'. Returns True if a playbook was decompiled.
        """
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                """UPDATE compiled_playbooks
                   SET status = 'decompiled', updated_at = CURRENT_TIMESTAMP
                   WHERE skill_id = ? AND status = 'compiled'""",
                (skill_id,),
            )
            if cur.rowcount > 0:
                self._refresh_cache()
                return True
        return False

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _refresh_cache(self) -> None:
        """Load compiled playbooks from DB into memory cache."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, skill_id, goal_pattern, signature_v2,
                          steps_json, compiled_at, replay_count,
                          consecutive_failures, status
                   FROM compiled_playbooks
                   WHERE status = 'compiled'"""
            ).fetchall()
        self._cache.clear()
        for row in rows:
            try:
                steps_data = json.loads(row["steps_json"])
                steps = [PlaybookStep.from_dict(s) for s in steps_data]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            self._cache[row["id"]] = CompiledPlaybook(
                id=row["id"],
                skill_id=row["skill_id"],
                goal_pattern=row["goal_pattern"],
                signature_v2=row["signature_v2"] or "",
                steps=steps,
                compiled_at=row["compiled_at"] or "",
                replay_count=row["replay_count"],
                consecutive_failures=row["consecutive_failures"],
                status=row["status"],
            )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def compiled_count(self) -> int:
        """Return the number of active compiled playbooks."""
        self._refresh_cache()
        return len(self._cache)

    def playbook_map(self) -> list[dict[str, Any]]:
        """Observable map of all compiled playbooks (for HUD/debugging)."""
        self._refresh_cache()
        return [
            {
                "id": pb.id,
                "skill_id": pb.skill_id,
                "goal_pattern": pb.goal_pattern,
                "step_count": len(pb.steps),
                "steps": [s.to_dict() for s in pb.steps],
                "replay_count": pb.replay_count,
                "consecutive_failures": pb.consecutive_failures,
                "status": pb.status,
            }
            for pb in self._cache.values()
        ]
