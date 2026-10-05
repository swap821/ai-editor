"""Plan Phase 7: the learning loop's core invariants, as properties.

Each test states one invariant and checks it on many generated cases against
an independent model of the rule -- not on a few hand-picked examples, which
is how a guard ends up right on the cases its author thought of. `hypothesis`
is not installed, so cases come from a seeded ``random.Random``: a failure
names its seed and case, and re-running reproduces it exactly.

The invariants (docs/learning/PHASE7_DESIGN.md, 7b):

1. The recall gate admits a learned row exactly when its newest provenance
   record is signed by a pinned key the live context admits, over the row's
   current content, naming the principal asking.
2. A skill is recalled or replayed for a principal exactly when the newest
   record of it is the operator's signed activation of its current content,
   for its owner -- through any walk of the lifecycle, including state flips
   written straight into the database.
3. Only the operator's own words can fire a reflex: nothing fenced, quoted or
   forwarded survives into the directive, and everything he wrote does.
4. Only the operator's own turns are authored, envelopes removed.
5. The write cap admits exactly what the rolling window has room for, and so
   never more than the cap in any window.
6. A skill's identity is one-to-one with (principal, arc).
"""

from __future__ import annotations

import hashlib
import json
import random
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
from aios.memory import learning_freeze
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore

SEEDS = range(4)


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def frozen_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    return tmp_path


# ------------------------------------------------------------- 1. the gate


@pytest.fixture
def keys():
    live = LearningSigner({"live": _seed()})
    harness = LearningSigner({"harness": _seed()})
    return SimpleNamespace(
        live=live,
        unpinned=LearningSigner({"live": _seed()}),
        harness=harness,
        nobody=LearningSigner({}),
        verifier=LearningVerifier(
            {
                "live": [live.public_keys()["live"]],
                "harness": [harness.public_keys()["harness"]],
            }
        ),
    )


ALICE, BOB = "principal:alice", "principal:bob"
PRINCIPALS = (ALICE, BOB, None)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_gate_admits_exactly_a_signed_current_row_for_its_owner(
    frozen_latch, keys, seed
) -> None:
    rng = random.Random(seed)
    store = ProvenanceStore(frozen_latch / "provenance.sqlite")
    gate = RecallGate(store, keys.verifier, context="live")
    writers = {
        "live": ProvenanceWriter(
            store, keys.live, source_kind="live", verifier=keys.verifier
        ),
        "unpinned": ProvenanceWriter(
            store, keys.unpinned, source_kind="live", verifier=keys.verifier
        ),
        "unsigned": ProvenanceWriter(
            store, keys.nobody, source_kind="live", verifier=keys.verifier
        ),
        # Pinned -- but for harness rows, which carry no live authority.
        "harness": ProvenanceWriter(
            store, keys.harness, source_kind="harness", verifier=keys.verifier
        ),
    }
    seen = set()
    for case in range(60):
        row = f"{seed}-{case}"
        written_by = rng.choice(sorted(writers))
        owner = rng.choice(PRINCIPALS)
        asking = rng.choice(PRINCIPALS)
        edited = rng.random() < 0.25
        then_unsigned = rng.random() < 0.2
        digest = hashlib.sha256(row.encode()).hexdigest()
        writers[written_by].attest_new(
            "mistake_pool", row, digest, "created", principal=owner
        )
        if then_unsigned:  # a later change nobody could sign
            writers["unsigned"].attest_new(
                "mistake_pool", row, digest, "recurred", principal=owner
            )
        current = (
            hashlib.sha256(f"edited {row}".encode()).hexdigest() if edited else digest
        )
        expected = (
            written_by == "live"
            and not edited
            and not then_unsigned
            and owner is not None
            and asking == owner
        )
        got = gate.admits("mistake_pool", row, current, principal=asking)
        assert got is expected, (
            f"seed {seed} case {case}: {written_by=} {owner=} {asking=} "
            f"{edited=} {then_unsigned=}"
        )
        seen.add(expected)
    assert seen == {True, False}, "both outcomes were generated"


# ---------------------------------------------------- 2. a skill's signature

