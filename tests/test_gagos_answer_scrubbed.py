"""An answer scrubbed on its way back is refused for that, not as the writer's
fault (2026-11-13).

GPT-6.1 Terra's eighth-hour PERF-04 test (gd-dded5807ee) kept the store's
retraction token in ``const token = getTabStoreSnapshot()...``. The gateway's
secret scanner (frozen core) reads ``token = <12+ characters>`` as a leaked
key and scrubbed it from the answer, so the file came back as ``const
<REDACTED:ASSIGNED_SECRET:622dfa91>().tabs...`` and was refused as "does not
parse". Now such an answer is refused saying what happened, and every writer
is told not to give a variable one of those names.
"""

from __future__ import annotations

import pytest

from aios.maintenance import daily_work as dw
from aios.runtime.secret_policy import SecretPolicy

LINE = "const token = getTabStoreSnapshot().tabs;"
BASE = "const a = 1;\n"


def test_the_cause_the_scanner_scrubs_a_code_line_naming_a_token() -> None:
    scrubbed = SecretPolicy().inspect_text(LINE).scrubbed
    assert scrubbed.startswith("const <REDACTED:ASSIGNED_SECRET:")


def _scrubbed_answer() -> str:
    return "```ts\n" + SecretPolicy().inspect_text(BASE + LINE).scrubbed + "\n```"


def test_a_whole_file_answer_scrubbed_in_transit_is_refused_for_it() -> None:
    with pytest.raises(dw.ProposalRefused, match="scrubbed on its way back") as exc:
        dw.parse_proposal(_scrubbed_answer(), original=BASE)
    assert "ASSIGNED_SECRET" in str(exc.value)


def test_an_edit_answer_scrubbed_in_transit_is_refused_for_it() -> None:
    raw = (
        "<<<<<<< SEARCH\nconst a = 1;\n=======\n"
        + SecretPolicy().inspect_text(LINE).scrubbed
        + "\n>>>>>>> REPLACE\n"
    )
    with pytest.raises(dw.ProposalRefused, match="scrubbed on its way back"):
        dw.parse_edits(raw, BASE)


def test_a_mark_the_file_already_held_is_the_files_own() -> None:
    """The privacy filter's own tests hold its marks as text: a change to such
    a file is not refused for keeping them."""
    original = "expect(out).toBe('[PATH REDACTED]');\n"
    raw = "```ts\nexpect(out).toBe('[PATH REDACTED]');\nconst b = 2;\n```"
    assert "const b = 2;" in dw.parse_proposal(raw, original=original)


@pytest.mark.parametrize(
    "system",
    [
        dw.PROPOSER_SYSTEM,
        dw.PYTHON_PROPOSER_SYSTEM,
        dw.TASK_SYSTEM,
        dw.PYTHON_TASK_SYSTEM,
        dw.TESTER_SYSTEM,
        dw.task_files_system(["frontend/src/a.ts", "aios/b.py"]),
    ],
)
def test_every_writer_is_told_and_the_telling_passes_the_scanners(system) -> None:
    from tools import gagos_daily as tool

    assert dw.SCANNER_NAMES_NOTE in system
    assert tool.would_be_altered("x", system) is None
