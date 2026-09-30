"""Fresh proof uses actual production authorities, never an arbitrary tip."""

import subprocess
import json

import pytest

from scripts import phase4_boundary_skill_evidence as runner


def test_tip_rejects_backend_edits_but_not_frontend_work(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    (tmp_path / "aios").mkdir()
    backend = tmp_path / "aios" / "authority.py"
    backend.write_text("# original\n")
    git("add", "aios")
    git(
        "-c",
        "user.name=Evidence test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    tip = git("rev-parse", "HEAD")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "new.ts").write_text("// isolated UI work\n")
    assert runner.backend_tip(tmp_path) == tip
    backend.write_text("# changed\n")
    with pytest.raises(RuntimeError, match="backend"):
        runner.backend_tip(tmp_path)


def test_boundary_probe_executes_real_controller_and_checks_refusal(
    tmp_path, monkeypatch
):
    from aios.application.capabilities.authority import EmergencyStopHardWiringAuthority

    assert "refused" in runner.probe_boundary(tmp_path)
    assert (tmp_path / "estop26.db").stat().st_size > 0
    monkeypatch.setattr(
        EmergencyStopHardWiringAuthority, "assert_operational", lambda *a, **k: None
    )
    with pytest.raises(RuntimeError, match="accepted"):
        runner.probe_boundary(tmp_path)


def test_skill_probe_reopens_durable_state_and_checks_birth_refusal(
    tmp_path, monkeypatch
):
    from aios.domain.learning.repository import SkillRepository

    assert "success_count=1" in runner.probe_skill(tmp_path)
    assert (tmp_path / "skills43.db").stat().st_size > 0
    monkeypatch.setattr(SkillRepository, "save", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="active"):
        runner.probe_skill(tmp_path / "negative")


def test_report_uses_existing_c10_artifact_contract_and_cannot_overwrite(
    tmp_path, monkeypatch
):
    from scripts.verify_organ_twelve_conditions import _PHASE4_ARTIFACT_RE

    tip = "a" * 40
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "backend_tip", lambda root: tip)
    monkeypatch.setattr(runner, "probe_boundary", lambda scratch: "boundary fixture")
    monkeypatch.setattr(runner, "probe_skill", lambda scratch: "skill fixture")
    assert runner.main() == 0
    artifact = next((tmp_path / "release" / "phase4").glob("*.json"))
    original = artifact.read_bytes()
    report = json.loads(original)
    citation = artifact.relative_to(tmp_path).as_posix()
    assert _PHASE4_ARTIFACT_RE.findall(citation) == [citation]
    assert report["tip_sha"] == tip
    assert {p["organ_id"] for p in report["proofs"]} == {26, 43}
    with pytest.raises(RuntimeError, match="preserve"):
        runner.main()
    assert artifact.read_bytes() == original


def test_failed_probe_cannot_produce_a_passed_report(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "backend_tip", lambda root: "b" * 40)
    monkeypatch.setattr(runner, "probe_boundary", lambda scratch: "boundary fixture")

    def failed_probe(scratch):
        raise RuntimeError("probe refused")

    monkeypatch.setattr(runner, "probe_skill", failed_probe)
    assert runner.main() == 1
    report = json.loads(
        next((tmp_path / "release" / "phase4").glob("*.json")).read_bytes()
    )
    assert report["all_passed"] is False
    assert report["proofs"][1]["passed"] is False
