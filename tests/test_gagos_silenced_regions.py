"""What disable comments silence, aligned line by line (Codex's P3 on #567).

GAGOS's unattended check refused a proposal that added or changed a disable
comment, and one that retargeted an unchanged ``disable-next-line``. It still
passed a warning moved into an existing bounded ``eslint-disable`` /
``eslint-enable`` region: the comments were unchanged, and the warning
disappeared from the lint. Counting hidden warnings could not catch it (move
one in and delete another), nor matching them by rule and message (function
A's ``x`` deleted while function B's ``x`` moves in).

Now the original and the proposal are aligned. Every silenced region must
survive whole and in place, and ESLint, run again with inline configuration
off, must show nothing newly hidden on the aligned original line. The cases
below run the real ESLint where it matters; the rest of the alignment is
pinned with fake lint results.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import REL, RULE, _result

UNUSED = "'unused' is assigned a value but never used."


def _finding(line: int = 2) -> dw.Finding:
    return dw.Finding(rel=REL, rule=RULE, warnings=((line, 9, UNUSED),))


def _verdict(before: str, after: str) -> dw.StaticVerdict:
    """The verdict with fake lint results that hide nothing: what the region
    alignment alone decides."""
    return dw.static_verdict(_finding(), before, after, _result(), _result())


# ------------------------------------------------------- the alignment, no ESLint


def test_a_bounded_region_that_reaches_the_end_of_the_file_cannot_grow() -> None:
    before = "/* eslint-disable no-unused-vars */\nconst a = 1;\nconst unused = 1;\n"
    after = "/* eslint-disable no-unused-vars */\nconst a = 1;\nconst b = 2;\n"
    verdict = _verdict(before, after)
    assert not verdict.passed and "disable comment silences" in verdict.reason


def test_nothing_may_be_inserted_inside_a_region() -> None:
    before = (
        "const unused = 1;\n"
        "/* eslint-disable no-console */\n"
        "console.log(1);\n"
        "/* eslint-enable no-console */\n"
    )
    after = before.replace(
        "/* eslint-disable no-console */\n",
        "/* eslint-disable no-console */\nconsole.log(2);\n",
    ).replace("const unused = 1;\n", "")
    assert not _verdict(before, after).passed


def test_lines_may_be_added_right_outside_a_region() -> None:
    before = (
        "const unused = 1;\n"
        "/* eslint-disable no-console */\n"
        "console.log(1);\n"
        "/* eslint-enable no-console */\n"
        "export {};\n"
    )
    above = before.replace("const unused = 1;\n", "// above\n")
    below = before.replace("const unused = 1;\n", "").replace(
        "/* eslint-enable no-console */\n", "/* eslint-enable no-console */\n// below\n"
    )
    assert _verdict(before, above).passed
    assert _verdict(before, below).passed


def test_moving_or_removing_an_enable_changes_the_region() -> None:
    before = (
        "/* eslint-disable no-console */\n"
        "console.log(1);\n"
        "/* eslint-enable no-console */\n"
        "const unused = 1;\n"
        "console.log(2);\n"
    )
    removed = before.replace("/* eslint-enable no-console */\n", "").replace(
        "const unused = 1;\n", ""
    )
    assert not _verdict(before, removed).passed


def test_an_enable_for_other_rules_does_not_end_the_region() -> None:
    lines = [
        "/* eslint-disable no-console, no-alert */",
        "console.log(1);",
        "/* eslint-enable no-console */",
        "alert(1);",
    ]
    assert dw._silenced_regions(lines) == [(0, 3)], "no-alert stays disabled"
    lines[2] = "/* eslint-enable no-console, no-alert */"
    assert dw._silenced_regions(lines) == [(0, 2)]


def test_a_comment_over_several_lines_covers_through_its_close() -> None:
    lines = ["/*", "  eslint-disable-next-line no-console", "*/", "console.log(1);"]
    assert dw._silenced_regions(lines) == [(1, 3)]


def test_two_identical_silencers_each_keep_their_place() -> None:
    pair = "// eslint-disable-next-line no-console\nconsole.log(1);\n"
    before = pair + "const unused = 1;\n" + pair
    assert _verdict(before, pair + pair).passed, (
        "deleting the line between two identical silencers is an ordinary fix"
    )
    assert not _verdict(before, pair + "console.log(1);\n").passed, (
        "removing one of two identical silencers is refused, whichever it was"
    )


def test_a_whole_file_silencer_refuses_any_change_and_cannot_be_added() -> None:
    before = "/* global helper */\nconst unused = helper;\nexport {};\n"
    assert not _verdict(before, "/* global helper */\nexport {};\n").passed
    plain = "const unused = 1;\nexport {};\n"
    added = "/* eslint no-unused-vars: off */\nconst unused = 1;\nexport {};\n"
    verdict = _verdict(plain, added)
    assert not verdict.passed and "disable comment" in verdict.reason


def test_without_the_inline_off_lint_nothing_passes() -> None:
    from aios.maintenance.frontend_static import StaticResult

    blind = StaticResult(messages=())
    verdict = dw.static_verdict(
        _finding(), "const unused = 1;\nexport {};\n", "export {};\n", blind, blind
    )
    assert not verdict.passed and "inline configuration off" in verdict.reason


# ------------------------------------------------------------ with the real ESLint


def _lint(text: str):
    from aios import config
    from aios.maintenance.frontend_static import check_texts

    repo = Path(config.PROJECT_ROOT)
    if (
        shutil.which("node") is None
        or not (repo / "frontend/node_modules/eslint").is_dir()
    ):
        pytest.skip("no node or no frontend toolchain here")
    return check_texts(repo, {REL: text}, inline_off=True)[REL]


def _real(before: str, after: str, finding_line: int = 2) -> dw.StaticVerdict:
    was, now = _lint(before), _lint(after)
    assert [m.line for m in was.warnings(RULE)] == [finding_line], (
        "the fixture's finding is the one warning ESLint shows"
    )
    return dw.static_verdict(_finding(finding_line), before, after, was, now)


def test_real_a_warning_moved_into_a_bounded_region_is_refused() -> None:
    """Codex's count case: move the visible warning into the region and
    delete the one it hid. The lint shows nothing, and the count of hidden
    warnings is unchanged. The lines right after each comment are unchanged
    too, so the check before this one (comment plus the next line) passed it."""
    before = (
        "export function Panel() {\n"
        "  const unused = 2;\n"
        "  /* eslint-disable no-unused-vars */\n"
        "  const keep = 1;\n"
        "  const hiddenA = 1;\n"
        "  /* eslint-enable no-unused-vars */\n"
        "  return null;\n"
        "}\n"
    )
    moved = (
        "export function Panel() {\n"
        "  /* eslint-disable no-unused-vars */\n"
        "  const keep = 1;\n"
        "  const unused = 2;\n"
        "  /* eslint-enable no-unused-vars */\n"
        "  return null;\n"
        "}\n"
    )
    was, now = _lint(before), _lint(moved)
    assert len(was.hidden()) == len(now.hidden()) == 2, "the count is unchanged"
    assert _lint(moved).warnings(RULE) == [], "the lint alone is fooled"
    verdict = _real(before, moved)
    assert not verdict.passed and "disable comment silences" in verdict.reason
    fixed = before.replace("  const unused = 2;\n", "")
    assert _real(before, fixed).passed, (
        "the real fix: the region and what it hides shift up a line, unchanged"
    )


def test_real_an_edit_outside_cannot_newly_hide_a_warning_inside() -> None:
    """The region's lines are untouched, but an edit outside makes a line in
    it unused, and the region hides that."""
    before = (
        "export function Panel() {\n"
        "  const unused = 3;\n"
        "  /* eslint-disable no-unused-vars */\n"
        "  const y = 1;\n"
        "  /* eslint-enable no-unused-vars */\n"
        "  return y;\n"
        "}\n"
    )
    after = (
        "export function Panel() {\n"
        "  /* eslint-disable no-unused-vars */\n"
        "  const y = 1;\n"
        "  /* eslint-enable no-unused-vars */\n"
        "  return null;\n"
        "}\n"
    )
    assert _lint(after).warnings(RULE) == []
    verdict = _real(before, after)
    assert not verdict.passed and "hides a no-unused-vars" in verdict.reason


def test_real_the_same_name_hidden_somewhere_else_is_still_new() -> None:
    """Codex's A.x / B.x case: one hidden x before and one after, with the same
    message, but the original hid A's and the proposal hides B's."""
    before = (
        "export function Panel() {\n"
        "  const unused = 3;\n"
        "  return [a(), b()];\n"
        "}\n"
        "function a() {\n"
        "  // eslint-disable-next-line no-unused-vars\n"
        "  const x = 1;\n"
        "  return 0;\n"
        "}\n"
        "function b() {\n"
        "  // eslint-disable-next-line no-unused-vars\n"
        "  const x = 2;\n"
        "  return x;\n"
        "}\n"
    )
    after = (
        before.replace("  const unused = 3;\n", "")
        .replace("  const x = 1;\n  return 0;\n", "  const x = 1;\n  return x;\n")
        .replace("  const x = 2;\n  return x;\n", "  const x = 2;\n  return 0;\n")
    )
    was, now = _lint(before), _lint(after)
    assert len(was.hidden()) == len(now.hidden()) == 1
    assert was.hidden()[0].message == now.hidden()[0].message
    verdict = dw.static_verdict(_finding(), before, after, was, now)
    assert not verdict.passed and "hides a no-unused-vars" in verdict.reason


def test_an_inline_off_lint_that_reports_nothing_is_unavailable(tmp_path) -> None:
    """Asked for the second lint, a toolchain answer without it is not a pass."""
    import json
    from types import SimpleNamespace

    from aios.maintenance.frontend_static import StaticCheckUnavailable, check_texts

    for tool in ("eslint", "typescript"):
        pkg = tmp_path / "frontend" / "node_modules" / tool / "package.json"
        pkg.parent.mkdir(parents=True)
        pkg.write_text("{}", encoding="utf-8")
    answer = json.dumps({REL: {"messages": [], "parse": []}})

    def run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=answer, stderr="")

    if shutil.which("node") is None:
        pytest.skip("no node here")
    assert check_texts(tmp_path, {REL: "x"}, run=run)[REL].inline_off is None
    with pytest.raises(StaticCheckUnavailable, match="inline-off"):
        check_texts(tmp_path, {REL: "x"}, run=run, inline_off=True)
