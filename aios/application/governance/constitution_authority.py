"""ConstitutionAuthority: the single authority owner for the active
Constitution snapshot (Organ 25).

Before this organ, "what is the current constitution?" had three different
answers depending on who asked: the durable snapshot chain, a per-call rebuild
from live config, and a hardcoded ``ratified_by_operator_id="operator"``
fallback inside ``PolicyKernel``. An activated amendment moved the durable
chain and reached neither of the other two, which made
``CapabilityAuthority.consume()``'s stale-constitution rejection structurally
inert: it compared a rebuilt digest against a binding stamped with the same
rebuilt digest, so the two always matched.

This module is the one answer. Every kernel, capability, principal, council
and mirror path reads the active snapshot from here.

Fail-closed contract
--------------------
Enrollment is re-verified on EVERY call, not only when the caller omits an
operator id. That distinction matters: the two call sites that run on every
authenticated request (``IdentityService``) and every capability consumption
(``CapabilityAuthority.consume``) both pass an explicit operator id, so a
check that only guarded the argument-free path would guard nothing that
actually runs.

Concretely:

* no enrolled sovereign -> :class:`NoEnrolledSovereignError`
* an explicit operator id that disagrees with the enrolled sovereign ->
  :class:`OperatorIdentityChangedError` (a capability or session minted for a
  sovereign who is no longer enrolled must not consume)
* database unreachable, or a row that fails its own digest check ->
  :class:`ConstitutionDegraded`

All three subclass :class:`ConstitutionAuthorityError`, which the API layer
maps to ``503`` -- the same shape ``IdentityDegraded`` already uses.

A chain is only ever bootstrapped for the *enrolled* sovereign. Passing a
novel operator id can no longer silently mint a second, never-amended shadow
chain and return it as authoritative.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Protocol

from aios.domain.governance.constitution import (
    ConstitutionSnapshotV1,
    build_constitution_snapshot,
)
from aios.infrastructure.governance.constitution_snapshot_store import (
    ConcurrentActivationError,
    ConstitutionSnapshotStore,
    RecordTamperedError,
)


class ConstitutionAuthorityError(RuntimeError):
    """Base class for every fail-closed constitution condition."""


class NoEnrolledSovereignError(ConstitutionAuthorityError):
    """No Human Sovereign is enrolled, so no constitution can be authoritative."""


class OperatorIdentityChangedError(ConstitutionAuthorityError):
    """A caller asked for a constitution under an operator id that is not the
    currently enrolled sovereign -- a stale session, a capability minted for a
    since-replaced operator, or a caller that fabricated an identity."""


class ConstitutionDegraded(ConstitutionAuthorityError):
    """The constitution store is unreadable or holds a tampered row."""


class OperatorLookup(Protocol):
    """The slice of ``IdentityStore`` this authority depends on."""

    def operator(self) -> dict[str, Any] | None: ...


class ConstitutionAuthority:
    """Authority for active constitution snapshot retrieval and activation."""

    def __init__(
        self,
        store: ConstitutionSnapshotStore,
        *,
        identity_store: OperatorLookup,
        constitution_id: str | None = None,
    ) -> None:
        self.store = store
        self.identity_store = identity_store
        self.constitution_id = constitution_id
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Identity resolution -- the fail-closed gate
    # ------------------------------------------------------------------ #
    def _enrolled_operator_id(self) -> str:
        """The one enrolled sovereign's id, or fail closed.

        ``sovereign_operator`` is a singleton table (``WHERE singleton_id =
        1``), so there is exactly one -- this is a lookup, not a search.
        """
        try:
            operator = self.identity_store.operator()
        except sqlite3.Error as exc:
            raise ConstitutionDegraded(
                f"identity store unreachable while resolving the active "
                f"constitution: {exc}"
            ) from exc
        if operator is None:
            raise NoEnrolledSovereignError(
                "no Human Sovereign is enrolled; there is no authoritative "
                "constitution to serve"
            )
        operator_id = str(operator.get("operator_id") or "").strip()
        if not operator_id:
            raise ConstitutionDegraded(
                "enrolled sovereign row is missing its operator_id"
            )
        return operator_id

    def _resolve(self, requested_operator_id: str | None) -> tuple[str, str]:
        """Return ``(constitution_id, operator_id)`` for this call.

        The enrolled sovereign is always consulted. A caller-supplied id is
        treated as an *assertion to verify*, never as a chain selector.
        """
        enrolled = self._enrolled_operator_id()
        if requested_operator_id is not None and requested_operator_id != enrolled:
            raise OperatorIdentityChangedError(
                f"requested constitution for operator "
                f"{requested_operator_id!r}, but the enrolled sovereign is a "
                f"different identity; refusing to serve a shadow chain"
            )
        cid = self.constitution_id or f"constitution:{enrolled}"
        return cid, enrolled

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_active_snapshot(
        self, ratified_by_operator_id: str | None = None
    ) -> ConstitutionSnapshotV1:
        """The active snapshot for the enrolled sovereign's chain.

        ``ratified_by_operator_id`` is optional and, when given, is verified
        against the enrolled sovereign rather than used to pick a chain.
        """
        cid, operator_id = self._resolve(ratified_by_operator_id)
        with self._lock:
            snapshot = self._get_current(cid)
            if snapshot is not None:
                return snapshot
            # First-ever access for the enrolled sovereign: mint the version-1
            # baseline. This is reachable only for the *enrolled* operator --
            # an unknown id fails closed in `_resolve` above rather than
            # minting a second chain.
            baseline = build_constitution_snapshot(
                ratified_by_operator_id=operator_id
            )
            try:
                self.store.save(baseline, expected_previous_digest=None)
            except ConcurrentActivationError:
                # Another writer bootstrapped this chain between our read and
                # our write. Theirs is authoritative; re-read rather than
                # overwriting a chain that may already have advanced.
                existing = self._get_current(cid)
                if existing is None:  # pragma: no cover - defensive
                    raise
                return existing
            except sqlite3.Error as exc:
                raise ConstitutionDegraded(
                    f"constitution store unwritable during baseline "
                    f"creation: {exc}"
                ) from exc
            return baseline

    def get_snapshot_by_digest(self, digest: str) -> ConstitutionSnapshotV1 | None:
        try:
            return self.store.get_by_digest(digest)
        except RecordTamperedError as exc:
            raise ConstitutionDegraded(str(exc)) from exc
        except sqlite3.Error as exc:
            raise ConstitutionDegraded(
                f"constitution store unreadable: {exc}"
            ) from exc

    def _get_current(self, cid: str) -> ConstitutionSnapshotV1 | None:
        try:
            return self.store.get_current(cid)
        except RecordTamperedError as exc:
            raise ConstitutionDegraded(str(exc)) from exc
        except sqlite3.Error as exc:
            raise ConstitutionDegraded(
                f"constitution store unreadable: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def activate_snapshot(
        self,
        snapshot: ConstitutionSnapshotV1,
        *,
        expected_previous_digest: str | None,
    ) -> None:
        """Move this chain's current pointer to `snapshot`, but only if it is
        still where the caller last saw it.

        :class:`ConcurrentActivationError` propagates uncaught -- a losing
        activation is a real 409 the caller must see, not something to
        paper over.
        """
        with self._lock:
            try:
                self.store.save(
                    snapshot, expected_previous_digest=expected_previous_digest
                )
            except sqlite3.Error as exc:
                raise ConstitutionDegraded(
                    f"constitution store unwritable during activation: {exc}"
                ) from exc


# --------------------------------------------------------------------------- #
# Process-wide singleton
#
# Lives here rather than in `aios/api/deps.py` so the non-HTTP construction
# sites (`get_policy_kernel`, `Executor.__init__`, the runtime proof) share the
# literal same object with the FastAPI-injected one. Pointing several
# instances at the same database file would still serialise writes through the
# store's compare-and-swap, but "one application-wide authority" would be a
# claim rather than a fact.
# --------------------------------------------------------------------------- #

_AUTHORITY: ConstitutionAuthority | None = None
_AUTHORITY_LOCK = threading.Lock()


def get_constitution_authority() -> ConstitutionAuthority:
    """Return the process-wide :class:`ConstitutionAuthority` singleton."""
    global _AUTHORITY
    if _AUTHORITY is not None:
        return _AUTHORITY
    with _AUTHORITY_LOCK:
        if _AUTHORITY is None:
            from aios import config
            from aios.infrastructure.identity.sqlite_store import IdentityStore

            _AUTHORITY = ConstitutionAuthority(
                ConstitutionSnapshotStore(config.CONSTITUTION_SNAPSHOT_DB_PATH),
                identity_store=IdentityStore(config.IDENTITY_DB_PATH),
            )
    return _AUTHORITY


def reset_constitution_authority() -> None:
    """Drop the cached singleton.

    Test-support only. Without this, whichever test first touches the kernel
    pins the authority for the rest of the pytest session, and a later test's
    dependency override silently fails to reach it.
    """
    global _AUTHORITY
    with _AUTHORITY_LOCK:
        _AUTHORITY = None


__all__ = [
    "ConstitutionAuthority",
    "ConstitutionAuthorityError",
    "ConstitutionDegraded",
    "NoEnrolledSovereignError",
    "OperatorIdentityChangedError",
    "OperatorLookup",
    "get_constitution_authority",
    "reset_constitution_authority",
]
