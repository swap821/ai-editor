"""Plan Phase 8: the learning loop's four organs (56-59), on the live path.

Operator decision 2026-10-05: the learning loop is governed by the organ
ledger, as four organs -- Learning Integrity and Provenance (56), Reflex
Authority (57), Recall Isolation (58), Learning Freeze (59). F1, the finding
the plan opened with, was a governed stack that the live turn never ran, so
each organ's C2 proof here drives the PROCESS authority (the one
`aios/application/memory/bootstrap.py` builds and every live turn uses) or the
real route's wiring -- a class that works in isolation would not pass. The
restart (C3) and fail-safe (C5) proofs the ledger cites that no older suite
already held are here too.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
from aios.core.verification_strength import VerificationStrength
from aios.memory import learning_freeze
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore

ALICE, BOB = "principal:organ-alice", "principal:organ-bob"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def own_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    return tmp_path


def _probe_text(marker: str) -> str:
    return f"when the {marker} build breaks, rerun the {marker} migration first"


def _probe_marker() -> str:
    """A unique word for one probe lesson that the secret scanner leaves alone.

    The lesson is recalled BY this word, and every lesson write is scrubbed. A
    random hex suffix reads as a HIGH_ENTROPY secret about 1.8% of the time
    (356 of 20,000, measured 2026-10-05), and a redacted marker is never
    recalled: organ 58's live-recall test failed on one in CI, on a commit
    whose other run was green. So draw until the scrubbed text is the text.
    """
    from aios.security.secret_scanner import scan_and_redact

    while True:
        marker = f"organprobe{uuid4().hex[:10]}"
        if scan_and_redact(_probe_text(marker)).scrubbed == _probe_text(marker):
            return marker


def _live_lesson(principal: str) -> tuple[object, int, str]:
    """A verified lesson written through the PROCESS authority's adapter."""
    from aios.api.deps import get_memory_authority
    from aios.memory.db import init_memory_db

    init_memory_db()  # what the app's startup does (aios/api/main.py)
    lessons = get_memory_authority().adapters["lessons"]
    marker = _probe_marker()
    text = _probe_text(marker)
    mistake_id = lessons.record(
        f"task-{marker}",
        "organ_probe",
        "the migration was skipped",
        "ran the migration",
        text,
        0.1,
        principal=principal,
    )
    lessons.promote(
        mistake_id, principal=principal, strength=VerificationStrength.STRONG
    )
    return lessons, int(mistake_id), marker


# ------------------------------------------- 56 Learning Integrity and Provenance


def test_organ_56_the_live_authority_signs_learning_through_its_writers() -> None:
    """C2. Lessons, semantic memory and facts share ONE ProvenanceWriter over
    the memory database; the skill library has its own over the operational
    database; both sign with the process's one signer, as LIVE rows. A lesson
    written and promoted through the live adapter ends on a SIGNED record
    (``latest`` is None whenever the newest record is unsigned)."""
    from aios.api.deps import get_memory_authority

    adapters = get_memory_authority().adapters
    memory_writers = {adapters[n].provenance for n in ("lessons", "semantic", "facts")}
    assert len(memory_writers) == 1
    (writer,) = memory_writers
    skills_writer = adapters["skills"].provenance
    assert isinstance(writer, ProvenanceWriter)
    assert isinstance(skills_writer, ProvenanceWriter)
    assert skills_writer is not writer
    assert skills_writer.signer is writer.signer
    assert writer.source_kind == skills_writer.source_kind == "live"

    lessons, mistake_id, _ = _live_lesson(ALICE)
    assert lessons.provenance is writer
    signed = writer.store.latest("mistake_pool", str(mistake_id))
    assert signed is not None, "the live write ended on an unsigned record"
    assert signed.provenance.principal == ALICE


def test_organ_56_a_signed_record_still_verifies_after_the_store_is_reopened(
    tmp_path, own_latch
) -> None:
    """C3. The append-only provenance store is durable: a record signed by one
    process verifies, unchanged, through a store a later process opens."""
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    db = tmp_path / "provenance.sqlite"
    writer = ProvenanceWriter(
        ProvenanceStore(db), signer, source_kind="live", verifier=verifier
    )
    writer.attest_new("mistake_pool", 7, "a" * 64, "created", principal=ALICE)

    reopened = ProvenanceStore(db).latest("mistake_pool", "7")
    assert reopened is not None
    assert verifier.verify(reopened, content_sha256="a" * 64, context="live").admitted
    refused = verifier.verify(reopened, content_sha256="b" * 64, context="live")
    assert not refused.admitted, "a changed row never verifies on the old record"


# ------------------------------------------------------------ 57 Reflex Authority


