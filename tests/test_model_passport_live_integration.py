"""Live capability-passport proof (organ 33), run against a real Ollama model.

Organ 33's declared authority_owner is ``ModelPassportAuthority``, and its one
recorded blocker has been "no Ollama -- live local-model / passport
qualification evidence needs live Ollama in CI or self-hosted runner".

Everything that exists for this organ today drives that authority through a
``MagicMock`` or a hand-authored registry row -- ``artifact_digest="abc123"``,
``qualification_evidence_digest="d" * 64``. Those are fabricated strings. They
prove the projection arithmetic and nothing about whether the evidence being
projected was ever earned, which is exactly the gap this file closes.

WHAT MAKES THIS HONEST RATHER THAN JUST GREENER

``passport_for()`` is a pure projection; it never calls a model itself. So
proving it in isolation would prove nothing new. The claim under test is the
whole chain: a REAL model is discovered by ``reconcile()``, a REAL qualification
suite runs against it via ``LocalWorkforceService.qualify()``, and the passport
the authority projects is a faithful readback of THAT run.

Critically, this suite does NOT require the model to pass qualification. A
small CI-sized model may honestly fail -- during development qwen2.5:1.5b
flipped from admitted to revoked between two runs seconds apart, which is real
small-model variance. Demanding a pass would create pressure to pick a model
that flatters the suite, and would turn a genuine failure into a red build.
Both outcomes are asserted instead, because the property that matters is that
the authority never reports an admission the registry did not earn -- and the
failure branch is the one where a projection bug would actually be dangerous.
"""

from __future__ import annotations

import os

import pytest

from aios.application.local_workforce.service import LocalWorkforceService
from aios.application.models.passport_authority import ModelPassportAuthority
from aios.core.llm import OllamaClient
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.memory.db import get_connection, init_memory_db

pytestmark = pytest.mark.skipif(
    os.getenv("AIOS_OLLAMA_INTEGRATION") != "1",
    reason="live local model passport proof (Ollama) is not enabled",
)

_MODEL = os.getenv("AIOS_OLLAMA_MODEL", "qwen2.5:0.5b")

_HEX = set("0123456789abcdef")


@pytest.fixture(scope="module")
def live_client() -> OllamaClient:
    """A client proven to be talking to a real, populated daemon.

    Same guard as tests/test_local_clerk_integration.py, for the same reason:
    ``list_models()`` NEVER raises and collapses to
    ``{"available": False, "models": []}``, which is TRUTHY. A bare
    ``assert client.list_models()`` therefore passes with no Ollama running at
    all, which is precisely how a "live" suite ends up proving nothing.
    """
    client = OllamaClient(model=_MODEL)
    discovery = client.list_models()

    assert discovery.get("available") is True, (
        f"live Ollama did not answer at {client.host}: {discovery}"
    )
    assert discovery.get("models"), (
        f"live Ollama at {client.host} answered but has no models installed"
    )
    return client


@pytest.fixture(scope="module")
def memory_db() -> None:
    """A fresh schema in the session's throwaway data dir.

    tests/conftest.py repoints AIOS_DATA_DIR at a temp directory before
    aios.config derives its paths, so this never touches the operator's real
    data/aios_memory.db -- verified before this suite was written, because a
    live test that reconciles real installed models into the real registry
    would be a genuinely destructive way to prove a point.
    """
    init_memory_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM local_worker_models")
        conn.commit()


@pytest.fixture(scope="module")
def qualified_model(live_client: OllamaClient, memory_db: None) -> tuple[str, dict]:
    """Discover the live model for real, then run the real qualification suite.

    ``reconcile()`` is used rather than seeding a row: the point is that the
    registry row under test was created from a model that genuinely exists on
    the daemon, not one this test invented.
    """
    registry = LocalWorkforceRegistry(live_client)
    registry.reconcile()

    model = registry.get_model(_MODEL)
    assert model is not None, (
        f"reconcile() did not register {_MODEL!r} from the live daemon; "
        f"registered ids: {[m.model_id for m in registry.list_models()]}"
    )

    registry.update_approval(_MODEL, True)
    service = LocalWorkforceService(registry, live_client)
    outcome = service.qualify(_MODEL)

    # qualify() returns status="rejected" for THREE different things: a failed
    # health check, a refused hardware admission, and a genuinely failed
    # qualification suite. Only the last one actually ran a model. Without this
    # guard, a daemon that answered discovery but could not serve the model
    # would short-circuit at the health gate and every assertion below would
    # still pass -- the suite would report "live proof" having never run one
    # case. Only the two post-suite branches carry "qualification".
    assert "qualification" in outcome, (
        f"qualify() returned {outcome.get('status')!r} BEFORE running the "
        f"qualification suite, so nothing was proven about the live model: "
        f"{outcome}"
    )
    assert outcome["qualification"].get("test_results"), (
        "the qualification suite ran but recorded no per-case results"
    )

    return _MODEL, outcome


