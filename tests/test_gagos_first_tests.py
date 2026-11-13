"""GAGOS's second kind of work (2026-11-02): a first test for a module of its
frontend that has none. Pinned here, without a model or a network:

* the work is a module with exports and no test of its name beside it; the
  new test goes beside it, and nothing in the module changes;
* the unattended checks refuse a test that does not parse, has any ESLint
  message, silences a check, reaches outside itself (network, filesystem,
  process, Node built-ins, eval, dynamic import), does not import its module
  or has no expectation -- and execute nothing;
* both reviewers read the module and the whole new test, by name only;
* delivery creates the test only while it is still missing and its module is
  as it was, and removes it again when the checks on master fail.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import (
    BEFORE,
    REL,
    _deliver_args,
    _git,
    _repo,
    _result,
    _warn,
)
from tests.test_gagos_identity_and_day import _both
from tools import gagos_daily as tool

TEST_REL = "frontend/src/workbench/Panel.test.jsx"
TEST = (
    "import { describe, it, expect } from 'vitest';\n"
    "import { render, screen } from '@testing-library/react';\n"
    "import { Panel } from './Panel';\n"
    "\n"
    "describe('Panel', () => {\n"
    "  it('shows its value', () => {\n"
    '    render(<Panel value="seven" />);\n'
    "    expect(screen.getByText('seven')).toBeTruthy();\n"
    "  });\n"
    "});\n"
)
FIRST = dw.Finding(rel=TEST_REL, rule=dw.MISSING_TEST, warnings=())


def test_a_first_test_sits_beside_its_module() -> None:
    assert dw.first_test_path(REL) == TEST_REL
    assert dw.subject_of(TEST_REL) == REL
    for rel in (
        TEST_REL,
        "frontend/src/a/Panel.spec.tsx",
        "frontend/src/a/types.d.ts",
        "frontend/src/a/index.js",
        "frontend/src/a/Panel.stories.jsx",
        "frontend/src/a/styles.css",
    ):
        assert dw.first_test_path(rel) is None, rel


def test_only_modules_with_exports_and_no_test_are_work() -> None:
    texts = {
        REL: BEFORE,
        "frontend/src/a/Tested.jsx": "export const x = 1;\n",
        "frontend/src/a/Tested.spec.jsx": "it('x', () => {});\n",
        "frontend/src/a/OnDisk.ts": "export const y = 2;\n",
        "frontend/src/a/Private.js": "const z = 3;\n",
    }
    on_disk = {"frontend/src/a/OnDisk.test.ts"}
    work = dw.missing_tests(texts, lambda rel: rel in on_disk)
    assert work == [FIRST]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda t: t + "fetch('/api');\n", "reaches outside"),
        (lambda t: t + "const fs = require('fs');\n", "reaches outside"),
        (lambda t: "import fs from 'node:fs';\n" + t, "reaches outside"),
        (lambda t: "import os from 'os';\n" + t, "reaches outside"),
        (lambda t: t + "const k = process.env.KEY;\n", "reaches outside"),
        (lambda t: t + "await import('./Panel');\n", "reaches outside"),
        (lambda t: t + "eval('1');\n", "reaches outside"),
        (lambda t: "// eslint-disable-next-line\n" + t, "silences"),
        (lambda t: t.replace("from './Panel'", "from '../Panel'"), "does not import"),
        (lambda t: t.replace("expect(", "check("), "no test with an expectation"),
        (lambda t: t + "\n" * 200, "lines; the bound"),
    ],
)
def test_the_unattended_checks_refuse(change, reason) -> None:
    verdict = dw.first_test_verdict(FIRST, change(TEST), _result())
    assert not verdict.passed and reason in verdict.reason


def test_a_clean_first_test_passes_and_any_lint_message_refuses() -> None:
    assert dw.first_test_verdict(FIRST, TEST, _result()).passed
    assert not dw.first_test_verdict(
        FIRST, TEST, _result(_warn("no-unused-vars"))
    ).passed


def test_the_reviewers_read_the_module_and_the_whole_test_by_name() -> None:
    prompt = dw.first_test_review_prompt(FIRST, BEFORE, TEST)
    assert "NEW test file" in prompt and BEFORE in prompt and TEST in prompt
    assert "Panel.jsx" in prompt and "Panel.test.jsx" in prompt
    assert "frontend/src" not in prompt, "paths do not leave the machine"


def test_a_batch_writes_a_first_test_and_keeps_its_module_as_the_base(
    tmp_path, monkeypatch
) -> None:
    root = _repo(tmp_path / "project")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(
        tool, "check_texts", lambda r, texts, **kw: {k: _result() for k in texts}
    )
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    systems: list = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            systems.append(system)
            return f"```jsx\n{TEST}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root), budget=5, model="m", region="r", rules=None, dry_run=False
    )
    assert tool.cmd_propose(args) == 0
    [p] = led.proposals()
    assert (p["rel"], p["rule"], p["status"]) == (TEST_REL, dw.MISSING_TEST, "proposed")
    assert p["base_text"] == BEFORE and p["new_text"] == TEST
    assert p["diff"].count("\n+") >= TEST.count("\n") - 1, "the diff is the whole test"
    assert systems == [dw.TESTER_SYSTEM]
    assert led.attempted(TEST_REL, dw.MISSING_TEST, dw.digest(BEFORE))
    evidence = tool.review_evidence(p, FIRST)
    assert "NEW test file" in evidence and TEST.splitlines()[2] in evidence


def test_what_a_new_test_adds_that_may_not_leave_is_hidden_not_refused(
    tmp_path,
) -> None:
    """2026-11-03: three correct new test files by Sonnet and Haiku could not be
    shown to the reviewer, for a relative import, a regex the privacy filter
    took for a path, and a fixed test UUID. The real filters, no stand-ins."""
    added = (
        "import { describe, it, expect, vi } from 'vitest';\n"
        "import { Panel } from './Panel';\n"
        "\n"
        "vi.mock('../superbrain/components/qualityTierContext', () => ({}));\n"
        "const MISSION_UUID = '00000000-0000-4000-8000-000000000001';\n"
        "\n"
        "describe('Panel', () => {\n"
        "  it('shows its value', () => {\n"
        "    expect(MISSION_UUID).toMatch(/last-known/);\n"
        "  });\n"
        "});\n"
    )
    assert tool.would_be_altered(added, ""), "the case itself: the filter alters it"
    led = dw.DailyLedger(tmp_path / "ledger.db")
    led.record_proposal(
        FIRST,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="claude-sonnet-5-5",
        new_text=added,
        verdict=dw.StaticVerdict(True, "ok", 11),
    )
    [p] = led.proposals()
    evidence = tool.review_evidence(p, FIRST)
    # The reviewers are the operator's plans (his decision of 2026-11-11):
    # the local path stays hidden; a fixed test UUID is no key, and is shown.
    assert "qualityTierContext" not in evidence
    assert "00000000-0000-4000-8000-000000000001" in evidence
    assert "GAGOSMASK" in evidence and "something the writer added" in evidence
    assert "describe('Panel'" in evidence, "the rest of the test is shown"
    # Every other route (Bedrock's) still hides both.
    full = tool.egress_redact(added)
    assert "qualityTierContext" not in full
    assert "00000000-0000-4000-8000-000000000001" not in full


@pytest.fixture()
def origin_and_worktree(tmp_path):
    """An origin with the module and GAGOS's worktree cloned from it."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True
    )
    seed = _repo(tmp_path / "seed")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "master")
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(work)],
        check=True,
    )
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    return seed, work


