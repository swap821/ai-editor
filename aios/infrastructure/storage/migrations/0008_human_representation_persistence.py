from __future__ import annotations

import sqlite3


class HumanRepresentationPersistenceMigration:
    """Tier-1 closure pass, organs 27/28: durable persistence for
    OperatorPreferenceV1 and ProjectPassportV1 -- both Slice 28 contracts
    that shipped typed but with no durable store of their own.

    ``operator_preference_sidecar`` holds only the fields OperatorPreferenceV1
    adds on top of ``aios.memory.facts.SemanticFacts`` (subject/predicate/
    object/confidence already live there, per this module's own docstring
    intent: "not a replacement persistence layer"). Each row is keyed to the
    ``semantic_facts`` row it decorates via ``fact_id``, reusing that table's
    existing contradiction-aware writes instead of duplicating them.

    ``project_passports`` is append-only per ``(project_id, revision)``,
    matching the correction-lineage convention already established for
    governance amendments (Slice 37) -- a project's understanding evolves
    over time and each verified snapshot is worth keeping, not just the
    latest.
    """

    version = 8
    name = "human_representation_persistence_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS operator_preference_sidecar (
                preference_id TEXT PRIMARY KEY,
                fact_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                key TEXT NOT NULL,
                scope TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                review_after TEXT,
                supersedes_json TEXT NOT NULL,
                contradicted_by_json TEXT NOT NULL,
                status TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_digest TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_operator_preference_sidecar_scope
                ON operator_preference_sidecar(scope);
            CREATE INDEX IF NOT EXISTS idx_operator_preference_sidecar_fact
                ON operator_preference_sidecar(fact_id);

            CREATE TABLE IF NOT EXISTS project_passports (
                project_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                goal TEXT NOT NULL,
                architecture_summary TEXT NOT NULL,
                invariants_json TEXT NOT NULL,
                important_paths_json TEXT NOT NULL,
                commands_json TEXT NOT NULL,
                environments_json TEXT NOT NULL,
                current_phase TEXT NOT NULL,
                known_risks_json TEXT NOT NULL,
                explicit_human_decisions_json TEXT NOT NULL,
                verified_at_commit TEXT,
                passport_digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_digest TEXT NOT NULL,
                PRIMARY KEY (project_id, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_project_passports_id
                ON project_passports(project_id);
            """
        )
