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

-- == L3: Semantic memory =====================================================
-- Durable knowledge chunks, each bound to a FAISS vector. semantic_memory.id
-- IS the FAISS vector id (via IndexIDMap); vector_id is kept denormalised for
-- backward-compatibility with the legacy Python vector utilities.
CREATE TABLE IF NOT EXISTS semantic_memory (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_content  TEXT NOT NULL,
    vector_id     INTEGER,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP
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
    finding_type     TEXT NOT NULL,   -- 'missing_test'|'smell'|'todo'|'complexity'|...
    evidence         TEXT NOT NULL,   -- deterministic fact: LOC, line refs, counts
    fingerprint      TEXT,            -- stable logical identity (sha256 path|type|symbol); NULL on legacy rows
    llm_commentary   TEXT,            -- model opinion, EXPLICITLY non-authoritative
    proposed_zone    TEXT,            -- 'GREEN'|'YELLOW'|'RED' if a fix were applied (T2)
    proposed_diff    TEXT,            -- unified diff, NULL until tier T2
    status           TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','proposed','approved','applied','rolled_back','rejected')),
    applied_audit_id INTEGER          -- FK into the audit trail once applied (T3)
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
-- Self-analysis hot paths: triaging by status, and looking up a file's history.
CREATE INDEX IF NOT EXISTS idx_sar_status       ON self_analysis_report(status);
CREATE INDEX IF NOT EXISTS idx_sar_path         ON self_analysis_report(target_path);
