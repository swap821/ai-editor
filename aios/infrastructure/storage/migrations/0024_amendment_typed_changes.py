from __future__ import annotations

import sqlite3


class AmendmentTypedChangesMigration:
    """Organ 46 — persist an amendment's typed changes and their ratification.

    `ConstitutionalAmendmentProposalV1` gained two fields when amendments
    stopped being inert prose and became applicable:

    * ``changes`` -- the typed `ConstitutionChangeV1` set an activation applies.
    * ``ratified_changes_digest`` -- a digest of that set taken at ratification,
      which activation re-verifies so a capability spent on one change cannot
      activate another.

    Without columns for them the store silently dropped both on the round trip.
    That is worse than it sounds: `_proposal_from_row` rebuilds the model and
    `_verify` recomputes the digest, so the loss surfaced as
    `RecordTamperedError` -- the tamper alarm firing on the store's own
    lossy read. And through the real HTTP flow (propose -> store -> ratify ->
    store -> activate) the changes would have been gone by activation, putting
    the feature straight back to the no-op it was written to fix.

    Nullable on purpose, following 0023: rows written before this migration
    carry no typed changes, and an absent column must read as "no changes"
    rather than being invented.
    """

    version = 24
    name = "amendment_typed_changes_v1"
    scope = "governance"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        # Index access, not row["name"]: this runs against whatever connection
        # apply_migrations was handed, which may not have a Row factory set.
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(governance_amendment_proposals)")
        }
        if "changes_json" not in existing:
            conn.execute(
                "ALTER TABLE governance_amendment_proposals "
                "ADD COLUMN changes_json TEXT"
            )
        if "ratified_changes_digest" not in existing:
            conn.execute(
                "ALTER TABLE governance_amendment_proposals "
                "ADD COLUMN ratified_changes_digest TEXT"
            )
