"""The operator refreshes the frozen spine's evidence himself, then re-signs.

`phase4_attach_ledger.py` never touches a spine-attested organ: its evidence is
covered by the operator's signature, so an agent edit silently breaks it. That
left no tool at all for the step the verifier asks for when a spine organ goes
stale ("re-run the evidence and spine_release_attest.py at a current commit").
`--operator-spine` is that step, and only that step: spine organs only, a real
terminal, a typed `approve`, evidence on master -- the same shape as `sign`.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_phase4_attach_ledger", REPO_ROOT / "scripts" / "phase4_attach_ledger.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def world(tmp_path, monkeypatch):
    head = subprocess.run(
        ["git", "rev-parse", "origin/master"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        pytest.skip("no origin/master ref in this clone")
    tip = head.stdout.strip()
    attach = _load()
    ledger = tmp_path / "ledger.json"
    rows = [
        {
            "organ_id": oid,
            "status": "green",
            "live_evidence": [],
            "last_verified_sha": "0" * 40,
            "known_blockers": [],
            "production_entrypoints": [],
        }
        for oid in (2, 14)
    ]
    ledger.write_text(json.dumps(rows), encoding="utf-8")
    attestation = tmp_path / "attestation.json"
    attestation.write_text(json.dumps({"organ_ids": [1, 2, 3, 4, 5]}), encoding="utf-8")
    monkeypatch.setattr(attach, "LEDGER_PATH", ledger)
    monkeypatch.setattr(attach, "ATTESTATION_PATH", attestation)
    # The tool records a repo-relative artifact path, so the artifact lives in
    # the repo for the duration of the test.
    artifact = (
        REPO_ROOT / "release" / "phase4" / f".operator-spine-{uuid.uuid4().hex}.json"
    )
    artifact.write_text(
        json.dumps(
            {
                "all_passed": True,
                "tip_sha": tip,
                "command": "python scripts/phase4_live_evidence.py",
                "proofs": [
                    {
                        "organ_id": oid,
                        "passed": True,
                        "command": "probe",
                        "evidence": "ok",
                    }
                    for oid in (2, 14)
                ],
            }
        ),
        encoding="utf-8",
    )
    yield attach, ledger, artifact, tip
    artifact.unlink(missing_ok=True)


def _rows(ledger: Path) -> dict[int, dict]:
    return {r["organ_id"]: r for r in json.loads(ledger.read_text(encoding="utf-8"))}


def _answer(monkeypatch, reply: str) -> list[str]:
    asked: list[str] = []

    def fake_input(prompt: str = "") -> str:
        asked.append(prompt)
        return reply

    monkeypatch.setattr(builtins, "input", fake_input)
    return asked


def test_the_default_mode_still_never_touches_a_spine_organ(world) -> None:
    attach, ledger, artifact, tip = world
    assert attach.main(["--artifact", str(artifact)]) == 0
    rows = _rows(ledger)
    assert rows[2]["last_verified_sha"] == "0" * 40 and rows[2]["live_evidence"] == []
    assert rows[14]["last_verified_sha"] == tip


def test_operator_spine_refuses_without_a_terminal(world, monkeypatch) -> None:
    attach, ledger, artifact, _tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: False)
    before = ledger.read_text(encoding="utf-8")
    assert attach.main(["--artifact", str(artifact), "--operator-spine"]) == 2
    assert ledger.read_text(encoding="utf-8") == before


def test_approve_writes_the_spine_organ_and_nothing_else(world, monkeypatch) -> None:
    attach, ledger, artifact, tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: True)
    asked = _answer(monkeypatch, "approve")
    assert attach.main(["--artifact", str(artifact), "--operator-spine"]) == 0
    assert len(asked) == 1, "the operator was not asked"
    rows = _rows(ledger)
    assert rows[2]["last_verified_sha"] == tip
    assert [e["commit_sha"] for e in rows[2]["live_evidence"]] == [tip]
    assert rows[14]["last_verified_sha"] == "0" * 40, "a non-spine organ was touched"


@pytest.mark.parametrize("reply", ["", "yes", "APPROVE", "approve it"])
def test_anything_but_approve_writes_nothing(world, monkeypatch, reply) -> None:
    attach, ledger, artifact, _tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: True)
    _answer(monkeypatch, reply)
    before = ledger.read_text(encoding="utf-8")
    assert attach.main(["--artifact", str(artifact), "--operator-spine"]) == 1
    assert ledger.read_text(encoding="utf-8") == before


def test_organs_narrows_the_refresh(world, monkeypatch) -> None:
    """Organ 3 is selected but has no proof here; organ 2 has one but is not
    selected -- so nothing qualifies and nothing is written."""
    attach, ledger, artifact, _tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: True)
    asked = _answer(monkeypatch, "approve")
    before = ledger.read_text(encoding="utf-8")
    assert (
        attach.main(["--artifact", str(artifact), "--operator-spine", "--organs", "3"])
        == 1
    )
    assert ledger.read_text(encoding="utf-8") == before
    assert asked == [], "asked to approve a refresh that would write nothing"


def test_organs_without_operator_spine_is_refused(world) -> None:
    attach, _ledger, artifact, _tip = world
    assert attach.main(["--artifact", str(artifact), "--organs", "2"]) == 2


def test_operator_spine_refuses_branch_tip_evidence(world, monkeypatch) -> None:
    """The signature must name a commit reachable from master."""
    attach, ledger, artifact, _tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: True)
    before = ledger.read_text(encoding="utf-8")
    assert (
        attach.main(
            ["--artifact", str(artifact), "--operator-spine", "--allow-branch-tip"]
        )
        == 2
    )
    assert ledger.read_text(encoding="utf-8") == before


def test_a_dry_run_needs_no_terminal_and_writes_nothing(world, monkeypatch) -> None:
    attach, ledger, artifact, _tip = world
    monkeypatch.setattr(attach, "_interactive", lambda: False)
    asked = _answer(monkeypatch, "approve")
    before = ledger.read_text(encoding="utf-8")
    assert (
        attach.main(["--artifact", str(artifact), "--operator-spine", "--dry-run"]) == 0
    )
    assert ledger.read_text(encoding="utf-8") == before
    assert asked == []


def test_the_terminal_check_reads_both_streams(monkeypatch) -> None:
    """Captured stdout OR stdin means an agent is likely driving it."""
    attach = _load()
    monkeypatch.delenv(attach._ALLOW_NONTTY_ENV, raising=False)

    class Stream:
        def __init__(self, tty: bool) -> None:
            self._tty = tty

        def isatty(self) -> bool:
            return self._tty

    for stdin_tty, stdout_tty in ((True, False), (False, True), (False, False)):
        monkeypatch.setattr(attach.sys, "stdin", Stream(stdin_tty))
        monkeypatch.setattr(attach.sys, "stdout", Stream(stdout_tty))
        assert not attach._interactive(), (stdin_tty, stdout_tty)
    monkeypatch.setattr(attach.sys, "stdin", Stream(True))
    monkeypatch.setattr(attach.sys, "stdout", Stream(True))
    assert attach._interactive()


def test_one_test_escape_shared_with_sign() -> None:
    attach = _load()
    sign_source = (REPO_ROOT / "scripts" / "spine_release_attest.py").read_text(
        encoding="utf-8"
    )
    assert attach._ALLOW_NONTTY_ENV == "AIOS_SPINE_RELEASE_ALLOW_NONTTY"
    assert attach._ALLOW_NONTTY_ENV in sign_source
