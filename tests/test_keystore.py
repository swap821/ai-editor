"""Production keys at rest: the OS credential store, and nothing ever prints one.

Operator decision 2026-10-11 (AGENTS.md §VII.4, amended). Pinned:

* a generated key goes straight into the store; the call returns nothing but
  the learning key's PUBLIC half, which is meant to be pinned;
* an existing key is never silently replaced;
* presence is reported without the value;
* a cloud key cannot be generated -- it comes from its provider;
* the real Windows store round-trips (on Windows, under a test-only name, and
  is cleaned up).
"""

from __future__ import annotations

import json
import secrets
import sys

import pytest

from aios.operations import keystore as ks


def test_generate_stores_and_returns_nothing_secret() -> None:
    store = ks.MemoryKeystore()
    assert ks.generate(store, "AIOS_VERIFICATION_AUTHORITY_KEY") is None
    value = store.get("AIOS_VERIFICATION_AUTHORITY_KEY")
    assert value and len(value) >= 32, "verification_authority refuses < 32 chars"


def test_the_learning_key_returns_only_its_public_half() -> None:
    store = ks.MemoryKeystore()
    public = ks.generate(store, "AIOS_LEARNING_KEY_LIVE")
    seed = store.get("AIOS_LEARNING_KEY_LIVE")
    assert public and seed and public != seed
    assert public == ks.learning_public_key(seed)
    assert len(bytes.fromhex(public)) == 32


def test_an_existing_key_is_never_silently_replaced() -> None:
    store = ks.MemoryKeystore({"AIOS_API_TOKEN": "kept"})
    with pytest.raises(ValueError, match="already stored"):
        ks.generate(store, "AIOS_API_TOKEN")
    assert store.get("AIOS_API_TOKEN") == "kept"
    ks.generate(store, "AIOS_API_TOKEN", rotate=True)
    assert store.get("AIOS_API_TOKEN") != "kept"


def test_a_cloud_key_comes_from_its_provider() -> None:
    with pytest.raises(ValueError, match="comes from its provider"):
        ks.generate(ks.MemoryKeystore(), "AWS_BEARER_TOKEN_BEDROCK")


def test_only_named_production_keys_are_stored() -> None:
    with pytest.raises(ValueError):
        ks.MemoryKeystore().set("PATH", "x")


def test_presence_never_carries_a_value() -> None:
    store = ks.MemoryKeystore({"AIOS_API_TOKEN": "s3cret-value"})
    report = ks.presence(store)
    assert report["AIOS_API_TOKEN"] is True
    assert report["AIOS_LEARNING_KEY_LIVE"] is False
    assert "s3cret-value" not in json.dumps(report)


def test_the_production_environment_holds_only_stored_keys() -> None:
    store = ks.MemoryKeystore({"AIOS_API_TOKEN": "a", "GEMINI_API_KEY": "g"})
    assert ks.production_environment(store) == {
        "AIOS_API_TOKEN": "a",
        "GEMINI_API_KEY": "g",
    }


def test_every_required_key_can_be_generated() -> None:
    """Production needs these, and none of them comes from a provider."""
    assert set(ks.REQUIRED) <= set(ks.GENERATORS)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager")
def test_the_windows_store_round_trips_under_a_test_name() -> None:
    store = ks.WindowsCredentialStore(prefix=f"GAGOS-TEST-{secrets.token_hex(6)}/")
    name = "AIOS_API_TOKEN"
    try:
        assert store.get(name) is None
        store.set(name, "round-trip ✓ value")
        assert store.get(name) == "round-trip ✓ value"
        store.set(name, "replaced")
        assert store.get(name) == "replaced"
    finally:
        assert store.delete(name) is True
    assert store.get(name) is None
    assert store.delete(name) is False


def test_off_windows_the_store_says_it_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(ks.sys, "platform", "linux")
    with pytest.raises(ks.KeystoreUnavailable):
        ks.WindowsCredentialStore()
