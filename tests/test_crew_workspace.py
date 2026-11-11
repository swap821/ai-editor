"""A crew agent's masked copy of the project (2026-11-11, "Files + sandboxed
tests"): what it holds, what it leaves out, and how its changes come back."""

from __future__ import annotations

import subprocess

import pytest

from aios.maintenance import crew_workspace as cw
from aios.maintenance.daily_work import ProposalRefused

SECRET = "sk-live-0123456789abcdef"


def _redact(text: str) -> str:
    # A stand-in scrubber: what the egress filters would replace.
    return text.replace(SECRET, "[REDACTED]")


def _git(root, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    files = {
        "frontend/src/a.ts": "export const a = 1;\n",
        "frontend/src/keys.ts": f"export const key = '{SECRET}';\nexport const b = 2;\n",
        "frontend/src/logo.png": None,
        "aios/other.py": "x = 1\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            (root / rel).write_bytes(b"\x89PNG\x00\x01")
        else:
            (root / rel).write_bytes(text.encode())
    (root / "frontend/src/untracked.ts").write_bytes(("export const u = 1;\n").encode())
    _git(
        root,
        "add",
        "frontend/src/a.ts",
        "frontend/src/keys.ts",
        "frontend/src/logo.png",
        "aios/other.py",
    )
    _git(root, "commit", "-qm", "base")
    return root, _git(root, "rev-parse", "HEAD")


def test_the_copy_holds_tracked_files_under_its_scope_masked(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    assert sorted(ws.shown) == ["frontend/src/a.ts", "frontend/src/keys.ts"]
    assert ws.left_out == {"frontend/src/logo.png": "not text"}
    assert not (tmp_path / "ws/frontend/src/untracked.ts").exists(), (
        "never the checkout"
    )
    assert not (tmp_path / "ws/aios").exists(), "only the scope"
    shown = (tmp_path / "ws/frontend/src/keys.ts").read_text()
    assert SECRET not in shown and "GAGOSMASKQ_0000" in shown
    assert _redact(shown) == shown


def test_changes_and_new_and_deleted_files_come_back_restored(
    project, tmp_path
) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    keys = tmp_path / "ws/frontend/src/keys.ts"
    masked = keys.read_text()
    # The agent splits keys.ts: the key moves into a new file, a.ts goes.
    line = masked.splitlines()[0] + "\n"
    keys.write_bytes((masked.replace(line, "")).encode())
    (tmp_path / "ws/frontend/src/key.ts").write_bytes((line).encode())
    (tmp_path / "ws/frontend/src/a.ts").unlink()
    got = cw.restore(ws, cw.changes(ws))
    assert got == {
        "frontend/src/keys.ts": "export const b = 2;\n",
        "frontend/src/key.ts": f"export const key = '{SECRET}';\n",
        "frontend/src/a.ts": None,
    }


def test_an_invented_placeholder_is_refused(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    (tmp_path / "ws/frontend/src/a.ts").write_text(
        "export const a = 'GAGOSMASKQ_0999';\n"
    )
    with pytest.raises(ProposalRefused, match="invents"):
        cw.restore(ws, cw.changes(ws))


def test_writing_a_file_it_was_not_shown_is_refused(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    (tmp_path / "ws/frontend/src/logo.png").write_bytes(("not a png any more").encode())
    with pytest.raises(ProposalRefused, match="not shown"):
        cw.changes(ws)


def test_an_unchanged_copy_reports_nothing(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    assert cw.changes(ws) == {}


def test_the_copy_must_start_empty(project, tmp_path) -> None:
    root, base = project
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws/stray.txt").write_bytes(("x").encode())
    with pytest.raises(ValueError, match="not empty"):
        cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