def test_reconcile_discovers_the_live_model_rather_than_a_seeded_row(
    qualified_model: tuple[str, dict],
) -> None:
    """The row the passport projects came from a real installed model."""
    model_id, _ = qualified_model
    registry = LocalWorkforceRegistry(OllamaClient(model=_MODEL))

    model = registry.get_model(model_id)

    assert model is not None
    assert model.installed is True, "live model should be marked installed"


def test_the_passport_faithfully_projects_a_real_qualification_run(
    qualified_model: tuple[str, dict],
) -> None:
    """Organ 33's authority reports exactly what the live run earned.

    Both branches are asserted. The suite's verdict on a small CI model is
    whatever it honestly is; what must hold either way is that admission is
    never claimed beyond the evidence.
    """
    model_id, outcome = qualified_model
    authority = ModelPassportAuthority(
        LocalWorkforceRegistry(OllamaClient(model=_MODEL))
    )

    passport = authority.passport_for(model_id)

    assert passport is not None, "a registered, qualified model must have a passport"

    digest = passport.passport_digest or ""
    assert len(digest) == 64 and set(digest) <= _HEX, (
        f"expected a real sha256 passport digest, got {digest!r}"
    )

    if outcome["status"] == "admitted":
        assert passport.admission_status == "admitted"
        assert passport.qualification_suite_version, (
            "an admitted passport must name the suite version that admitted it"
        )
        assert passport.last_qualified_at is not None, (
            "an admitted passport must carry when it was qualified"
        )
    else:
        # The dangerous direction, and the one that actually fires on a small
        # model: a failed live run must NOT project as admitted, and must not
        # carry qualification metadata it did not earn. Both fields are
        # asserted null rather than just checking admission_status, because a
        # stale suite_version/timestamp left behind by a failed run is exactly
        # how a revoked model would later read as merely expired.
        assert passport.admission_status != "admitted", (
            f"live qualification returned {outcome['status']!r} but the passport "
            "still projects an admission"
        )
        assert passport.qualification_suite_version is None, (
            "a model that failed qualification must not carry a suite version: "
            f"{passport.qualification_suite_version!r}"
        )
        assert passport.last_qualified_at is None, (
            "a model that failed qualification must not carry a qualified-at "
            f"timestamp: {passport.last_qualified_at!r}"
        )


def test_a_role_the_live_evidence_does_not_back_is_refused(
    qualified_model: tuple[str, dict],
) -> None:
    """Organ 33's actual claim: a profile must be EARNED, never asserted.

    This is not hypothetical. This repo's own live registry once carried
    granite3.2:2b claiming the ``summarise`` profile while every recorded
    qualification run had FAILED summarisation. Validating the vocabulary could
    never have caught that -- ``summarise`` IS a valid profile; the model
    simply had not earned it.

    So the assertion here is the refusal itself, not a subset relation. An
    earlier version of this test asserted ``projected <= backed``, which is
    trivially true while ``qualified_roles`` is empty -- a check that cannot
    fail is worth less than none.
    """
    from aios.application.local_workforce.service import UnsupportedJobProfileClaim
    from aios.domain.local_workforce.contracts import LocalJobProfile

    model_id, _ = qualified_model
    registry = LocalWorkforceRegistry(OllamaClient(model=_MODEL))
    service = LocalWorkforceService(registry, OllamaClient(model=_MODEL))

    every_profile = frozenset(LocalJobProfile)
    unsupported = service.unsupported_profile_claims(model_id, every_profile)
    assert unsupported, (
        "the live evidence appears to back EVERY profile, which would mean the "
        "refusal mechanism is not discriminating -- 9 of 13 profiles have no "
        "suite coverage at all and can never be evidence-backed"
    )

    with pytest.raises(UnsupportedJobProfileClaim):
        service.update_profiles(model_id, sorted(p.value for p in every_profile))

    # The refusal must also have left no trace: nothing partially granted.
    passport = ModelPassportAuthority(registry).passport_for(model_id)
    assert passport is not None
    projected = {LocalJobProfile(role) for role in passport.qualified_roles}
    assert projected <= (every_profile - unsupported), (
        f"passport projects roles the live evidence does not back: "
        f"{projected - (every_profile - unsupported)}"
    )


def test_an_unregistered_model_has_no_passport(memory_db: None) -> None:
    """None means "no record", which callers must treat as not-admitted.

    A proposed-but-empty passport would read as merely awaiting qualification,
    which is a materially different and more permissive claim.
    """
    registry = LocalWorkforceRegistry(OllamaClient(model=_MODEL))
    authority = ModelPassportAuthority(registry)

    assert authority.passport_for("model-that-was-never-installed:0b") is None