def _reflex_world(root: Path):
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )
    from aios.core.cerebellum import Cerebellum
    from aios.domain.learning.repository import SkillRepository
    from aios.memory.db import init_memory_db

    memory = root / "memory.sqlite"
    operational = root / "operational.sqlite"
    init_memory_db(memory)

    def library():
        return InstitutionalSkillAdapter(
            SkillRepository(operational), SkillTrailIndex(operational)
        )

    def cerebellum(lib):
        c = Cerebellum(memory)
        c.attach_reflex_gate(lib)
        return c

    return library, cerebellum


GOAL = "show the organ notes"
STEPS = ["read_file: filepath=README.md"]


def test_organ_57_the_live_turn_matches_through_the_authoritys_cerebellum() -> None:
    """C2. `/api/generate` resolves `get_cerebellum`, which is the ONE
    cerebellum the process authority owns, and its reflexes come only from the
    authority's skill library."""
    from aios.api.deps import get_cerebellum, get_memory_authority
    from aios.api.main import app

    adapters = get_memory_authority().adapters
    cerebellum = get_cerebellum()
    assert cerebellum is adapters["cerebellum"].store
    assert cerebellum._reflex_gate is adapters["skills"]
    generate = [r for r in app.routes if getattr(r, "path", "") == "/api/generate"]
    assert generate, "the live turn route exists"
    calls = {d.call for r in generate for d in r.dependant.dependencies}
    assert get_cerebellum in calls


def test_organ_57_a_retired_reflex_stays_retired_for_a_new_process(
    tmp_path, own_latch
) -> None:
    """C3. Compiled reflexes and their retirement are durable: a new
    cerebellum over the same databases replays what was compiled, and never
    what was retired -- retirement suspended the skill, and only the
    operator's re-activation brings it back."""
    library, cerebellum = _reflex_world(tmp_path)
    first = library()
    for _ in range(3):
        first.record_attempt(
            GOAL,
            STEPS,
            success=True,
            strength=VerificationStrength.STRONG,
            principal=ALICE,
        )
    (record,) = first.repository.list_skills()
    first.repository.transition_state(record.skill_id, 1, "human_reviewed")
    first.repository.transition_state(record.skill_id, 1, "active")
    assert cerebellum(first).try_compile_all() == 1

    restarted = cerebellum(library())
    playbook = restarted.match(GOAL, principal=ALICE)
    assert playbook is not None, "a compiled reflex survives the restart"
    restarted.decompile(playbook.id, reason="organ 57 restart proof")

    again = cerebellum(library())
    assert again.match(GOAL, principal=ALICE) is None
    assert again.try_compile_all() == 0
    assert library().repository.get(record.skill_id, 1).state == "suspended"


# ------------------------------------------------------------ 58 Recall Isolation


def test_organ_58_live_recall_admits_through_the_authoritys_gate() -> None:
    """C2. Lessons, semantic memory and facts are admitted by ONE RecallGate
    over the memory database (the skill library by its own, over the
    operational one). A lesson the live path wrote is recalled for its owner
    only through the gate admitting it. (Anyone else is refused twice over:
    the store filters by its principal column, and the gate by the SIGNED
    principal -- which `test_learning_properties.py` pins on its own.)"""
    from aios.api.deps import get_memory_authority

    adapters = get_memory_authority().adapters
    gates = {adapters[n].gate for n in ("lessons", "semantic", "facts")}
    assert len(gates) == 1
    (gate,) = gates
    assert isinstance(gate, RecallGate)
    assert isinstance(adapters["skills"].gate, RecallGate)
    assert gate.context == adapters["skills"].gate.context == "live"

    lessons, mistake_id, marker = _live_lesson(ALICE)
    admitted = gate.admitted
    owner = lessons.relevant_verified(marker, 5, principal=ALICE)
    assert [int(r["mistake_id"]) for r in owner] == [mistake_id]
    assert gate.admitted > admitted, "the live gate admitted it"
    assert lessons.relevant_verified(marker, 5, principal=BOB) == []


def test_a_probe_marker_survives_the_secret_scanner() -> None:
    """The flake `_probe_marker` closes: drawn plainly, about 1 marker in 56
    was redacted, and organ 58's recall-by-marker found nothing."""
    from aios.security.secret_scanner import scan_and_redact

    for _ in range(2000):
        text = _probe_text(_probe_marker())
        assert scan_and_redact(text).scrubbed == text


def test_organ_58_a_new_gate_over_the_same_store_admits_only_what_was_signed(
    tmp_path, own_latch
) -> None:
    """C3. Admission rests on the durable store, not on process memory: a gate
    a later process builds admits the signed row for its owner and still
    refuses everyone else."""
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    db = tmp_path / "provenance.sqlite"
    ProvenanceWriter(
        ProvenanceStore(db), signer, source_kind="live", verifier=verifier
    ).attest_new("mistake_pool", 9, "c" * 64, "created", principal=ALICE)

    gate = RecallGate(ProvenanceStore(db), verifier, context="live")
    assert gate.admits("mistake_pool", 9, "c" * 64, principal=ALICE) is True
    assert gate.admits("mistake_pool", 9, "c" * 64, principal=BOB) is False


