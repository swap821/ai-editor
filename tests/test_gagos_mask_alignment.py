"""Masking holds wherever the file lands in the prompt (2026-11-12).

The frozen secret scanner's sliding window starts at every fifth character of
the whole payload, so an ordinary line of code can be scrubbed at one offset
and not at another. GAGOS masked each file alone (offset 0) and then checked
the assembled prompt, where the same line sat at another offset: the
operator's goal gt-838f049241 was refused unsent, "the secret policy would
scrub this file". Pinned without a model:

* the scanner's behaviour that causes it (a real line from
  useWorkMaterialization.js, scrubbed only at 2 mod 5);
* masking with the old oracle misses it at the offset the prompt used;
* ``mask_redact`` masks it, so the masked text survives the scrubbers at
  every offset, and unmasking restores the file exactly.
"""

from __future__ import annotations

import pytest

from aios.maintenance.daily_work import mask_lines, unmask
from tools import gagos_daily as tool

LINE = (
    "        if (turnTokenRef.current !== token || "
    "!ownsWorkSurface(writingTab.id, token)) return;"
)
FILE = "const a = 1;\n" + LINE + "\nexport default a;\n"


def _scrubbed_at(text: str, offset: int) -> bool:
    padded = " " * offset + text
    return tool.egress_redact(padded) != padded


def test_the_scanner_scrubs_the_line_only_at_some_offsets() -> None:
    offsets = [k for k in range(2 * tool.SCAN_ALIGNMENTS) if _scrubbed_at(LINE, k)]
    assert offsets, "the scanner no longer flags this line at any offset"
    assert len(offsets) < 2 * tool.SCAN_ALIGNMENTS, "flagged everywhere"


def test_masking_at_one_offset_missed_it_where_the_prompt_put_it() -> None:
    masked, _mapping = mask_lines(FILE, tool.egress_redact)
    assert any(_scrubbed_at(masked, k) for k in range(tool.SCAN_ALIGNMENTS)), (
        "the old oracle now catches it; this test pins the defect it fixed"
    )


@pytest.mark.parametrize("offset", range(2 * tool.SCAN_ALIGNMENTS))
def test_the_masked_file_survives_the_scrubbers_at_every_offset(offset) -> None:
    masked, mapping = mask_lines(FILE, tool.mask_redact)
    assert mapping, "nothing was masked"
    assert not _scrubbed_at(masked, offset)
    assert unmask(masked, mapping, masked=masked) == FILE


def test_a_file_with_nothing_to_hide_is_left_alone() -> None:
    plain = "const total = items.length;\nexport default total;\n"
    assert tool.mask_redact(plain) == plain
    assert mask_lines(plain, tool.mask_redact) == (plain, {})


def test_every_masking_call_asks_the_alignment_aware_oracle() -> None:
    import re

    from tests.source_rules import executable_source

    calls = re.findall(r"mask_lines\(\s*[^,]+,\s*(\w+)", executable_source(tool))
    assert calls and set(calls) == {"mask_redact"}, calls
