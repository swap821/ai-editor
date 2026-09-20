"""A lesson must survive the retry being TYPED differently — and only that.

`confirm()` promotes a lesson when the command that produced it succeeds. It
compared the two strings byte-for-byte, so a retry that differed only in
whitespace — CRLF from a Windows tool call, a trailing space, a re-indented
wrapped line — looked like a different command and the lesson stayed pending
forever. Nothing reported it; the verified count simply never moved.

The other half of these tests is the part that must NOT change. Promotion on
resemblance is worse than no promotion at all: a wrongly-verified lesson feeds
planner confidence and is recalled into every later turn. So flag order,
newline structure, and the verification-strength floor are pinned here as
things normalization deliberately does not touch.
"""

from __future__ import annotations

from aios.agents import tool_loop_helpers
from aios.core.verification_strength import VerificationStrength


def _promote(pending: list[tuple[int, str]], command: str, **kwargs) -> list[int]:
    """Run confirm() and return the ids it actually promoted."""
    promoted: list[int] = []
    events = list(
        tool_loop_helpers.confirm(
            pending,
            command,
            0,
            lambda mistake_id: promoted.append(mistake_id),
            **kwargs,
        )
    )
    assert len(events) == (1 if promoted else 0)
    return promoted


class TestTheSameCommandTypedDifferently:
    def test_crlf_retry_still_promotes(self) -> None:
        """Windows tool calls routinely round-trip through CRLF."""
        pending = [(1, "pytest tests/a.py\npytest tests/b.py")]
        assert _promote(pending, "pytest tests/a.py\r\npytest tests/b.py") == [1]

    def test_surrounding_whitespace_still_promotes(self) -> None:
        pending = [(2, "pytest tests/a.py")]
        assert _promote(pending, "  pytest tests/a.py  ") == [2]

    def test_collapsed_indentation_still_promotes(self) -> None:
        pending = [(3, "pytest    -q     tests/a.py")]
        assert _promote(pending, "pytest -q tests/a.py") == [3]

    def test_a_promoted_lesson_is_removed_from_the_pending_list(self) -> None:
        """Otherwise the next success promotes it a second time."""
        pending = [(4, "pytest tests/a.py ")]
        _promote(pending, "pytest tests/a.py")
        assert pending == []

    def test_a_redacted_stored_command_matches_its_raw_retry(self) -> None:
        """Lessons are stored scrubbed; the live retry is not.

        Without redacting both sides, any command carrying a credential could
        never be matched to its own success — the lesson would be permanently
        unpromotable for exactly the commands most worth learning from.
        """
        raw = "curl -H 'Authorization: Bearer sk-abcdef0123456789abcdef0123456789'"
        stored = tool_loop_helpers.normalize_command(raw)
        assert _promote([(5, stored)], raw) == [5]


class TestWhatNormalizationMustNotDo:
    def test_reordered_flags_do_not_promote(self) -> None:
        """Sorting tokens needs a grammar to keep `--model` with its value."""
        pending = [(6, "pytest -q tests/a.py")]
        assert _promote(pending, "pytest tests/a.py -q") == []

    def test_a_different_heredoc_body_does_not_promote(self) -> None:
        """Newlines stay significant, so two different bodies stay different."""
        pending = [(7, "cat <<EOF\nalpha\nEOF")]
        assert _promote(pending, "cat <<EOF\nbeta\nEOF") == []

    def test_a_different_command_does_not_promote(self) -> None:
        pending = [(8, "pytest tests/a.py")]
        assert _promote(pending, "pytest tests/b.py") == []

    def test_a_weak_green_does_not_promote(self) -> None:
        """The promotion floor is untouched by any of this."""
        pending = [(9, "pytest tests/a.py")]
        assert (
            _promote(pending, "pytest tests/a.py", strength=VerificationStrength.WEAK)
            == []
        )
        assert pending == [(9, "pytest tests/a.py")], (
            "a below-floor success must leave the lesson pending AND still "
            "pending-tracked, so a later strong success can still confirm it"
        )

    def test_no_hook_promotes_nothing(self) -> None:
        pending = [(10, "pytest tests/a.py")]
        assert (
            list(tool_loop_helpers.confirm(pending, "pytest tests/a.py", 0, None)) == []
        )
        assert pending == [(10, "pytest tests/a.py")]


class TestNormalizeCommandItself:
    def test_it_is_idempotent(self) -> None:
        """It runs on stored values that were already normalized once."""
        once = tool_loop_helpers.normalize_command("  pytest   -q  tests/a.py \r\n ")
        assert tool_loop_helpers.normalize_command(once) == once

    def test_it_does_not_invent_a_match_for_empty_input(self) -> None:
        assert tool_loop_helpers.normalize_command("   \r\n  ") == ""
