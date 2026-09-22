"""Self-curriculum miner: generates new training tasks from audit evidence.

Reads verified-success outcomes from the development evidence store and
harness audit logs, identifies task patterns the system has demonstrated
competence in, and proposes harder variants as new curriculum entries.

The miner NEVER executes tasks or modifies the curriculum directly.
It produces proposals that a human (or the operator via the API) must
explicitly accept before they enter the curriculum. This keeps the
authority boundary intact: the system can suggest what to practice next,
but cannot unilaterally expand its own training.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance


@dataclass(frozen=True)
class CurriculumProposal:
    """A proposed new curriculum task generated from evidence."""

    skill_name: str
    level: int
    prompt: str
    rationale: str
    source_pattern: str
    difficulty_delta: str
    #: A level with no held-out task can NEVER be mastered -- `_refresh_level`
    #: gates on ``bool(held_out) and all(...)``, so an empty held-out set is
    #: False forever. Nothing automatic ever created one, which made mastery
    #: inert out of the box. Mining a held-out sibling alongside the training
    #: variant is what lets a level become masterable without a hand-written
    #: operator POST.
    held_out: bool = False

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()[:16]


# Task pattern templates for generating harder variants
_ESCALATION_TEMPLATES: dict[str, list[str]] = {
    "create_and_test": [
        "Create training_ground/{module}.py with {description}. Add error handling for invalid inputs (raise appropriate exceptions). Then create training_ground/test_{module}.py with pytest tests covering both normal behavior and error cases. Then verify that the tests pass.",
        "Create training_ground/{module}.py with {description}. Ensure it handles edge cases (empty input, very large input, None values). Then create training_ground/test_{module}.py with pytest tests covering at least 8 distinct scenarios. Then verify that the tests pass.",
        "Create training_ground/{module}.py with {description}. Include type hints on all public functions. Then create training_ground/test_{module}.py with pytest tests using parametrize for comprehensive coverage. Then verify that the tests pass.",
    ],
    "refactor_and_test": [
        "Edit training_ground/{module}.py to refactor {description} into smaller, more testable functions. Then update training_ground/test_{module}.py to test each extracted function individually. Then verify that the tests pass.",
    ],
    "extend_and_test": [
        "Edit training_ground/{module}.py to add {description}. Then edit training_ground/test_{module}.py to add tests for the new functionality. Then verify that the tests pass.",
    ],
    # THE REAL-CODE FAMILY.
    #
    # Every family above names `training_ground/`, so a verified success on
    # this repository's own source produced no proposal at all: the miner could
    # RUN on real turns and still only ever propose toy work. That was L6's
    # standing blocker, and it is a design limit rather than a regex typo --
    # which is why the fix is a family, not a widened pattern.
    #
    # The escalation for real code is to PIN MORE OF ITS BEHAVIOUR: read the
    # module, write characterisation tests, run them. It never edits the
    # source, because a curriculum that proposes editing this repository's own
    # code as practice is a different and much larger proposition than one that
    # proposes describing it. The proposal is still only a proposal -- nothing
    # here accepts it.
    "pin_real_behaviour": [
        "Read {path} and then create {test_path} with pytest tests that pin the current behaviour of {description}. Do not edit {path}. Then verify that the tests pass.",
        "Read {path} and then create {test_path} with pytest tests that pin {description}, including the error paths. Do not edit {path}. Then verify that the tests pass.",
    ],
}


def _template_family(source_prompt: str) -> str:
    """Which escalation family fits the SOURCE task's shape.

    `_generate_variants` hardcoded "create_and_test", so the other two families
    were unreachable: a refactor task escalated into a create task, and the
    curriculum could only ever get harder along one axis. Derive it instead.

    Ordering matters -- "refactor" is checked before the generic edit/add case
    because a refactor prompt also contains "Edit".
    """
    lowered = source_prompt.lower()
    if "refactor" in lowered:
        return "refactor_and_test"
    if lowered.startswith("edit ") or " to add " in lowered:
        return "extend_and_test"
    return "create_and_test"


# Skill categories inferred from task patterns
_SKILL_PATTERNS: dict[str, re.Pattern[str]] = {
    "python-data-structures": re.compile(
        r"(stack|queue|linked.?list|tree|graph|hash.?map|heap|trie|cache)", re.I
    ),
    "python-algorithms": re.compile(
        r"(sort|search|fibonacci|factorial|permut|combinat|dynamic.?prog|greedy|recursive)",
        re.I,
    ),
    "python-string-processing": re.compile(
        r"(string|text|parse|csv|json|format|regex|slug|roman|palindrome)", re.I
    ),
    "python-error-handling": re.compile(
        r"(error|exception|raise|try|validate|safe_|robust)", re.I
    ),
    "python-testing": re.compile(
        r"(test|tdd|assert|mock|fixture|parametrize|coverage)", re.I
    ),
    "python-design-patterns": re.compile(
        r"(pipeline|factory|observer|strategy|decorator|state.?machine|builder)", re.I
    ),
}


def _infer_skill(prompt: str) -> str:
    for skill, pattern in _SKILL_PATTERNS.items():
        if pattern.search(prompt):
            return skill
    return "python-general"


#: Directories that hold DISPOSABLE practice code. Work inside them is the toy
#: world; work anywhere else in the repository is real.
_TOY_ROOTS = ("training_ground/", "lab/")

#: Any repo-relative python file named in a prompt. Deliberately not anchored to
#: one directory -- that anchoring WAS the blocker.
_PY_TARGET = re.compile(r"\b([A-Za-z0-9_][\w./-]*/)?([A-Za-z_]\w*)\.py\b")


@dataclass(frozen=True)
class MiningTarget:
    """The file a source task worked on, and which world it lives in."""

    path: str
    module: str

    @property
    def real(self) -> bool:
        """True when this is the repository's own code rather than practice code.

        A bare filename with no directory is treated as toy: it names nothing
        this repository can locate, so proposing work against it would be
        proposing work against a guess.
        """
        return "/" in self.path and not self.path.startswith(_TOY_ROOTS)


def _extract_target(prompt: str) -> Optional[MiningTarget]:
    """The first python file a prompt names, toy or real.

    Test files are skipped when the prompt also names a non-test module: a task
    about `tool_agent.py` that happens to mention `test_tool_agent.py` is about
    the module, and proposing tests-for-the-tests is escalation in name only.
    """
    matches = [
        MiningTarget(path=(m.group(1) or "") + m.group(2) + ".py", module=m.group(2))
        for m in _PY_TARGET.finditer(prompt)
    ]
    if not matches:
        return None
    for target in matches:
        if not target.module.startswith("test_"):
            return target
    return matches[0]


def _extract_module_name(prompt: str) -> Optional[str]:
    """The toy-world module name, unchanged.

    Kept exactly as it was: the toy families interpolate `{module}` into a
    `training_ground/...` path, so widening THIS function would have silently
    pointed toy templates at real files. The real family uses `_extract_target`
    and its own templates instead.
    """
    m = re.search(r"training_ground/(\w+)\.py", prompt)
    return m.group(1) if m else None


#: A symbol the source task named, for the proposal to be about something
#: narrower than "the whole module".
_SYMBOL = re.compile(r"(?:::|\b(?:function|method|class)\s+)([A-Za-z_]\w*)")


def _real_description(prompt: str, target: MiningTarget) -> str:
    match = _SYMBOL.search(prompt)
    if match:
        return f"{match.group(1)}()"
    return f"the public functions of {target.module}"


def _task_complexity_score(prompt: str) -> int:
    score = 0
    if "edge case" in prompt.lower():
        score += 1
    if "error" in prompt.lower() or "exception" in prompt.lower():
        score += 1
    if "parametrize" in prompt.lower():
        score += 1
    if "refactor" in prompt.lower():
        score += 1
    if "Edit" in prompt:
        score += 1
    word_count = len(prompt.split())
    if word_count > 80:
        score += 1
    return score


class CurriculumMiner:
    """Mines verified outcomes for curriculum task proposals."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def mine_from_development(
        self,
        *,
        existing_prompts: Optional[set[str]] = None,
        max_proposals: int = 10,
    ) -> list[CurriculumProposal]:
        """Generate proposals from verified-success development events.

        Reads task_text from verified successes, groups by inferred skill,
        determines current mastery level, and proposes harder variants.
        """
        if existing_prompts is None:
            existing_prompts = self._get_existing_prompts()

        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT task_text FROM development_events "
                "WHERE outcome = 'verified_success' "
                "ORDER BY id DESC LIMIT 500",
            ).fetchall()

        if not rows:
            return []

        by_skill: dict[str, list[str]] = {}
        for row in rows:
            text = str(row["task_text"])
            skill = _infer_skill(text)
            by_skill.setdefault(skill, []).append(text)

        proposals: list[CurriculumProposal] = []
        for skill, tasks in by_skill.items():
            max_complexity = max(_task_complexity_score(t) for t in tasks)
            next_level = max_complexity + 2

            for task in tasks[:3]:
                new_proposals = self._generate_variants(
                    task, skill, next_level, existing_prompts
                )
                proposals.extend(new_proposals)
                if len(proposals) >= max_proposals:
                    break
            if len(proposals) >= max_proposals:
                break

        return proposals[:max_proposals]

    def mine_from_audit_log(
        self,
        audit_path: Path,
        *,
        existing_prompts: Optional[set[str]] = None,
        max_proposals: int = 10,
    ) -> list[CurriculumProposal]:
        """Generate proposals from harness audit logs (JSONL files).

        Reads session-complete records from experience accumulator /
        golden mission logs and proposes new tasks from successful patterns.
        """
        if existing_prompts is None:
            existing_prompts = self._get_existing_prompts()

        if not audit_path.exists():
            return []

        successful_prompts: list[str] = []
        try:
            with audit_path.open() as fh:
                for line in fh:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        record.get("kind") == "session-complete"
                        and record.get("outcome") == "verified_success"
                    ):
                        prompt = record.get("prompt") or record.get(
                            "answer_preview", ""
                        )
                        if prompt:
                            successful_prompts.append(prompt)
                    elif (
                        record.get("kind") == "turn-done"
                        and record.get("outcome") == "verified_success"
                    ):
                        prompt = record.get("prompt", "")
                        if prompt:
                            successful_prompts.append(prompt)
        except OSError:
            return []

        proposals: list[CurriculumProposal] = []
        for prompt in successful_prompts[:20]:
            skill = _infer_skill(prompt)
            complexity = _task_complexity_score(prompt)
            new_proposals = self._generate_variants(
                prompt, skill, complexity + 2, existing_prompts
            )
            proposals.extend(new_proposals)
            if len(proposals) >= max_proposals:
                break

        return proposals[:max_proposals]

    def _generate_variants(
        self,
        source_prompt: str,
        skill_name: str,
        target_level: int,
        existing_prompts: set[str],
    ) -> list[CurriculumProposal]:
        target = _extract_target(source_prompt)
        if target is not None and target.real:
            return self._generate_real_variants(
                source_prompt, target, skill_name, target_level, existing_prompts
            )

        module_name = _extract_module_name(source_prompt)
        if not module_name:
            return []

        proposals: list[CurriculumProposal] = []
        # Pick the family from the SOURCE task's shape. This was hardcoded to
        # "create_and_test", which made `refactor_and_test` and
        # `extend_and_test` unreachable dead code -- every mined proposal came
        # out a "create + test" variant no matter what the source task did, so
        # a refactor skill could only ever be escalated into a create skill.
        templates = _ESCALATION_TEMPLATES.get(
            _template_family(source_prompt), _ESCALATION_TEMPLATES["create_and_test"]
        )

        for template in templates:
            description = self._extract_description(source_prompt)
            if not description:
                continue
            harder_desc = self._escalate_description(description)
            new_module = f"{module_name}_v{target_level}"
            prompt = template.format(module=new_module, description=harder_desc)

            if prompt in existing_prompts:
                continue
            if any(relevance(prompt, ep) > 0.85 for ep in list(existing_prompts)[:50]):
                continue

            proposals.append(
                CurriculumProposal(
                    skill_name=skill_name,
                    level=target_level,
                    prompt=prompt,
                    rationale=f"Escalation from verified task in {module_name}",
                    source_pattern=source_prompt[:200],
                    difficulty_delta=f"level {target_level} (added error handling / edge cases / type hints)",
                )
            )
            existing_prompts.add(prompt)
            break

        # A HELD-OUT SIBLING, from a different template than the training task.
        #
        # Without one the level can never be mastered: `_refresh_level` gates on
        # ``bool(held_out) and all(...)``, so an empty held-out set is False
        # forever and the transition is a silent permanent no-op. Nothing
        # automatic created one -- only a privileged operator POST could -- so
        # out of the box the curriculum recorded successes that could never
        # amount to growth.
        #
        # It must be a DIFFERENT prompt, or it is not held out in any meaningful
        # sense: mastery would be proven by the same task that trained it.
        if proposals:
            trained = proposals[0].prompt
            for template in templates:
                description = self._extract_description(source_prompt)
                if not description:
                    continue
                harder_desc = self._escalate_description(description)
                new_module = f"{module_name}_v{target_level}_holdout"
                prompt = template.format(module=new_module, description=harder_desc)
                if prompt == trained or prompt in existing_prompts:
                    continue
                proposals.append(
                    CurriculumProposal(
                        skill_name=skill_name,
                        level=target_level,
                        prompt=prompt,
                        rationale=(
                            "Held-out sibling: a level with no held-out task can "
                            "never be mastered, however many training passes accrue"
                        ),
                        source_pattern=source_prompt[:200],
                        difficulty_delta=f"level {target_level} held-out check",
                        held_out=True,
                    )
                )
                existing_prompts.add(prompt)
                break

        return proposals

    def _generate_real_variants(
        self,
        source_prompt: str,
        target: MiningTarget,
        skill_name: str,
        target_level: int,
        existing_prompts: set[str],
    ) -> list[CurriculumProposal]:
        """Escalate work on the repository's own code.

        Same two-proposal shape as the toy path -- one training task and one
        held-out sibling from a DIFFERENT template -- because the reason for the
        held-out task does not change with the subject: a level with no held-out
        task can never be mastered, so mining only the trainer would propose a
        level that is permanently un-masterable.

        The proposals describe reading and pinning, never editing. Nothing here
        accepts them; `add_task` is still somebody else's call.
        """
        templates = _ESCALATION_TEMPLATES["pin_real_behaviour"]
        description = _real_description(source_prompt, target)
        proposals: list[CurriculumProposal] = []

        for template in templates:
            suffix = "_holdout" if proposals else ""
            prompt = template.format(
                path=target.path,
                test_path=f"tests/test_{target.module}_pinned_v{target_level}{suffix}.py",
                description=description,
            )
            if prompt in existing_prompts:
                continue
            if not proposals and any(
                relevance(prompt, ep) > 0.85 for ep in list(existing_prompts)[:50]
            ):
                continue
            held_out = bool(proposals)
            proposals.append(
                CurriculumProposal(
                    skill_name=skill_name,
                    level=target_level,
                    prompt=prompt,
                    rationale=(
                        f"Held-out sibling for {target.path}"
                        if held_out
                        else f"Escalation from verified work on {target.path}"
                    ),
                    source_pattern=source_prompt[:200],
                    difficulty_delta=(
                        f"level {target_level} "
                        + ("held-out check" if held_out else "(pin real behaviour)")
                    ),
                    held_out=held_out,
                )
            )
            existing_prompts.add(prompt)
            if held_out:
                break
        return proposals

    def _extract_description(self, prompt: str) -> Optional[str]:
        m = re.search(
            r"with (?:a |an )?(.+?)(?:\. Then|\. Include|\. Ensure|\. Add)", prompt
        )
        if m:
            return m.group(1).strip()
        m = re.search(r"with (.+?)(?:\.|$)", prompt)
        if m:
            return m.group(1).strip()[:200]
        return None

    def _escalate_description(self, description: str) -> str:
        if "error" not in description.lower():
            return f"{description} that also validates inputs and raises ValueError for invalid arguments"
        if "edge" not in description.lower():
            return f"{description} handling edge cases including empty collections and boundary values"
        return f"{description} with O(n log n) time complexity or better"

    def _get_existing_prompts(self) -> set[str]:
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT prompt FROM curriculum_tasks").fetchall()
        return {str(row["prompt"]) for row in rows}

    def list_proposals(self, *, max_proposals: int = 10) -> list[CurriculumProposal]:
        """Convenience: mine from both development events and all audit logs."""
        existing = self._get_existing_prompts()
        proposals: list[CurriculumProposal] = []

        proposals.extend(
            self.mine_from_development(
                existing_prompts=existing, max_proposals=max_proposals
            )
        )

        audit_dir = Path(config.PROJECT_ROOT) / ".aios" / "audit"
        if audit_dir.is_dir():
            for log_file in sorted(audit_dir.glob("*.jsonl")):
                if len(proposals) >= max_proposals:
                    break
                remaining = max_proposals - len(proposals)
                proposals.extend(
                    self.mine_from_audit_log(
                        log_file,
                        existing_prompts=existing,
                        max_proposals=remaining,
                    )
                )

        return proposals[:max_proposals]
