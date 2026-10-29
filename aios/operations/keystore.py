"""Production keys, at rest in the operator's OS credential store.

Operator decision, 2026-10-11 (AGENTS.md §VII.4, amended): a 24/7 production
profile must restart after a reboot without the operator typing keys, so its
keys live in **Windows Credential Manager** -- encrypted by Windows to his
login (DPAPI) -- and nowhere else: never a file, the repo, ``.env`` or
``.aios/``.

* Only the launcher reads a value, only to hand it to the production
  containers in memory (``aios/launcher.py``).
* No command prints a value. ``gagos keys status`` reports presence.
* Storing a key is the operator's act: ``gagos keys generate`` makes a key
  straight into the store (he never sees it either), and ``gagos keys set``
  reads one he already holds from a hidden prompt.

The Windows store is reached through ``advapi32`` directly (ctypes), so this
adds no dependency. Off Windows the store is unavailable and says so.
"""

from __future__ import annotations

import secrets
import sys
from typing import Callable, Optional, Protocol

#: Every credential GAGOS stores is named ``GAGOS/<variable>``.
TARGET_PREFIX = "GAGOS/"

#: Production refuses to start without these (``aios/launcher.py``).
REQUIRED = (
    "AIOS_API_TOKEN",
    "AIOS_EXECUTOR_TOKEN",
    "AIOS_GRAFANA_ADMIN_PASSWORD",
    "AIOS_VERIFICATION_AUTHORITY_KEY",
    # Promotion (every repair or change applied to a project) refuses without
    # it. It had no place in the keystore at all until 2026-10-19, so no
    # install could ever promote.
    "AIOS_PROMOTION_AUTHORITY_KEY",
    # Rollback manifests are signed with it; until 2026-10-19 a missing key
    # silently became a constant published in checkpoint.py.
    "AIOS_CHECKPOINT_AUTHORITY_KEY",
    "AIOS_LEARNING_KEY_LIVE",
)
#: Cloud brains are optional: each one present is one more provider. Bedrock
#: takes either an API key (bearer) or IAM credentials (SigV4); an account whose
#: organization denies bedrock:CallWithBearerToken can only use the latter.
OPTIONAL = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AIOS_OPENAI_API_KEY",
    "AIOS_ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    # The audit chain's signing seed (aios/security/audit_logger.py). Without
    # it every process signs with a throwaway key, and the frozen logger's own
    # trust anchor -- the public half of this seed -- does not exist, so the
    # live chain can never verify. Until 2026-10-29 it had no place here, so it
    # could not be stored at all (found by a review). Optional so production
    # still starts without it; the logger says loudly that it is ephemeral.
    "AIOS_AUDIT_PRIVATE_KEY",
)
NAMES = REQUIRED + OPTIONAL


def _learning_seed() -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


#: The keys GAGOS can make itself. A cloud key comes from its provider.
GENERATORS: dict[str, Callable[[], str]] = {
    "AIOS_API_TOKEN": lambda: secrets.token_urlsafe(32),
    "AIOS_EXECUTOR_TOKEN": lambda: secrets.token_urlsafe(32),
    "AIOS_GRAFANA_ADMIN_PASSWORD": lambda: secrets.token_urlsafe(24),
    # verification_authority refuses a key shorter than 32 characters.
    "AIOS_VERIFICATION_AUTHORITY_KEY": lambda: secrets.token_hex(32),
    # promotion authority refuses a key shorter than 32 characters too.
    "AIOS_PROMOTION_AUTHORITY_KEY": lambda: secrets.token_hex(32),
    "AIOS_CHECKPOINT_AUTHORITY_KEY": lambda: secrets.token_hex(32),
    "AIOS_LEARNING_KEY_LIVE": _learning_seed,
    # A 32-byte Ed25519 seed as 64 hex characters, the form the logger reads.
    "AIOS_AUDIT_PRIVATE_KEY": _learning_seed,
}


class KeystoreUnavailable(RuntimeError):
    """There is no OS credential store here (or it refused)."""


class Keystore(Protocol):
    def get(self, name: str) -> Optional[str]: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool: ...


def _check_name(name: str) -> None:
    if name not in NAMES:
        raise ValueError(f"{name!r} is not a GAGOS production key: {', '.join(NAMES)}")


