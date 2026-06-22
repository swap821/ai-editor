import { test } from 'node:test';
import assert from 'node:assert/strict';
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import { logAuditEntry, verifyAuditChain } from '../auditLogger.js';

async function freshDB() {
  const db = await open({ filename: ':memory:', driver: sqlite3.Database });
  await db.exec(`
    CREATE TABLE tamper_audit_trail (
      entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
      actor TEXT NOT NULL,
      action_payload TEXT NOT NULL,
      security_zone TEXT NOT NULL CHECK (security_zone IN ('GREEN','YELLOW','RED')),
      current_hash TEXT NOT NULL,
      previous_hash TEXT NOT NULL
    );
  `);
  return db;
}

test('a fresh, untampered chain verifies valid', async () => {
  const db = await freshDB();
  await logAuditEntry(db, 'agent', 'action one', 'GREEN');
  await logAuditEntry(db, 'agent', 'action two', 'YELLOW');
  await logAuditEntry(db, 'human', 'action three', 'RED');
  const r = await verifyAuditChain(db);
  assert.equal(r.valid, true);
  assert.equal(r.total_entries, 3);
});

test('tampering with a payload breaks the chain at that entry', async () => {
  const db = await freshDB();
  await logAuditEntry(db, 'agent', 'original payload', 'GREEN');
  await logAuditEntry(db, 'agent', 'second payload', 'YELLOW');
  await logAuditEntry(db, 'agent', 'third payload', 'GREEN');

  // Tamper: rewrite entry 2's payload without recomputing hashes.
  await db.run(`UPDATE tamper_audit_trail SET action_payload = ? WHERE entry_id = 2`, ['HACKED']);

  const r = await verifyAuditChain(db);
  assert.equal(r.valid, false);
  assert.equal(r.broken_at, 2);
});

test('hashes are chained (each entry references the previous hash)', async () => {
  const db = await freshDB();
  await logAuditEntry(db, 'agent', 'a', 'GREEN');
  await logAuditEntry(db, 'agent', 'b', 'GREEN');
  const rows = await db.all('SELECT * FROM tamper_audit_trail ORDER BY entry_id');
  assert.equal(rows[1].previous_hash, rows[0].current_hash);
});
