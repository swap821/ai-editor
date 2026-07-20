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
}

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


def _extract_module_name(prompt: str) -> Optional[str]:
    m = re.search(r"training_ground/(\w+)\.py", prompt)
    return m.group(1) if m else None


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
        module_name = _extract_module_name(source_prompt)
        if not module_name:
            return []

        proposals: list[CurriculumProposal] = []
        templates = _ESCALATION_TEMPLATES.get("create_and_test", [])

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
