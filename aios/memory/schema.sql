-- aios/memory/schema.sql
-- Schema for the AI OS memory layers: L2 Episodic, L3 Semantic, L4 Mistake.
--
-- L1 Working memory is RAM-only (see working.py) and intentionally has no table.
-- The tamper-evident audit trail lives in a SEPARATE database
-- (see aios/security/audit_logger.py) so the cryptographic ledger is isolated
-- from mutable memory and cannot be perturbed by ordinary memory writes.
--
-- Executed idempotently by aios.memory.db.init_memory_db(); safe to re-run.

PRAGMA foreign_keys = ON;

-- == L2: Episodic memory =====================================================
-- The chronological record of what the agent did, said, and observed.
CREATE TABLE IF NOT EXISTS episodic_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,          -- 'user' | 'assistant' | 'tool' | 'system'
    content     TEXT NOT NULL
);

-- == Durable conversation alignment =========================================
-- The latest validated UnderstandingFrame for a session. It remains advisory
-- and unverified; persistence only restores continuity after refresh/restart.
-- session_id is a SHA-256 digest, never the caller-supplied raw identifier.
CREATE TABLE IF NOT EXISTS conversation_state (
    session_id  TEXT PRIMARY KEY,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    frame_json  TEXT NOT NULL
);

-- User-authored corrections to the system's interpretation. These revisions
-- remain communication context only, never approval or verified evidence.
CREATE TABLE IF NOT EXISTS conversation_corrections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    superseded_at       DATETIME,
    status              TEXT NOT NULL
                        CHECK (status IN ('active','superseded','cleared')),
    overrides_json      TEXT NOT NULL,
    corrected_fields_json TEXT NOT NULL,
    before_frame_json   TEXT NOT NULL,
    after_frame_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_corrections_session
    ON conversation_corrections(session_id, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_corrections_active
    ON conversation_corrections(session_id) WHERE status = 'active';

-- == L3: Semantic memory =====================================================
-- Durable knowledge chunks, each bound to a FAISS vector. semantic_memory.id
-- IS the FAISS vector id (via IndexIDMap); vector_id is kept denormalised for
-- backward-compatibility with the legacy Python vector utilities.
CREATE TABLE IF NOT EXISTS semantic_memory (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_content  TEXT NOT NULL,
    vector_id     INTEGER,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    content_hash  TEXT,
    memory_type   TEXT NOT NULL DEFAULT 'chat'
                  CHECK (memory_type IN ('chat','lesson','fact','preference','procedure')),
    verification_status TEXT NOT NULL DEFAULT 'unverified'
                  CHECK (verification_status IN ('unverified','verified','superseded')),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- == L4: Mistake pool ========================================================
-- Structured post-mortems for cross-session learning (Blueprint Section 07).
CREATE TABLE IF NOT EXISTS mistake_pool (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    task_id             TEXT NOT NULL,
    error_type          TEXT NOT NULL,          -- 'TypeError', 'AssertionError', ...
    root_cause          TEXT NOT NULL,          -- human-readable causal analysis
    fix_applied         TEXT NOT NULL,          -- specific remediation steps
    lesson_text         TEXT NOT NULL,          -- generalised prevention rule
    confidence_delta    REAL NOT NULL,          -- post-incident adjustment in [-1.0, 0]
    verification_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (verification_status IN ('pending','verified','superseded')),
    superseded_by       INTEGER REFERENCES mistake_pool(id),
    occurrence_count    INTEGER NOT NULL DEFAULT 1
);

-- == L3b: Semantic facts (entity-relation triples) ===========================
-- Project entities, user preferences, codebase facts as (subject, predicate,
-- object). Contradiction detection (Blueprint 5.3) checks for an existing
-- *active* fact on the same subject+predicate before committing a different
-- object, instead of silently accumulating conflicting knowledge.
CREATE TABLE IF NOT EXISTS semantic_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    approved_by TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','superseded'))
);

-- == Self-Analysis report (the module's own-code diagnostics) =================
-- Modelled on mistake_pool (Assessment §6.4): a structured, queryable record of
-- findings the Self-Analysis agent produces while reading + diagnosing the
-- system's OWN code. T0/T1 write deterministic findings (target_path,
-- finding_type, evidence) with status 'open'; llm_commentary is EXPLICITLY
-- non-authoritative ("trust evidence, not the model"). proposed_zone /
-- proposed_diff stay NULL until a later T2 (propose-diff) increment, and
-- applied_audit_id links into the audit trail only once a T3 apply happens.
CREATE TABLE IF NOT EXISTS self_analysis_report (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP,
    target_path      TEXT NOT NULL,   -- file analysed (project-relative)
    finding_type     TEXT NOT NULL,   -- 'missing_test'|'smell'|'todo'|'complexity'|'uncovered'|...
    evidence         TEXT NOT NULL,   -- deterministic fact: LOC, line refs, counts
    fingerprint      TEXT,            -- stable logical identity (sha256 path|type|symbol); NULL on legacy rows
    llm_commentary   TEXT,            -- model opinion, EXPLICITLY non-authoritative
    proposed_zone    TEXT,            -- 'GREEN'|'YELLOW'|'RED' if a fix were applied (T2)
    proposed_diff    TEXT,            -- unified diff, NULL until tier T2
    proposed_by      TEXT,            -- who proposed the fix (§6.3 groundwork for T3's no-self-approval guard)
    approved_by      TEXT,            -- the HUMAN who approved the apply (T3); must differ from proposed_by (§6.3)
    status           TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','proposed','approved','applied','rolled_back','rejected')),
    applied_audit_id INTEGER          -- FK into the audit trail once applied (T3)
);

-- == Development evidence ====================================================
-- One row per completed/paused agent turn. Only verified_success and
-- verified_failure outcomes may calibrate future planning or procedural skills.
CREATE TABLE IF NOT EXISTS development_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    task_text           TEXT NOT NULL,
    task_signature      TEXT NOT NULL,
    outcome             TEXT NOT NULL
                        CHECK (outcome IN ('verified_success','verified_failure',
                                           'unverified','paused')),
    tool_calls           INTEGER NOT NULL DEFAULT 0,
    human_interventions INTEGER NOT NULL DEFAULT 0,
    blocked_actions     INTEGER NOT NULL DEFAULT 0,
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

-- == Procedural skill memory =================================================
-- Workflows become verified only after repeated verification-backed success.
CREATE TABLE IF NOT EXISTS procedural_skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    signature       TEXT NOT NULL UNIQUE,
    goal_pattern    TEXT NOT NULL,
    steps_json      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate','verified','superseded')),
    success_count   INTEGER NOT NULL DEFAULT 0,
    failure_count   INTEGER NOT NULL DEFAULT 0
);

-- == Safe curriculum =========================================================
-- Curriculum tasks never auto-execute. Verified live outcomes matching a task
-- update its evidence; a level is mastered only after training passes plus a
-- held-out pass.
CREATE TABLE IF NOT EXISTS curriculum_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    skill_name      TEXT NOT NULL,
    level           INTEGER NOT NULL CHECK (level >= 1),
    prompt          TEXT NOT NULL,
    held_out        INTEGER NOT NULL DEFAULT 0 CHECK (held_out IN (0,1)),
    status          TEXT NOT NULL DEFAULT 'available'
                    CHECK (status IN ('locked','available','mastered')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    successes       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(skill_name, level, prompt)
);

-- == Indexes =================================================================
CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id);
CREATE INDEX IF NOT EXISTS idx_episodic_time    ON episodic_memory(timestamp);
CREATE INDEX IF NOT EXISTS idx_mistake_task     ON mistake_pool(task_id);
CREATE INDEX IF NOT EXISTS idx_mistake_type     ON mistake_pool(error_type);
CREATE INDEX IF NOT EXISTS idx_mistake_time     ON mistake_pool(timestamp);
-- Partial index: hot path is querying *verified* lessons during planning.
CREATE INDEX IF NOT EXISTS idx_mistake_verified ON mistake_pool(verification_status)
    WHERE verification_status = 'verified';
CREATE INDEX IF NOT EXISTS idx_facts_sp         ON semantic_facts(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_development_sig  ON development_events(task_signature);
CREATE INDEX IF NOT EXISTS idx_development_outcome ON development_events(outcome);
CREATE INDEX IF NOT EXISTS idx_skills_status    ON procedural_skills(status);
CREATE INDEX IF NOT EXISTS idx_curriculum_skill ON curriculum_tasks(skill_name, level);
-- Self-analysis hot paths: triaging by status, and looking up a file's history.
CREATE INDEX IF NOT EXISTS idx_sar_status       ON self_analysis_report(status);
CREATE INDEX IF NOT EXISTS idx_sar_path         ON self_analysis_report(target_path);
