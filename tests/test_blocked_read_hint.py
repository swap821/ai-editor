"""A blocked file-read must name the tool that would have worked.

Measured in one 5-mission cohort on gemini-3.1-pro-preview: the model spent
ELEVEN iterations trying to read files it had just written --

    BLOCKED: cat training_ground/test_calculator.py
    BLOCKED: ls -la training_ground/test_sorted_insert.py
    BLOCKED: python -c "print(open('training_ground/test_sorted_insert.py').read())"
    CREATE:  training_ground/read_it.py      <- a script written only to read
    CREATE:  training_ground/read_b64.py     <- and another
    BLOCKED: python training_ground/read_b64.py

-- while `read_file` sat in its tool list the whole time. Each refusal said
"[BLOCKED] <reason>" and offered nowhere to go, so the model tried the next
spelling.

Same dead end #215/#238 fixed for no-op writes and #240 fixed for edit_file.
The gate does not move: the command is still blocked, nothing new is permitted.
Only the message gains a next step.
"""
from __future__ import annotations

import pytest

from aios.agents.tool_handlers import next_step_after_blocked_read


READS = [
    "cat training_ground/x.py",
    r"type training_ground\x.py",
    "head -n 20 training_ground/x.py",
    "tail training_ground/x.py",
    "more training_ground/x.py",
    "Get-Content training_ground/x.py",
]

LISTS = [
    "ls -la training_ground/",
    "dir training_ground",
    "Get-ChildItem training_ground",
    "tree training_ground",
]

INLINE_READS = [
    "python -c \"print(open('training_ground/x.py').read())\"",
    "python -c \"with open('training_ground/x.py') as f: print(f.read())\"",
]

#: Refusals that must stay unadorned -- a hint on these would be noise at best
#: and misdirection at worst.
NOT_READS = [
    "pytest training_ground/x.py",
    "pip install requests",
    "rm -rf /",
    "git clone https://example.com/x",
    "python training_ground/app.py",
    "",
    "   ",
]


@pytest.mark.parametrize("command", READS)
def test_a_blocked_file_read_names_read_file(command: str) -> None:
    hint = next_step_after_blocked_read(command)
    assert "read_file" in hint, f"no way forward offered for {command!r}"


@pytest.mark.parametrize("command", LISTS)
def test_a_blocked_listing_names_read_directory(command: str) -> None:
    hint = next_step_after_blocked_read(command)
    assert "read_directory" in hint, f"no way forward offered for {command!r}"


@pytest.mark.parametrize("command", INLINE_READS)
def test_an_inline_python_read_is_recognised(command: str) -> None:
    """The shape the model escalated to after cat and ls were refused."""
    assert "read_file" in next_step_after_blocked_read(command)


@pytest.mark.parametrize("command", NOT_READS)
def test_other_refusals_stay_unadorned(command: str) -> None:
    assert next_step_after_blocked_read(command) == "", (
        f"{command!r} is not a read attempt and must not be given a read hint"
    )


def test_the_hint_carries_the_path_so_the_model_can_act() -> None:
    """A next step the model must guess at is only half a next step."""
    hint = next_step_after_blocked_read("cat training_ground/user_registry.py")

    assert "training_ground/user_registry.py" in hint


def test_a_malformed_command_cannot_break_the_refusal() -> None:
    """A hint must never be able to fail a security path."""
    for command in ('cat "unclosed', "cat $(", "\x00", "cat " + "x" * 5000):
        next_step_after_blocked_read(command)  # must not raise


def test_the_refusal_itself_is_unchanged() -> None:
    """The gate does not move: BLOCKED is still BLOCKED, hint or not."""
    from types import SimpleNamespace

    from aios.agents.tool_handlers import _format_exec_result

    blocked = SimpleNamespace(
        status="BLOCKED", reason="RED zone command refused.",
        command="cat training_ground/x.py", stdout="", stderr="", exit_code=1,
    )
    output, status, failed = _format_exec_result(blocked)

    assert status == "blocked"
    assert output.startswith("[BLOCKED] RED zone command refused.")
    assert "read_file" in output