class MemoryKeystore:
    """A keystore in memory, for tests and dry runs."""

    def __init__(self, values: Optional[dict[str, str]] = None) -> None:
        self._values = dict(values or {})

    def get(self, name: str) -> Optional[str]:
        _check_name(name)
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        _check_name(name)
        self._values[name] = value

    def delete(self, name: str) -> bool:
        _check_name(name)
        return self._values.pop(name, None) is not None


class WindowsCredentialStore:
    """Windows Credential Manager: generic credentials, persisted for this
    user on this machine, encrypted by Windows (DPAPI)."""

    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168
    _MAX_BLOB = 2560

    def __init__(self, prefix: str = TARGET_PREFIX) -> None:
        if sys.platform != "win32":
            raise KeystoreUnavailable("the OS credential store is Windows-only here")
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        pcred = ctypes.POINTER(CREDENTIALW)
        advapi32.CredWriteW.argtypes = [pcred, wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(pcred),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        advapi32.CredDeleteW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None
        self._ctypes = ctypes
        self._api = advapi32
        self._CREDENTIALW = CREDENTIALW
        self._pcred = pcred
        #: Tests use their own prefix and never touch a real GAGOS key.
        self._prefix = prefix

    def _target(self, name: str) -> str:
        _check_name(name)
        return self._prefix + name

    def get(self, name: str) -> Optional[str]:
        ctypes = self._ctypes
        found = self._pcred()
        if not self._api.CredReadW(
            self._target(name), self._CRED_TYPE_GENERIC, 0, ctypes.byref(found)
        ):
            error = ctypes.get_last_error()
            if error == self._ERROR_NOT_FOUND:
                return None
            raise KeystoreUnavailable(f"Credential Manager read failed (error {error})")
        try:
            cred = found.contents
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        finally:
            self._api.CredFree(found)
        return raw.decode("utf-8")

    def set(self, name: str, value: str) -> None:
        ctypes = self._ctypes
        blob = value.encode("utf-8")
        if not blob or len(blob) > self._MAX_BLOB:
            raise ValueError(f"a key must be 1..{self._MAX_BLOB} bytes")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = self._CREDENTIALW()
        cred.Type = self._CRED_TYPE_GENERIC
        cred.TargetName = self._target(name)
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "GAGOS"
        if not self._api.CredWriteW(ctypes.byref(cred), 0):
            error = ctypes.get_last_error()
            raise KeystoreUnavailable(
                f"Credential Manager write failed (error {error})"
            )

    def delete(self, name: str) -> bool:
        ctypes = self._ctypes
        if self._api.CredDeleteW(self._target(name), self._CRED_TYPE_GENERIC, 0):
            return True
        error = ctypes.get_last_error()
        if error == self._ERROR_NOT_FOUND:
            return False
        raise KeystoreUnavailable(f"Credential Manager delete failed (error {error})")


def default_keystore() -> Keystore:
    return WindowsCredentialStore()


def presence(store: Keystore) -> dict[str, bool]:
    """Which keys are stored. Values are read and dropped, never returned."""
    return {name: bool(store.get(name)) for name in NAMES}


def generate(store: Keystore, name: str, *, rotate: bool = False) -> Optional[str]:
    """Make *name* straight into *store*. Returns the learning key's PUBLIC
    half (to pin), else None. Refuses to overwrite unless *rotate*."""
    if name not in GENERATORS:
        raise ValueError(f"{name} comes from its provider: use `gagos keys set {name}`")
    if store.get(name) and not rotate:
        raise ValueError(f"{name} is already stored; pass --rotate to replace it")
    value = GENERATORS[name]()
    store.set(name, value)
    if name == "AIOS_LEARNING_KEY_LIVE":
        return learning_public_key(value)
    return None


def learning_public_key(seed_hex: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def production_environment(store: Keystore) -> dict[str, str]:
    """The stored keys, for the launcher to hand to the production containers."""
    found: dict[str, str] = {}
    for name in NAMES:
        value = store.get(name)
        if value:
            found[name] = value
    return found


__all__ = [
    "GENERATORS",
    "Keystore",
    "KeystoreUnavailable",
    "MemoryKeystore",
    "NAMES",
    "OPTIONAL",
    "REQUIRED",
    "TARGET_PREFIX",
    "WindowsCredentialStore",
    "default_keystore",
    "generate",
    "learning_public_key",
    "presence",
    "production_environment",
]
