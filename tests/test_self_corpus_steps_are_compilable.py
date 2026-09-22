"""Every step the self-corpus records must be one the cerebellum can compile.

Two halves of this system write procedural steps: the chat turn path via
`turn_pipeline._workflow_step`, and the self-corpus via
`self_corpus_grading.pin_steps`. One half reads them: `cerebellum._parse_step`.

They had drifted. The self-corpus recorded `create_file: <name>` while the
parser requires `create_file: filepath=..., content_sha256=<64 hex>`, and a
single unparseable step makes the WHOLE arc uncompilable. So every skill the
self-corpus ever earned was silently barred from becoming a reflex: the arc
verified, the compiler skipped it, and the chain stopped one link short with
nothing reporting why.

This is the differential shape that has found real bugs in this repository
before — do two layers that must agree actually agree? A docstring promising
they do is not the same as asking them.
"""

from __future__ import annotations

import hashlib

from aios.core.cerebellum import _COMPILABLE_TOOLS, _parse_step
from tools.self_corpus_grading import content_digest, pin_steps

SOURCE = "def test_x():\n    assert 1 + 1 == 2\n"
STEPS = pin_steps(
    "aios/agents/tool_agent.py", "tests/test_pin_x.py", content_digest(SOURCE)
)


class TestTheParserAcceptsEveryStepWeRecord:
    def test_every_step_parses(self) -> None:
        for step in STEPS:
            assert _parse_step(step) is not None, (
                f"the cerebellum cannot parse a step the self-corpus records, so "
                f"no self-corpus skill can ever compile: {step!r}"
            )

    def test_every_tool_is_compilable(self) -> None:
        for step in STEPS:
            assert step.split(":", 1)[0] in _COMPILABLE_TOOLS

    def test_the_values_survive_parsing(self) -> None:
        """A `key=` prefix left on the value makes every replay abort RED."""
        parsed = {p.tool_name: p.args for p in map(_parse_step, STEPS)}
        assert parsed["read_file"]["filepath"] == "aios/agents/tool_agent.py"
        assert parsed["create_file"]["filepath"] == "tests/test_pin_x.py"
        assert parsed["verify"]["command"] == "pytest tests/test_pin_x.py"

    def test_the_create_digest_is_the_real_content_hash(self) -> None:
        """A replay CONFIRMS a create_file by comparing bytes to this hash, so a
        wrong digest would make the reflex abstain on a file it wrote itself."""
        parsed = _parse_step(STEPS[1])
        assert (
            parsed.args["content_sha256"]
            == hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
        )


class TestTheOldShapeWouldHaveFailed:
    """Proof the bug was real, not theoretical."""

    def test_a_bare_create_file_step_does_not_parse(self) -> None:
        assert _parse_step("create_file: tests/test_pin_x.py") is None

    def test_one_unparseable_step_is_enough_to_block_an_arc(self) -> None:
        """The compile guard needs ALL steps; this is why the bug was total."""
        mixed = [STEPS[0], "create_file: tests/test_pin_x.py", STEPS[2]]
        assert any(_parse_step(s) is None for s in mixed)


class TestOneDerivationForTheVerifyCommand:
    """The verify command appears in three places that must agree exactly.

    It is the recorded step, the command a failure's lesson is keyed to, and
    the command whose later success confirms that lesson. A single differing
    flag makes the lesson permanently unpromotable — which is precisely how
    every lesson in the live pool ended up unable to graduate.
    """

    def test_the_step_and_the_helper_agree(self) -> None:
        from tools.self_corpus_grading import _pin_verify_command

        command = _pin_verify_command("tests/test_pin_x.py")
        assert f"verify: command={command}" == STEPS[2]
        assert _parse_step(STEPS[2]).args["command"] == command


class TestAStoredRecipeCanImprove:
    """An arc recorded in a poorer shape must be able to become compilable.

    `record_attempt` updates counts but historically never rewrote
    `steps_json` except to drop redaction artifacts. So an arc first recorded
    with an unparseable `create_file` step stayed unparseable forever, and
    could never become a reflex however often it verified. Observed live:
    skill 66, verified at 8 successes and 0 failures from real code, silently
    uncompilable.

    Counts are still never rewritten. This is about the RECIPE — the thing
    recalled into future context and handed to the compiler.
    """

    from aios.memory.skills import _better_recipe  # noqa: PLC0415

    OLD = '["read_file: a.py", "create_file: t.py", "verify: pytest"]'
    NEW = (
        '["read_file: filepath=a.py", '
        '"create_file: filepath=t.py, content_sha256=' + "0" * 64 + '", '
        '"verify: command=pytest t.py"]'
    )

    def test_a_more_compilable_recipe_wins(self) -> None:
        from aios.memory.skills import _better_recipe

        assert _better_recipe(self.NEW, self.OLD) is True

    def test_a_less_compilable_recipe_does_not(self) -> None:
        """The rule must not run backwards and downgrade a good recipe."""
        from aios.memory.skills import _better_recipe

        assert _better_recipe(self.OLD, self.NEW) is False

    def test_an_identical_recipe_is_not_an_improvement(self) -> None:
        """Otherwise every success rewrites the row for nothing."""
        from aios.memory.skills import _better_recipe

        assert _better_recipe(self.NEW, self.NEW) is False

    def test_fewer_redactions_still_wins(self) -> None:
        """The original rule keeps working."""
        from aios.memory.skills import _better_recipe

        noisy = '["read_file: filepath=<REDACTED:HIGH_ENTROPY:abcd1234>.py"]'
        clean = '["read_file: filepath=a.py"]'
        assert _better_recipe(clean, noisy) is True
        assert _better_recipe(noisy, clean) is False

    def test_a_trade_off_is_refused(self) -> None:
        """Better on one axis, worse on the other, is not an improvement.

        Silently swapping in that case would make stored history change for
        reasons nobody can reconstruct.
        """
        from aios.memory.skills import _better_recipe

        gained_compilable_lost_clean = (
            '["verify: command=pytest <REDACTED:HIGH_ENTROPY:dd53fe01>.py"]'
        )
        clean_but_uncompilable = '["verify: pytest"]'
        assert (
            _better_recipe(gained_compilable_lost_clean, clean_but_uncompilable)
            is False
        )

    def test_a_verified_arc_upgrades_on_its_next_success(self, tmp_path) -> None:
        """End to end: the stuck arc becomes compilable without losing counts."""
        import json as _json

        from aios.core.cerebellum import Cerebellum
        from aios.core.verification_strength import VerificationStrength
        from aios.memory.db import get_connection, init_memory_db
        from aios.memory.skills import SkillMemory

        db = tmp_path / "memory.sqlite"
        init_memory_db(db)
        skills = SkillMemory(db_path=db)
        goal = "pin the behaviour of a.py::thing via clerk"
        old_steps = ["read_file: a.py", "create_file: t.py", "verify: pytest"]
        for _ in range(3):
            skills.record_attempt(
                goal, old_steps, success=True, strength=VerificationStrength.STRONG
            )
        assert Cerebellum(db).try_compile_all() == 0, "the old shape cannot compile"

        new_steps = pin_steps("a.py", "t.py", content_digest("x"))
        skills.record_attempt(
            goal, new_steps, success=True, strength=VerificationStrength.STRONG
        )

        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT steps_json, success_count FROM procedural_skills"
            ).fetchone()
        assert _json.loads(row["steps_json"]) == new_steps
        assert row["success_count"] == 4, "counts accumulate; they are never rewritten"
        assert Cerebellum(db).try_compile_all() == 1
