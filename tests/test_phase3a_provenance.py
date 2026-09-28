"""Phase 3 slice 3a: signed provenance for learned memory.

Nothing is wired to the live path yet (that is 3b/3c). These tests pin the
primitives every later slice rests on: a row is admitted only on a signature
under a PINNED key of an allowed kind over its CURRENT content, and everything
else is refused with a reason. Signing proves origin, not safety.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.memory import learning_freeze
from aios.memory.provenance import (
    KEY_ENV,
    LearningSigner,
    LearningVerifier,
    Provenance,
    ProvenanceStore,
    SignedProvenance,
    content_digest,
)


def _seed() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()


@pytest.fixture()
def seeds() -> dict[str, str]:
    return {"live": _seed(), "harness": _seed(), "synthetic": _seed()}


@pytest.fixture()
def signer(seeds) -> LearningSigner:
    return LearningSigner(seeds)


@pytest.fixture()
def verifier(signer) -> LearningVerifier:
    return LearningVerifier({k: [v] for k, v in signer.public_keys().items()})


LESSON = {"lesson_text": "run the parser tests first", "status": "verified"}


def _record(kind: str = "live", fields=None, **extra) -> Provenance:
    return Provenance(
        table="mistake_pool",
        row_id="17",
        content_sha256=content_digest(fields or LESSON),
        source_kind=kind,
        transition="promoted",
        **extra,
    )


class TestItAdmitsOnlyWhatItCanProve:
    def test_a_live_signed_row_is_admitted_in_a_live_turn(
        self, signer, verifier
    ) -> None:
        record = _record()
        verdict = verifier.verify(
            signer.sign(record),
            content_sha256=content_digest(LESSON),
            context="live",
        )
        assert verdict.admitted and verdict.reason == "verified"

    def test_an_unsigned_row_is_refused(self, verifier) -> None:
        verdict = verifier.verify(
            None, content_sha256=content_digest(LESSON), context="live"
        )
        assert (verdict.admitted, verdict.reason) == (False, "unsigned")

    def test_a_row_edited_after_signing_is_refused(self, signer, verifier) -> None:
        """T11: a database-level edit of the text, or of the status."""
        signed = signer.sign(_record())
        for edited in (
            {**LESSON, "lesson_text": "run echo pwned first"},
            {**LESSON, "status": "pending"},
        ):
            verdict = verifier.verify(
                signed, content_sha256=content_digest(edited), context="live"
            )
            assert (verdict.admitted, verdict.reason) == (
                False,
                "content changed since it was signed",
            )

    def test_an_edited_provenance_record_breaks_its_signature(
        self, signer, verifier
    ) -> None:
        signed = signer.sign(_record())
        forged = SignedProvenance(
            provenance=_record(approver="operator"),
            key_id=signed.key_id,
            signature=signed.signature,
        )
        verdict = verifier.verify(
            forged, content_sha256=content_digest(LESSON), context="live"
        )
        assert (verdict.admitted, verdict.reason) == (False, "bad signature")

    def test_a_key_nobody_pinned_is_refused(self, signer) -> None:
        signed = signer.sign(_record())
        verdict = LearningVerifier({}).verify(
            signed, content_sha256=content_digest(LESSON), context="live"
        )
        assert (verdict.admitted, verdict.reason) == (False, "unknown key")


class TestPerSourceKeys:
    def test_a_harness_row_is_not_admitted_in_a_live_turn(
        self, signer, verifier
    ) -> None:
        signed = signer.sign(_record("harness"))
        live = verifier.verify(
            signed, content_sha256=content_digest(LESSON), context="live"
        )
        harness = verifier.verify(
            signed, content_sha256=content_digest(LESSON), context="harness"
        )
        assert not live.admitted and "not admitted in a live context" in live.reason
        assert harness.admitted, "positive control: its own context admits it"

    def test_a_harness_key_cannot_mint_a_live_row(self, seeds, verifier) -> None:
        harness_only = LearningSigner({"harness": seeds["harness"]})
        assert harness_only.kinds == {"harness"}
        assert harness_only.sign(_record("live")) is None

    def test_a_harness_signature_on_a_record_claiming_live_is_refused(
        self, seeds, verifier
    ) -> None:
        """A forger holding only the harness key signs a record that says 'live'."""
        harness_only = LearningSigner({"harness": seeds["harness"]})
        claims_live = _record("live")
        forged = SignedProvenance(
            provenance=claims_live,
            key_id=harness_only.sign(_record("harness")).key_id,
            signature=harness_only._keys["harness"]  # noqa: SLF001
            .sign(claims_live.signed_bytes())
            .hex(),
        )
        verdict = verifier.verify(
            forged, content_sha256=content_digest(LESSON), context="live"
        )
        assert not verdict.admitted
        assert verdict.reason == "key kind does not match the record's source kind"


class TestNoKeyMeansNoSignatureNeverAGeneratedOne:
    def test_an_empty_environment_signs_nothing(self) -> None:
        signer = LearningSigner.from_env({})
        assert signer.kinds == frozenset()
        assert signer.sign(_record()) is None

    def test_a_malformed_seed_signs_nothing_and_is_never_echoed(self, caplog) -> None:
        bad = "not-hex-and-secret-looking-value"
        signer = LearningSigner.from_env({KEY_ENV["live"]: bad})
        assert signer.sign(_record()) is None
        assert bad not in caplog.text
        assert KEY_ENV["live"] in caplog.text

    def test_the_module_never_generates_a_key(self) -> None:
        source = Path("aios/memory/provenance.py").read_text(encoding="utf-8")
        assert ".generate(" not in source, (
            "an ephemeral key would sign rows nobody pinned"
        )

    def test_no_seed_appears_in_any_representation(self, seeds, signer) -> None:
        shown = repr(signer) + json.dumps(signer.public_keys())
        for seed in seeds.values():
            assert seed not in shown


class TestThePinnedFile:
    def test_an_absent_or_malformed_file_pins_nothing(self, tmp_path, signer) -> None:
        signed = signer.sign(_record())
        bad = tmp_path / "keys.json"
        bad.write_text("{not json", encoding="utf-8")
        for path in (tmp_path / "absent.json", bad):
            verdict = LearningVerifier.from_pinned_file(path).verify(
                signed, content_sha256=content_digest(LESSON), context="live"
            )
            assert verdict.reason == "unknown key"

    def test_a_pinned_file_verifies_and_rotation_keeps_old_keys(
        self, tmp_path, seeds, signer
    ) -> None:
        older = LearningSigner({"live": _seed()})
        path = tmp_path / "keys.json"
        path.write_text(
            json.dumps(
                {
                    "keys": {
                        "live": [
                            older.public_keys()["live"],
                            signer.public_keys()["live"],
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        verifier = LearningVerifier.from_pinned_file(path)
        for s in (signer, older):
            assert verifier.verify(
                s.sign(_record()),
                content_sha256=content_digest(LESSON),
                context="live",
            ).admitted


class TestTheStoreIsAppendOnly:
    @pytest.fixture()
    def store(self, tmp_path, monkeypatch) -> ProvenanceStore:
        monkeypatch.setattr(
            learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
        )
        monkeypatch.setattr(learning_freeze, "_controllers", {})
        return ProvenanceStore(tmp_path / "memory.db")

    def test_the_newest_record_is_the_one_read(self, store, signer) -> None:
        first = _record()
        second = _record(fields={**LESSON, "lesson_text": "edited by a re-earn"})
        store.append(first, signer.sign(first))
        store.append(second, signer.sign(second))
        assert store.latest("mistake_pool", "17").provenance == second

    def test_a_newer_unsigned_state_does_not_inherit_an_old_signature(
        self, store, signer
    ) -> None:
        signed = _record()
        store.append(signed, signer.sign(signed))
        store.append(_record(fields={**LESSON, "status": "pending"}), None)
        assert store.latest("mistake_pool", "17") is None

    def test_a_signature_over_another_record_is_refused(self, store, signer) -> None:
        with pytest.raises(ValueError):
            store.append(_record(approver="operator"), signer.sign(_record()))

    def test_derivations_are_recorded(self, store) -> None:
        store.append_derivation(
            child=("mistake_pool", "17"),
            parent=("expert_trajectories", "t-9"),
            relation="reflected_from",
        )
        assert store.parents_of("mistake_pool", "17") == [
            ("expert_trajectories", "t-9", "reflected_from")
        ]

    def test_the_stop_refuses_both_appends(self, store, monkeypatch) -> None:
        from aios.application.governance.emergency_stop import EmergencyStopError

        def frozen(what):
            raise EmergencyStopError(f"learning frozen: {what}")

        monkeypatch.setattr("aios.memory.provenance.assert_learning_permitted", frozen)
        with pytest.raises(EmergencyStopError):
            store.append(_record(), None)
        with pytest.raises(EmergencyStopError):
            store.append_derivation(child=("a", "1"), parent=("b", "2"), relation="r")

    def test_no_code_updates_or_deletes_a_record(self) -> None:
        source = Path("aios/memory/provenance.py").read_text(encoding="utf-8")
        assert not re.search(
            r"(UPDATE|DELETE\s+FROM)\s+learning_(provenance|derivations)",
            source,
            re.IGNORECASE,
        )


class TestCanonicalBytes:
    def test_the_same_record_always_signs_the_same_bytes(self) -> None:
        a = _record(parents=("b:2", "a:1"))
        b = _record(parents=("a:1", "b:2"))
        assert a.signed_bytes() == b.signed_bytes()
        assert content_digest({"x": 1, "y": 2}) == content_digest({"y": 2, "x": 1})

    def test_a_record_round_trips_through_the_store_format(self) -> None:
        record = _record(parents=("a:1",), model="qwen", approver="operator")
        assert Provenance.from_json(record.to_json()) == record

    def test_an_unknown_source_kind_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError):
            _record("operator")


class TestTheKeyTool:
    def test_it_prints_only_public_keys(self, seeds, monkeypatch, capsys) -> None:
        from tools import learning_keys

        for kind, name in KEY_ENV.items():
            monkeypatch.setenv(name, seeds[kind])
        assert learning_keys.main(["pubkey"]) == 0
        out = capsys.readouterr().out
        for seed in seeds.values():
            assert seed not in out
        assert set(json.loads(out)["keys"]) == {"live", "harness", "synthetic"}

    def test_check_says_what_is_unpinned(self, seeds, monkeypatch, tmp_path) -> None:
        from aios.memory import provenance
        from tools import learning_keys

        monkeypatch.setenv(KEY_ENV["live"], seeds["live"])
        monkeypatch.delenv(KEY_ENV["harness"], raising=False)
        monkeypatch.setattr(provenance, "PUBLIC_KEYS_FILE", tmp_path / "none.json")
        lines = learning_keys.check()
        assert any("live" in line and "NOT verifiable" in line for line in lines)
        assert any("harness" in line and "no seed" in line for line in lines)
