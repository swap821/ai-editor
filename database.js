import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import path from 'path';

export async function initDB() {
  // Open connection to a local SQLite file
  const db = await open({
    filename: path.resolve('./orchestrator_memory.sqlite'),
    driver: sqlite3.Database
  });

  // --- PRODUCTION CONFIGURATION ---
  // Enable Write-Ahead Logging (WAL) for concurrent agent read/writes
  await db.exec('PRAGMA journal_mode = WAL;');
  await db.exec('PRAGMA synchronous = NORMAL;');
  await db.exec('PRAGMA foreign_keys = ON;');

  // --- LAYER 2: EPISODIC MEMORY ---
  // Stores the history of what the agent did and when
  await db.exec(`
    CREATE TABLE IF NOT EXISTS episodic_memory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      session_id TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL
    );
  `);

  // --- LAYER 3: SEMANTIC MEMORY ---
  // Stores ingested knowledge chunks, each mapped to a FAISS vector row.
  // IMPORTANT: This schema MUST match vector_memory_setup.py and hybrid_search.py.
  // If these columns drift, the Python FAISS retrieval breaks silently.
  await db.exec(`
    CREATE TABLE IF NOT EXISTS semantic_memory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      text_content TEXT NOT NULL,
      vector_id INTEGER,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
  `);

  // --- LAYER 4: MISTAKE POOL (Blueprint Sec 6.1) ---
  // Allows the AI to learn from its past terminal errors
  await db.exec(`
    CREATE TABLE IF NOT EXISTS mistake_pool (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      task_id TEXT NOT NULL,
      error_type TEXT NOT NULL,
      root_cause TEXT NOT NULL,
      fix_applied TEXT NOT NULL,
      lesson_text TEXT NOT NULL,
      confidence_delta REAL NOT NULL,
      verification_status TEXT DEFAULT 'pending',
      occurrence_count INTEGER DEFAULT 1
    );
  `);

  // --- LAYER 5: CRYPTOGRAPHIC AUDIT LOG (Blueprint Sec 6.2) ---
  // Tamper-evident ledger for all security-gated actions
  await db.exec(`
    CREATE TABLE IF NOT EXISTS tamper_audit_trail (
      entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      actor TEXT NOT NULL,
      action_payload TEXT NOT NULL,
      security_zone TEXT NOT NULL CHECK (security_zone IN ('GREEN', 'YELLOW', 'RED')),
      current_hash TEXT NOT NULL,
      previous_hash TEXT NOT NULL
    );
  `);

  // Create indexes for fast retrieval during the Agent's reasoning loop
  await db.exec(`CREATE INDEX IF NOT EXISTS idx_mistake_task ON mistake_pool(task_id);`);
  await db.exec(`CREATE INDEX IF NOT EXISTS idx_mistake_type ON mistake_pool(error_type);`);
  await db.exec(`CREATE INDEX IF NOT EXISTS idx_mistake_time ON mistake_pool(timestamp);`);
  await db.exec(`CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id);`);
  await db.exec(`CREATE INDEX IF NOT EXISTS idx_audit_zone ON tamper_audit_trail(security_zone);`);

  console.log("[MEMORY ENGINE] SQLite Database initialized with WAL mode enabled.");
  return db;
}