"""GAGOS's hour activates its review-ready skills inside the operator's standing
skill envelope (2026-11-18), and never without one, nor unsigned.

Real skill repository, real envelope authority with its own stop; only the
signing and the keystore stand in.
"""

from __future__ import annotations

from tests.test_gagos_skill_envelope import Who, _authority, _skill, _terms

from aios.application.learning.service import LearningService
from aios.domain.learning.repository import SkillRepository
from tools import gagos_daily as tool


class Service:
    """The learning service's skill path over a real repository."""

    def __init__(self, repository: SkillRepository) -> None:
        self.skill_repository = repository

    def _assert_operational(self) -> None:
        return None

    def activate_skill_within_envelope(self, *args, **kwargs):
        return LearningService.activate_skill_within_envelope(self, *args, **kwargs)


class Keys:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def get(self, name: str) -> str | None:
        return self.value


def _world(tmp_path, *skills):
    repository = SkillRepository(tmp_path / "learn.db")
    for skill in skills:
        repository.save(skill)
    return repository, Service(repository)


def test_without_a_skill_envelope_nothing_is_activated(tmp_path) -> None:
    repository, service = _world(tmp_path, _skill("arc-ready"))
    said = tool.skills_hour(
        authority=_authority(tmp_path), service=service, attest=lambda *a, **k: True
    )
    assert said == ["none activated -- the operator has not signed a skill envelope"]
    assert repository.get("arc-ready", 1).state == "candidate"


def test_only_review_ready_candidates_are_activated_and_signed(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AIOS_LEARNING_KEY_LIVE", "test-key")
    repository, service = _world(
        tmp_path, _skill("arc-ready"), _skill("arc-young", ready=False)
    )
    authority = _authority(tmp_path)
    authority.sign(_terms(max_activations=5), principal=Who())
    signed = []
    said = tool.skills_hour(
        authority=authority,
        service=service,
        attest=lambda skill_id, version, approver: (
            signed.append((skill_id, approver)) or True
        ),
    )
    assert repository.get("arc-ready", 1).state == "active"
    assert repository.get("arc-young", 1).state == "candidate"
    assert signed == [("arc-ready", "operator-1")]
    assert len(said) == 1 and said[0].startswith(
        "arc-ready@1 activated -- Activated within"
    )
    assert said[0].endswith("; signed")


def test_without_the_signing_key_no_skill_is_activated(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AIOS_LEARNING_KEY_LIVE", raising=False)
    repository, service = _world(tmp_path, _skill("arc-ready"))
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    said = tool.skills_hour(
        authority=authority,
        service=service,
        attest=lambda *a, **k: True,
        store=Keys(None),
    )
    assert "an unsigned skill is inert" in said[0]
    assert repository.get("arc-ready", 1).state == "candidate"
    assert authority.status()["activationsUsed"] == 0


def test_an_unsigned_activation_is_said_as_inert(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_LEARNING_KEY_LIVE", "test-key")
    _repository, service = _world(tmp_path, _skill("arc-ready"))
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    said = tool.skills_hour(
        authority=authority, service=service, attest=lambda *a, **k: False
    )
    assert said[0].endswith("NOT signed, so inert until signed")


def test_a_full_envelope_stops_the_hour(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_LEARNING_KEY_LIVE", "test-key")
    repository, service = _world(
        tmp_path, _skill("arc-a"), _skill("arc-b"), _skill("arc-c")
    )
    authority = _authority(tmp_path)
    authority.sign(_terms(max_activations=1), principal=Who())
    said = tool.skills_hour(
        authority=authority, service=service, attest=lambda *a, **k: True
    )
    active = [
        s for s in ("arc-a", "arc-b", "arc-c") if repository.get(s, 1).state == "active"
    ]
    assert len(active) == 1
    assert "1 activations are used" in said[-1]
    assert len(said) == 2, said


def test_no_ready_skill_is_said() -> None:
    class Empty:
        skill_repository = type("R", (), {"list_skills": lambda self: []})()

    class Live:
        def status(self):
            return {"live": True}

    assert tool.skills_hour(
        authority=Live(), service=Empty(), attest=lambda *a, **k: True
    ) == ["no review-ready skill awaits activation"]
