"""Build a governance observation from real system state.

Organ 55's adjudicators decide over `(audit rows, filesystem state, memory
state)` and never over model output. This module is what turns a live system
into that structure. Nothing here judges anything -- it collects.

WHY THIS EXISTS SEPARATELY FROM THE ADJUDICATORS

The adjudicators were originally written against an *assumed* audit schema, and
every one of the five missions was consequently unadjudicable: they read keys
like `event="red_refusal"` and `strength="STRONG"` that no production code has
ever emitted. The lesson, encoded here: **reconcile the reader to the data, never
the data to the reader.** This module owns every piece of knowledge about how the
real records are shaped, so the adjudicators can stay declarative.

THE ENVELOPE TRAP, IN ONE PLACE

`CortexBus.fetch_since()` returns `BusEvent(id, event_type, signature, payload)`
where `payload` is the **entire serialised CanonicalEvent**, not the domain
payload. So a domain key and an envelope key of the same name collide, and the
envelope wins::

    payload["source"]            == "aios.api.main.sse"   # the emitting module
    payload["payload"]["source"] == "tool_output"         # what M3 must read

Reading the obvious `row["source"]` yields the module name, never matches
`"tool_output"`, and scores M3 a silent permanent failure -- indistinguishable
from "this system has no tool-output detection", which is the very thing M3
exists to detect. `_normalise_bus_event` unwraps exactly one level so that trap
is sprung once, here, instead of in four adjudicators.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "GovernanceSnapshot",
    "GovernanceObservationCollector",
    "normalise_bus_event",
]

#: Keys the envelope contributes, exposed under an underscore so they can never
#: be confused with a domain key of the same name (notably ``source``).
_ENVELOPE_KEYS = {
    "source": "_emitter",
    "turnId": "_turn_id",
    "sessionId": "_session_id",
    "missionId": "_mission_id",
    "workerId": "_worker_id",
    "occurredAt": "_occurred_at",
    "status": "_status",
    "trust": "_trust",
}


def normalise_bus_event(bus_event: Any) -> dict[str, Any]:
    """Flatten one `BusEvent` into a row an adjudicator can read.

    The domain payload wins on every key. Envelope metadata is preserved under
    underscore-prefixed names, so `row["source"]` is unambiguously the DOMAIN
    source and `row["_emitter"]` is the module that emitted it.
    """
    envelope: Mapping[str, Any] = getattr(bus_event, "payload", None) or {}
    inner = envelope.get("payload")
    inner = inner if isinstance(inner, Mapping) else {}

    row: dict[str, Any] = {"event": getattr(bus_event, "event_type", "")}
    for envelope_key, alias in _ENVELOPE_KEYS.items():
        if envelope_key in envelope:
            row[alias] = envelope[envelope_key]
    row.update(inner)
    row.setdefault("event", getattr(bus_event, "event_type", ""))
    # `event` is the canonical type and must never be shadowed by a domain key.
    row["event"] = getattr(bus_event, "event_type", "")
    return row


def _file_digests(roots: Sequence[Path], repo_root: Path | None) -> dict[str, str]:
    """`{repo_relative_posix_path: sha256}` for every regular file under *roots*.

    Keys are repo-relative and POSIX-normalised because that is the vocabulary
    the adjudicators speak -- M3 asks whether anything under `aios/security/`
    changed, and an absolute Windows path would never match that prefix.

    Symlinks are skipped rather than followed: a link pointing out of the tree
    would otherwise let a change appear to have happened somewhere it did not.
    """
    digests: dict[str, str] = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        candidates: Iterable[Path] = root.rglob("*") if root.is_dir() else [root]
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            key = path
            if repo_root is not None:
                try:
                    key = path.relative_to(repo_root)
                except ValueError:
                    pass  # outside the repo: keep the absolute path, still hashed
            digests[key.as_posix()] = digest
    return digests


@dataclass(frozen=True)
class GovernanceSnapshot:
    """System state captured BEFORE a mission runs.

    The bus head id is the mechanism that scopes the observation to this
    mission: everything appended after it belongs to the run, and nothing
    before it does. Without that boundary a collector would happily read a
    previous mission's refusal and score this one on it.
    """

    bus_head_id: int = 0
    file_digests: Mapping[str, str] = field(default_factory=dict)
    memory_baseline: frozenset[Any] = field(default_factory=frozenset)


class GovernanceObservationCollector:
    """Collects real system state into the shape organ 55 adjudicates over.

    Deliberately has no opinion about pass or fail, and no access to model
    output -- there is nowhere for it to put any, because
    `GovernanceObservation` has no field for it.
    """

    def __init__(
        self,
        *,
        bus: Any = None,
        protected_roots: Sequence[Path] = (),
        memory_reader: Any = None,
        repo_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._protected_roots = [Path(p) for p in protected_roots]
        self._memory_reader = memory_reader
        self._repo_root = Path(repo_root) if repo_root is not None else None

    # -- snapshot ---------------------------------------------------------- #

    def begin(self) -> GovernanceSnapshot:
        return GovernanceSnapshot(
            bus_head_id=self._bus_head(),
            file_digests=_file_digests(self._protected_roots, self._repo_root),
            memory_baseline=self._memory_ids(),
        )

    def _bus_head(self) -> int:
        if self._bus is None:
            return 0
        try:
            rows = self._bus.fetch_since(0, limit=100000)
        except Exception:  # noqa: BLE001 - collection must not mask a mission fault
            return 0
        return max((int(getattr(r, "id", 0)) for r in rows), default=0)

    def _memory_ids(self) -> frozenset[Any]:
        if self._memory_reader is None:
            return frozenset()
        try:
            return frozenset(self._memory_reader.verified_ids())
        except Exception:  # noqa: BLE001
            return frozenset()

    # -- collect ----------------------------------------------------------- #

    def collect(
        self,
        snapshot: GovernanceSnapshot,
        *,
        decisions: Sequence[Mapping[str, Any]] = (),
    ) -> Any:
        """Build the observation for the window opened by *snapshot*.

        `decisions` are supplied by the caller because a refusal is returned
        SYNCHRONOUSLY on the verifier's return value (ADR 4.1) and deliberately
        never rides the bus -- the driver sees `ExecutionResult` in the HTTP
        response and hands it here. That is not a workaround; it is the
        architecture's stated position on where decisions live.
        """
        from tools.governance_conformance_runner import GovernanceObservation

        # Declare what was actually READ, not merely what came back empty.
        # An unreachable memory store yields no memory_writes, and without this
        # provenance an adjudicator would score that silence as "nothing
        # unearned was promoted" -- the benchmark passing on its own blindness.
        collected: set[str] = set()
        if self._bus is not None:
            collected.add("bus")
        if self._protected_roots:
            collected.add("filesystem")
        if self._memory_reader is not None:
            collected.add("memory")
        if decisions is not None:
            collected.add("decisions")

        return GovernanceObservation(
            audit_rows=tuple(self._rows_since(snapshot.bus_head_id)),
            filesystem_changes=self._changes_since(snapshot.file_digests),
            memory_writes=tuple(self._memory_since(snapshot.memory_baseline)),
            decisions=tuple(dict(d) for d in decisions),
            collected=frozenset(collected),
        )

    def _rows_since(self, head_id: int) -> list[dict[str, Any]]:
        if self._bus is None:
            return []
        try:
            rows = self._bus.fetch_since(head_id, limit=100000)
        except Exception:  # noqa: BLE001
            return []
        return [normalise_bus_event(r) for r in rows]

    def _changes_since(self, before: Mapping[str, str]) -> dict[str, str | None]:
        after = _file_digests(self._protected_roots, self._repo_root)
        changes: dict[str, str | None] = {}
        for path, digest in after.items():
            if before.get(path) != digest:
                changes[path] = digest
        for path in before:
            if path not in after:
                changes[path] = None  # deleted
        return changes

    def _memory_since(self, baseline: frozenset[Any]) -> list[Mapping[str, Any]]:
        if self._memory_reader is None:
            return []
        try:
            return [
                dict(entry) for entry in self._memory_reader.verified_since(baseline)
            ]
        except Exception:  # noqa: BLE001
            return []


class VerifiedMemoryReader:
    """Reads what actually entered TRUSTED memory, and whether it was earned.

    Organ 55's M2 asks whether a model claim can reach trusted memory as a
    verified success. Answering that needs two things from the store: which
    entries are verified, and whether each one cleared the promotion floor.

    `procedural_skills` has no evidence column -- the text a verdict was derived
    from is not stored beside it (that gap is why VERIFICATION_COMPLETED now
    carries evidence on the bus). What the row DOES carry is
    `verification_strength`, added by an in-place migration
    (`aios/memory/db.py:266`), and promotion is gated on
    `meets_promotion_floor`. So "earned" is decidable from the row: a verified
    entry whose strength is absent or below the floor was promoted without
    earning it.

    Reading strength rather than inventing an `verifier_evidence` column is the
    same discipline as everywhere else here -- reconcile the reader to the data.
    """

    #: (store, id) pairs are the identity; ids are only unique within a table.
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def _connect(self):  # noqa: ANN202 - sqlite3.Connection, imported lazily
        import sqlite3

        from aios import config

        path = self._db_path if self._db_path is not None else config.MEMORY_DB_PATH
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    _QUERIES = (
        (
            "procedural_skills",
            "SELECT id, verification_strength AS strength FROM procedural_skills "
            "WHERE status = 'verified'",
        ),
        (
            "mistake_pool",
            "SELECT id, NULL AS strength FROM mistake_pool "
            "WHERE verification_status = 'verified'",
        ),
    )

    def _rows(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            conn = self._connect()
        except Exception:  # noqa: BLE001 - an unreadable store is reported, not guessed
            return out
        try:
            for store, sql in self._QUERIES:
                try:
                    for row in conn.execute(sql):
                        out.append(
                            {
                                "store": store,
                                "id": row["id"],
                                "trust": "verified",
                                "strength": row["strength"],
                                "earned": self._earned(row["strength"]),
                            }
                        )
                except Exception:  # noqa: BLE001 - table may not exist yet
                    continue
        finally:
            conn.close()
        return out

    @staticmethod
    def _earned(strength_name: Any) -> bool:
        """True when the recorded strength cleared the promotion floor.

        A verified row with no strength at all is NOT earned: it was promoted
        without a recorded basis, which is exactly what M2 is looking for.
        """
        if not strength_name:
            return False
        try:
            from aios.core.verification_strength import (
                meets_promotion_floor,
                strength_from_name,
            )

            return bool(meets_promotion_floor(strength_from_name(str(strength_name))))
        except Exception:  # noqa: BLE001 - unknown label cannot be called earned
            return False

    def verified_ids(self) -> set[tuple[str, Any]]:
        return {(r["store"], r["id"]) for r in self._rows()}

    def verified_since(
        self, baseline: frozenset[tuple[str, Any]]
    ) -> list[dict[str, Any]]:
        return [r for r in self._rows() if (r["store"], r["id"]) not in baseline]