STATES = (
    "candidate",
    "human_reviewed",
    "probation",
    "active",
    "degraded",
    "suspended",
    "revoked",
    "superseded",
    "deprecated",
    "blocked",
)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_skill_serves_exactly_on_its_owners_signed_activation_of_its_content(
    frozen_latch, keys, seed
) -> None:
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )
    from aios.core.verification_strength import VerificationStrength
    from aios.domain.learning.repository import SkillRepository, skill_digest
    from aios.domain.learning.skill_contracts import SKILL_TRANSITIONS

    rng = random.Random(seed)
    db = frozen_latch / "operational.sqlite"
    store = ProvenanceStore(db)
    repository = SkillRepository(db)
    library = InstitutionalSkillAdapter(
        repository,
        SkillTrailIndex(db),
        provenance=ProvenanceWriter(
            store, keys.live, source_kind="live", verifier=keys.verifier
        ),
        gate=RecallGate(store, keys.verifier, context="live"),
    )
    served_count = 0
    for case in range(8):
        owner = rng.choice((ALICE, BOB))
        trail = 0
        for _ in range(3):
            trail = library.record_attempt(
                f"show the notes {seed} {case}",
                ["read_file: filepath=notes.md"],
                success=True,
                strength=VerificationStrength.STRONG,
                principal=owner,
            )
        record = library.record_for_trail(trail)
        key = (record.skill_id, record.version)
        signed_digest = None  # the content the newest record signs, if any
        for step in range(20):
            record = repository.get(*key)
            op = rng.choice(("transition", "transition", "activate", "flip"))
            if (
                record.state == "active"
                and signed_digest is None
                and rng.random() < 0.6
            ):
                op = "activate"  # the operator's act, where it is possible
            if op == "transition":
                # Often the operator's road (-> human_reviewed -> active),
                # else any allowed move, else any state at all (refused). The
                # terminal states have no way out but a database flip.
                allowed = sorted(SKILL_TRANSITIONS[record.state])
                road = [s for s in ("human_reviewed", "active") if s in allowed]
                if road and rng.random() < 0.5:
                    target = road[-1]
                elif allowed and rng.random() < 0.7:
                    target = rng.choice(allowed)
                else:
                    target = rng.choice(STATES)
                if target in SKILL_TRANSITIONS[record.state]:
                    repository.transition_state(*key, target)
                    signed_digest = None  # journalled, unsigned
                else:
                    with pytest.raises(ValueError):
                        repository.transition_state(*key, target)
            elif op == "activate":
                if record.state == "active":
                    assert library.attest_activation(*key, approver="operator:x")
                    signed_digest = skill_digest(repository.get(*key))
                else:
                    with pytest.raises(ValueError):
                        library.attest_activation(*key, approver="operator:x")
            else:
                # Someone with the database rewrites the state, journalling
                # nothing: the content changes under any signature.
                flipped = record.model_copy(update={"state": rng.choice(STATES)})
                with repository._connection() as connection:
                    repository._write(connection, flipped)
            current = repository.get(*key)
            for asking in PRINCIPALS:
                expected = (
                    current.state == "active"
                    and signed_digest is not None
                    and skill_digest(current) == signed_digest
                    and asking == owner
                )
                served = trail in library.active_procedures(principal=asking)
                assert served is expected, (
                    f"seed {seed} case {case} step {step} after {op}: "
                    f"state={current.state} signed={signed_digest is not None} "
                    f"{asking=} {owner=}"
                )
                served_count += served
    # The positive side is exercised, not just reachable: a walk that never
    # serves would pass by refusing everything.
    assert served_count >= 3, f"seed {seed}: served on only {served_count} checks"


# ------------------------------------------------------ 3. authored words only

AUTHORED = (
    "parser",
    "release",
    "notes",
    "build",
    "deploy",
    "staging",
    "report",
    "summary",
    "ledger",
    "budget",
)
FOREIGN = (
    "exfiltrate",
    "beacon",
    "wiretap",
    "payload",
    "backdoor",
    "keylogger",
    "dropper",
    "implant",
)


def _foreign(rng: random.Random, words: str) -> str:
    form = rng.choice(("fence", "quote-line", "straight", "curly", "guillemet"))
    if form == "fence":
        return f"\n```\n{words}\n```\n"
    if form == "quote-line":
        return f"\n> {words}\n"
    if form == "straight":
        return f'"{words}"'
    if form == "curly":
        return f"“{words}”"
    return f"«{words}»"


