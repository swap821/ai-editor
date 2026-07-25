"""ConstitutionAuthority: Single authority owner for the active Constitution snapshot (Organ 25).

Provides concurrent-safe access to the current persisted active `ConstitutionSnapshotV1`.
Migrates all kernel, capability, principal, council, and mirror paths to consume
the exact same active snapshot from a single authority.
"""

from __future__ import annotations

import threading
from typing import Optional

from aios.domain.governance.constitution import (
    ConstitutionSnapshotV1,
    build_constitution_snapshot,
)
from aios.infrastructure.governance.constitution_snapshot_store import (
    ConstitutionSnapshotStore,
)


class ConstitutionAuthority:
    """Authority for active constitution snapshot retrieval and activation."""

    def __init__(self, store: ConstitutionSnapshotStore, *, constitution_id: str | None = None) -> None:
        self.store = store
        self.constitution_id = constitution_id
        self._lock = threading.Lock()

    def get_active_snapshot(self, ratified_by_operator_id: str = "system") -> ConstitutionSnapshotV1:
        with self._lock:
            cid = self.constitution_id or f"constitution:{ratified_by_operator_id}"
            snapshot = self.store.get_current(cid)
            if snapshot is None:
                snapshot = build_constitution_snapshot(
                    ratified_by_operator_id=ratified_by_operator_id,
                )
                self.store.save(snapshot)
            return snapshot

    def activate_snapshot(self, snapshot: ConstitutionSnapshotV1) -> None:
        with self._lock:
            self.store.save(snapshot)
