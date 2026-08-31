"""The frozen-core rule is enforced at the merge boundary, not just in-process.

Inventory item 5. `AGENTS.md` §VIII declares `aios/security/` frozen, and until
`scripts/check_frozen_core.py` existed that rule had exactly two enforcers --
`ConstitutionEnforcer.check_file_edit` and `SelfAnalysisAgent.classify_target` --
both *in-process*. A commit authored any other way met no automated resistance:
an agent editing files directly, a human in a hurry, or a future self-improvement
loop opening its own PR. The catalog names this as the precondition for enabling
any loop with PR-write access.

These tests drive the real script against real git history in a real temporary
repository. Nothing here inspects a data structure the test itself built.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_frozen_core.py"


def test_the_gate_runs_in_ci() -> None:
    """A gate nobody invokes is a claim.

    This repo has now shipped four checks that existed and never ran. The rule
    lives here so removing the invocation fails review rather than silently
    reopening the frozen core.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python scripts/check_frozen_core.py" in workflow, (
        "the frozen-core gate is no longer invoked by ci.yml -- aios/security/ "
        "is back to being guarded only by in-process checks"
    )


def test_the_gate_reads_the_same_constant_the_runtime_enforces() -> None:
    """One derivation, two callers.

    Two independently-maintained answers to "is this path frozen?" is the exact
    shape that produced two containment escapes in this repo. A gate that
    disagrees with the runtime is worse than no gate: it certifies the wrong
    thing. Asserted by identity, not by comparing two copies of a list.
    """
    from aios.policy.constitution import FROZEN_PATH_PREFIXES

    import importlib.util

    spec = importlib.util.spec_from_file_location("_frozen_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.FROZEN_PATH_PREFIXES is FROZEN_PATH_PREFIXES, (
        "the gate has grown its own copy of the frozen-path list; it must import "
        "aios.policy.constitution.FROZEN_PATH_PREFIXES so the gate and the "
        "runtime enforcer can never disagree"
    )


def test_the_prefix_match_does_not_catch_a_sibling_name() -> None:
    """`aios/security_notes.py` is not inside `aios/security/`.

    A naive `startswith(prefix)` on the un-stripped prefix would be correct here
    by luck, but `startswith("aios/security")` would not. Pinned because the
    over-broad version fails closed on innocent files, which creates pressure to
    weaken the gate.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_frozen_gate2", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.is_frozen("aios/security/gateway.py") is True
    assert module.is_frozen("aios/security") is True
    assert module.is_frozen("aios/security_notes.py") is False
    assert module.is_frozen("aios/policy/constitution.py") is False


# --------------------------------------------------------------------------- #
# End-to-end: a real repo, real commits, the real script
# --------------------------------------------------------------------------- #
def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A tiny repo with a `master` to diff against and the real script vendored."""
    root = tmp_path / "repo"
    (root / "aios" / "security").mkdir(parents=True)
    (root / "aios" / "policy").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)

    # The real constant, so the vendored script resolves exactly as in production.
    (root / "aios" / "__init__.py").write_text("", encoding="utf-8")
    (root / "aios" / "policy" / "__init__.py").write_text("", encoding="utf-8")
    (root / "aios" / "policy" / "constitution.py").write_text(
        'FROZEN_PATH_PREFIXES: tuple[str, ...] = ("aios/security/",)\n',
        encoding="utf-8",
    )
    (root / "aios" / "security" / "__init__.py").write_text("", encoding="utf-8")
    (root / "aios" / "security" / "gateway.py").write_text(
        "SPINE = 1\n", encoding="utf-8"
    )
    (root / "scripts" / "check_frozen_core.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "readme.md").write_text("ordinary file\n", encoding="utf-8")

    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "work")
    return root


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_frozen_core.py", "--base", "master"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_an_ordinary_change_passes(repo: Path) -> None:
    (repo / "readme.md").write_text("edited\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "ordinary change")

    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no frozen path touched" in result.stdout


def test_touching_the_frozen_core_fails(repo: Path) -> None:
    """The whole point: this must go red."""
    (repo / "aios" / "security" / "gateway.py").write_text(
        "SPINE = 2\n", encoding="utf-8"
    )
    _git(repo, "commit", "-qam", "edit the spine")

    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "aios/security/gateway.py" in result.stderr
    assert "FROZEN" in result.stderr


def test_a_section_viii_record_in_the_same_diff_authorizes_it(repo: Path) -> None:
    """The §VIII escape hatch works, and leaves an artifact behind.

    This is a tripwire that forces ceremony, not an authorization system -- the
    real authority is the human who merges. What it guarantees is that the change
    cannot be quiet.
    """
    (repo / "aios" / "security" / "gateway.py").write_text(
        "SPINE = 2\n", encoding="utf-8"
    )
    record_dir = repo / "release" / "section-viii"
    record_dir.mkdir(parents=True)
    (record_dir / "2026-08-31-spine-fix.md").write_text(
        "# §VIII record\n\nAuthorizes: aios/security/gateway.py\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "section VIII change with record")

    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "authorized by release/section-viii/2026-08-31-spine-fix.md" in result.stdout


def test_a_record_that_does_not_name_the_path_does_not_authorize_it(
    repo: Path,
) -> None:
    """A record is not a blanket permit.

    A §VIII record naming one file must not wave through a second file edited in
    the same diff -- otherwise one approved change becomes cover for anything
    bundled alongside it.
    """
    (repo / "aios" / "security" / "gateway.py").write_text(
        "SPINE = 2\n", encoding="utf-8"
    )
    (repo / "aios" / "security" / "scope_lock.py").write_text(
        "ROOTS = ()\n", encoding="utf-8"
    )
    record_dir = repo / "release" / "section-viii"
    record_dir.mkdir(parents=True)
    (record_dir / "record.md").write_text(
        "Authorizes: aios/security/gateway.py\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "two spine files, one record")

    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "aios/security/scope_lock.py" in result.stderr
    assert "aios/security/gateway.py" not in result.stderr.split("FAILED")[-1].split(
        "\n\nAGENTS.md"
    )[0]


def test_a_stale_record_from_an_earlier_commit_does_not_authorize(repo: Path) -> None:
    """Ceremony must be per-change, not once-forever.

    A record merged months ago must not keep authorizing spine edits. The record
    has to appear in THIS diff, or one approved change silently becomes a
    standing permission -- the opposite of §VIII.
    """
    # Land the record on master FIRST, so it is not part of the branch diff.
    _git(repo, "checkout", "-q", "master")
    record_dir = repo / "release" / "section-viii"
    record_dir.mkdir(parents=True)
    (record_dir / "old.md").write_text(
        "Authorizes: aios/security/gateway.py\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "historic record")
    _git(repo, "checkout", "-q", "work")
    _git(repo, "merge", "-q", "master", "-m", "sync")

    (repo / "aios" / "security" / "gateway.py").write_text(
        "SPINE = 3\n", encoding="utf-8"
    )
    _git(repo, "commit", "-qam", "spine edit leaning on an old record")

    result = _run(repo)
    assert result.returncode == 1, (
        "a record that predates this diff authorized a frozen-core edit; §VIII "
        "ceremony must be per-change\n" + result.stdout + result.stderr
    )