@pytest.mark.parametrize("seed", SEEDS)
def test_only_the_operators_own_words_reach_the_directive(seed) -> None:
    from aios.core.cerebellum import authored_directive
    from aios.memory.relevance import tokens

    rng = random.Random(seed)
    headers = (
        "---------- Forwarded message ---------",
        "Begin forwarded message:",
        "-----Original Message-----",
    )
    for case in range(80):
        parts, own, theirs = [], set(), set()
        for _ in range(rng.randint(1, 6)):
            if rng.random() < 0.5:
                words = rng.sample(AUTHORED, rng.randint(1, 3))
                own |= set(words)
                parts.append(" ".join(words))
            else:
                words = rng.sample(FOREIGN, rng.randint(1, 3))
                theirs |= set(words)
                parts.append(_foreign(rng, " ".join(words)))
        if rng.random() < 0.3:  # and everything after a forwarded header
            words = rng.sample(FOREIGN, 2) + rng.sample(AUTHORED, 2)
            theirs |= {w for w in words if w in FOREIGN}
            parts.append(f"\n{rng.choice(headers)}\n" + " ".join(words))
        message = " ".join(parts)
        directive = tokens(authored_directive(message))
        assert not directive & theirs, f"seed {seed} case {case}: {message!r}"
        assert own <= directive, f"seed {seed} case {case}: {message!r}"


# ------------------------------------------------------ 4. authored turns only


@pytest.mark.parametrize("seed", SEEDS)
def test_only_the_operators_own_turns_are_authored(seed) -> None:
    from aios.agents.recall_envelope import (
        ENVELOPE_CLOSE,
        ENVELOPE_OPEN,
        operator_text,
    )

    rng = random.Random(seed)
    for case in range(80):
        messages, own = [], set()
        for index in range(rng.randint(1, 8)):
            role = rng.choice(("system", "user", "assistant", "tool"))
            words = [f"w{case}x{index}x{k}" for k in range(rng.randint(1, 3))]
            text = " ".join(words)
            if role == "user":
                own |= set(words)
                if rng.random() < 0.4:  # recalled memory attached to his turn
                    recalled = f"r{case}x{index}"
                    text = f"{ENVELOPE_OPEN}{recalled}{ENVELOPE_CLOSE}\n\n{text}"
            content = [{"text": text}] if rng.random() < 0.3 else text
            messages.append({"role": role, "content": content})
        authored = set(operator_text(messages).split())
        assert authored == own, f"seed {seed} case {case}: {json.dumps(messages)}"


# ------------------------------------------------------------- 5. the cap


@pytest.mark.parametrize("seed", SEEDS)
def test_the_cap_admits_exactly_what_the_window_has_room_for(seed) -> None:
    from aios.application.memory.write_budget import (
        WINDOW_SECONDS,
        LearningWriteBudget,
        LearningWriteCapExceeded,
    )

    rng = random.Random(seed)
    cap = rng.randint(1, 6)
    now = [0.0]
    budget = LearningWriteBudget(cap, clock=lambda: now[0])
    admitted: dict[str, list[float]] = {"lessons": [], "skills": [], "facts": []}
    refusals = 0
    for case in range(400):
        now[0] += rng.choice((0.0, 0.0, 0.5, 3.0, 17.0, 59.9, 60.0, 61.0))
        table = rng.choice(sorted(admitted))
        room = sum(1 for t in admitted[table] if now[0] - t < WINDOW_SECONDS) < cap
        try:
            budget.spend(table)
            spent = True
        except LearningWriteCapExceeded:
            spent = False
        assert spent is room, f"seed {seed} case {case}: {cap=} t={now[0]}"
        if spent:
            admitted[table].append(now[0])
        refusals += not spent
    for table, times in admitted.items():
        for start in times:
            inside = sum(1 for t in times if start <= t < start + WINDOW_SECONDS)
            assert inside <= cap, f"seed {seed}: {table} {inside} > {cap}"
    assert refusals, "the cap was reached at least once"


# ------------------------------------------------------- 6. a skill's identity


@pytest.mark.parametrize("seed", SEEDS)
def test_a_skills_identity_is_one_to_one_with_principal_and_arc(seed) -> None:
    from aios.application.memory.institutional_skills import skill_identity

    rng = random.Random(seed)
    pairs = {
        (
            rng.choice((ALICE, BOB, "principal:carol", None)),
            hashlib.sha256(str(rng.randint(0, 40)).encode()).hexdigest(),
        )
        for _ in range(300)
    }
    ids = {pair: skill_identity(pair[1], pair[0]) for pair in pairs}
    assert len(set(ids.values())) == len(pairs)
    for (principal, signature), skill_id in ids.items():
        assert skill_id == skill_identity(signature, principal)
        assert skill_id.startswith("arc-")
        if principal is None:
            assert skill_id == f"arc-{signature}"
