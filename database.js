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
  // Stores learned facts about the project (e.g., "User prefers Tailwind")
  await db.exec(`
    CREATE TABLE IF NOT EXISTS semantic_memory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      entity_key TEXT UNIQUE NOT NULL,
      entity_value TEXT NOT NULL,
      confidence REAL DEFAULT 1.0
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

  console.log("[MEMORY ENGINE] SQLite Database initialized with WAL mode enabled.");
  return db;
}