"""Plan Phase 9: the lineage tool and C10 answer "is this row bound to its
commit?" with ONE function, so the tool cannot produce a row C10 refuses.

`scripts/verify_evidence_lineage.py --update` re-points a squash-orphaned sha
to an ancestor carrying byte-identical entrypoints. For a live-evidence row
that cites a `release/phase4` artifact or a CI run, that is wrong: C10 checks
the artifact's `tip_sha` (and the run's commit) against the row's commit, so a
moved row fails C10 -- observed in #368, which re-gathered instead. Until now
the only guard was a sentence in phase4_attach_ledger.py's refusal message.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_evidence_lineage as lineage
from scripts import verify_organ_twelve_conditions as gate
from tests.source_rules import executable_source

ARTIFACT = "release/phase4/live-evidence-0123456789ab.json"


def _git(root: Path, *args: str, when: str | None = None) -> str:
    env = dict(os.environ)
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=lineage-test",
            "-c",
            "user.email=lineage@test.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def _commit(root: Path, files: dict[str, str], message: str, when: str) -> str:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", message, when=when)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def squashed(tmp_path: Path, monkeypatch) -> dict:
    """A branch commit orphaned by a squash that carried identical content."""
    _git(tmp_path, "init", "-q", "-b", "main")
    base = _commit(tmp_path, {"a.py": "x = 1\n"}, "base", "2026-10-01T10:00:00")
    _git(tmp_path, "checkout", "-q", "-b", "evidence-branch")
    orphan = _commit(
        tmp_path, {"a.py": "x = 2\n"}, "verified here", "2026-10-02T10:00:00"
    )
    _git(tmp_path, "checkout", "-q", "main")
    squash = _commit(
        tmp_path, {"a.py": "x = 2\n"}, "squash of the branch", "2026-10-03T10:00:00"
    )
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(lineage, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lineage, "LEDGER", ledger)
    return {
        "root": tmp_path,
        "ledger": ledger,
        "base": base,
        "orphan": orphan,
        "squash": squash,
    }


def _row(organ_id: int, attested: str, evidence_sha: str, description: str) -> dict:
    return {
        "organ_id": organ_id,
        "last_verified_sha": attested,
        "production_entrypoints": ["a.py"],
        "live_evidence": [
            {
                "commit_sha": evidence_sha,
                "proof_level": "live",
                "description": description,
            }
        ],
        "condition_verdicts": {},
    }


def _run(world: dict, rows: list[dict], monkeypatch, *, update: bool) -> list[dict]:
    world["ledger"].write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["verify_evidence_lineage.py", *(["--update"] if update else [])]
    )
    lineage.main()
    return json.loads(world["ledger"].read_text(encoding="utf-8"))


def test_a_row_proven_at_the_orphan_is_refused_and_left_alone(
    squashed, monkeypatch, capsys
) -> None:
    rows = [
        _row(
            30,
            squashed["squash"],
            squashed["orphan"],
            f"gathered by {ARTIFACT} at the branch tip",
        )
    ]
    after = _run(squashed, rows, monkeypatch, update=True)

    assert after[0]["live_evidence"][0]["commit_sha"] == squashed["orphan"]
    out = capsys.readouterr().out
    assert "re-gather at a current commit" in out
    assert ARTIFACT in out


def test_a_ci_run_citation_is_bound_too(squashed, monkeypatch, capsys) -> None:
    rows = [
        _row(
            31,
            squashed["squash"],
            squashed["orphan"],
            "https://github.com/o/r/actions/runs/123456 passed",
        )
    ]
    after = _run(squashed, rows, monkeypatch, update=True)

    assert after[0]["live_evidence"][0]["commit_sha"] == squashed["orphan"]
    assert "actions/runs/123456" in capsys.readouterr().out


def test_a_row_citing_no_commit_bound_proof_is_still_repointed(
    squashed, monkeypatch
) -> None:
    """The control: the tool still does its job where C10 has nothing to bind."""
    rows = [
        _row(
            32,
            squashed["squash"],
            squashed["orphan"],
            "tests/test_a.py::test_x ran and passed in this gate run",
        )
    ]
    after = _run(squashed, rows, monkeypatch, update=True)

    assert after[0]["live_evidence"][0]["commit_sha"] == squashed["squash"]


def test_c10_reads_its_citations_through_the_shared_function() -> None:
    src = executable_source(gate._evidence_reference_failures)
    assert "commit_bound_citations(desc)" in src
    assert "_PHASE4_ARTIFACT_RE.findall" not in src
    assert "_CI_RUN_RE.findall" not in src


def test_the_shared_function_finds_both_kinds() -> None:
    artifacts, runs = gate.commit_bound_citations(
        f"see {ARTIFACT} and https://github.com/o/r/actions/runs/42"
    )
    assert artifacts == [ARTIFACT] and runs == ["42"]
    assert gate.commit_bound_citations("tests/test_a.py::test_x") == ([], [])