def _accepted_first_test(led):
    pid = led.record_proposal(
        FIRST,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="m",
        new_text=TEST,
        verdict=dw.StaticVerdict(True, "ok", 10),
    )
    _both(led, pid)
    return pid


def test_delivery_creates_the_first_test(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    _seed, work = origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    checked: list = []
    monkeypatch.setattr(
        smoke, "frontend_smoke", lambda root, paths, **kw: checked.append(paths) or None
    )
    pid = _accepted_first_test(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert (work / TEST_REL).read_text(encoding="utf-8") == TEST
    assert (work / REL).read_text(encoding="utf-8") == BEFORE, "the module is untouched"
    assert checked == [[work.resolve() / TEST_REL]] or checked == [[work / TEST_REL]]
    message = _git(work, "log", "-1", "--format=%B")
    assert message.startswith(f"GAGOS: a first test for {REL}") and pid in message


def test_delivery_is_stale_when_the_module_changed(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    seed, work = origin_and_worktree
    (seed / REL).write_bytes((BEFORE + "// changed\n").encode())
    _git(seed, "commit", "-qam", "changed")
    _git(seed, "push", "-q", "origin", "master")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    monkeypatch.setattr(smoke, "frontend_smoke", lambda *a, **kw: None)
    _accepted_first_test(led)
    tool.cmd_deliver(_deliver_args(work))
    assert led.proposals()[0]["status"] == "stale"
    assert not (work / TEST_REL).exists()


def test_a_first_test_that_fails_on_master_is_removed(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    _seed, work = origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    monkeypatch.setattr(smoke, "frontend_smoke", lambda *a, **kw: "vitest failed")
    _accepted_first_test(led)
    tool.cmd_deliver(_deliver_args(work))
    assert led.proposals()[0]["status"] == "failed"
    assert not (work / TEST_REL).exists()
    assert _git(work, "status", "--porcelain") == ""


def test_a_first_test_may_reuse_its_modules_hidden_values_never_invent_one() -> None:
    """Live smoke, 2026-11-02: three of four first tests reused a value the
    module hides, and the whole-file rule refused them as duplicates."""
    token = "GAGOSMASKABCDEF_0000"
    mapping, masked = {token: "hidden"}, f"const url = {token};"
    answer = f"expect(a).toBe({token}); expect(b).toBe({token});"
    with pytest.raises(dw.ProposalRefused, match="duplicates"):
        dw.unmask(answer, mapping, masked=masked)
    assert dw.unmask(answer, mapping, masked=masked, repeat=True) == (
        "expect(a).toBe(hidden); expect(b).toBe(hidden);"
    )
    with pytest.raises(dw.ProposalRefused, match="invents"):
        dw.unmask("GAGOSMASKABCDEF_0001", mapping, masked=masked, repeat=True)