def test_organ_58_a_recall_that_names_no_one_is_refused_everything(
    tmp_path, own_latch
) -> None:
    """C5. A recall that does not say who is asking gets NOTHING -- not
    everyone's rows, and not a plausible guess -- and the refusal is counted
    for the operator."""
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(tmp_path / "provenance.sqlite")
    ProvenanceWriter(store, signer, source_kind="live", verifier=verifier).attest_new(
        "mistake_pool", 3, "d" * 64, "created", principal=ALICE
    )
    gate = RecallGate(store, verifier, context="live")
    for anonymous in (None, ""):
        assert gate.admits("mistake_pool", 3, "d" * 64, principal=anonymous) is False
    assert gate.refused.get("no principal") == 2
    assert gate.admits("mistake_pool", 3, "d" * 64, principal=ALICE) is True


# --------------------------------------------------------------- 59 Learning Freeze


class _Frozen(learning_freeze.LearningFreezeAuthority):
    def __init__(self) -> None:
        self.asked: list[str] = []

    def permitted(self) -> bool:
        self.asked.append("<bookkeeping>")
        return False

    def assert_permitted(self, boundary: str) -> None:
        from aios.application.governance.emergency_stop import EmergencyStopError

        self.asked.append(boundary)
        raise EmergencyStopError(f"organ 59 probe: refused {boundary}")


def test_organ_59_every_live_learning_write_asks_the_freeze(monkeypatch) -> None:
    """C2. The process authority's learning writes -- a lesson, a skill
    attempt -- and its reflex compiler all consult the ONE
    LearningFreezeAuthority: frozen, each is refused and names its
    boundary."""
    from aios.api.deps import get_memory_authority
    from aios.application.governance.emergency_stop import EmergencyStopError

    assert isinstance(
        learning_freeze.LEARNING_FREEZE, learning_freeze.LearningFreezeAuthority
    )
    frozen = _Frozen()
    monkeypatch.setattr(learning_freeze, "LEARNING_FREEZE", frozen)
    adapters = get_memory_authority().adapters

    with pytest.raises(EmergencyStopError):
        adapters["lessons"].record(
            "task-frozen", "organ_probe", "c", "f", "a lesson", 0.1, principal=ALICE
        )
    with pytest.raises(EmergencyStopError):
        adapters["skills"].record_attempt(
            "a frozen arc",
            STEPS,
            success=True,
            strength=VerificationStrength.STRONG,
            principal=ALICE,
        )
    assert adapters["cerebellum"].store.try_compile_all() == 0
    assert len(frozen.asked) >= 3, frozen.asked
    assert any("<bookkeeping>" == b for b in frozen.asked)


def test_organ_59_the_freeze_survives_a_restart(own_latch) -> None:
    """C3. The freeze is the operator's DURABLE latch: engaged by one
    controller, a later process -- an empty controller cache -- is frozen
    too, until the operator clears it."""
    from aios.application.governance.emergency_stop import (
        EmergencyStopController,
        EmergencyStopError,
        EmergencyStopHooks,
    )
    from aios.domain.governance.contracts import EmergencyStopRequest

    def noop(*_a, **_k):
        return None

    hooks = EmergencyStopHooks(
        revoke_capabilities=noop,
        cancel_queued_missions=noop,
        kill_active_workers=noop,
        disable_autonomy=noop,
        preserve_evidence=noop,
    )
    EmergencyStopController(own_latch / "emergency_stop.db", hooks=hooks).engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:engage",
            reason="organ 59 restart proof",
        )
    )
    learning_freeze._controllers.clear()  # a new process: nothing cached
    freeze = learning_freeze.LearningFreezeAuthority()
    assert freeze.permitted() is False
    with pytest.raises(EmergencyStopError, match="learning is frozen too"):
        freeze.assert_permitted("organ 59 restart proof")
    assert json.dumps({"control": freeze.control}) == '{"control": "emergency_stop"}'


# ------------------------------- 43 re-scoped: the unified authority's library


def test_organ_43_the_live_skill_library_applies_outcomes_through_its_authority() -> (
    None
):
    """C2 (plan Phase 8: organ 43 re-scoped to the unified authority). The
    process authority's skill slot is the institutional library, and every
    reuse outcome it credits or stains goes through SkillLifecycleAuthority
    over the same operational repository the live turn reads."""
    from aios.api.deps import get_memory_authority
    from aios.application.learning.skill_lifecycle import SkillLifecycleAuthority
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
    )

    skills = get_memory_authority().adapters["skills"]
    assert isinstance(skills, InstitutionalSkillAdapter)
    assert isinstance(skills.lifecycle, SkillLifecycleAuthority)
    assert skills.lifecycle.repository is skills.repository
