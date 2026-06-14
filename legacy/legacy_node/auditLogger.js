import crypto from 'crypto';

// The genesis hash represents the start of the chain (64 zeros)
const GENESIS_HASH = '0'.repeat(64);

export async function logAuditEntry(db, actor, action_payload, security_zone = 'YELLOW') {
  try {
    // 1. Retrieve the previous hash from the database
    const lastEntry = await db.get('SELECT current_hash FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1');
    const previous_hash = lastEntry ? lastEntry.current_hash : GENESIS_HASH;

    // 2. Generate precision timestamp
    const timestamp = new Date().toISOString();

    // 3. Compute the cryptographic hash: SHA-256(prev_hash + timestamp + actor + payload + zone)
    const dataString = `${previous_hash}${timestamp}${actor}${action_payload}${security_zone}`;
    const current_hash = crypto.createHash('sha256').update(dataString).digest('hex');

    // 4. Append to the tamper-evident ledger
    await db.run(
      `INSERT INTO tamper_audit_trail (timestamp, actor, action_payload, security_zone, current_hash, previous_hash)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [timestamp, actor, action_payload, security_zone, current_hash, previous_hash]
    );

    console.log(`[AUDIT] Action logged securely. Hash: ${current_hash.substring(0, 8)}...`);
    return current_hash;
  } catch (error) {
    console.error("[FATAL SECURITY ERROR] Audit log failure:", error);
    throw new Error("Audit log failure - Fail-closed policy enacted.");
  }
}

// Verification function to ensure the database hasn't been tampered with
export async function verifyAuditChain(db) {
  const entries = await db.all('SELECT * FROM tamper_audit_trail ORDER BY entry_id ASC');
  let previous_hash = GENESIS_HASH;

  for (const entry of entries) {
    // Check 1: Does the chain link properly?
    if (entry.previous_hash !== previous_hash) {
      return { valid: false, broken_at: entry.entry_id, reason: "Chain linkage broken (previous hash mismatch)" };
    }
    
    // Check 2: Was the payload altered after the fact?
    const dataString = `${previous_hash}${entry.timestamp}${entry.actor}${entry.action_payload}${entry.security_zone}`;
    const computed_hash = crypto.createHash('sha256').update(dataString).digest('hex');

    if (computed_hash !== entry.current_hash) {
      return { valid: false, broken_at: entry.entry_id, reason: "Payload tampering detected (hash mismatch)" };
    }
    
    previous_hash = entry.current_hash;
  }
  
  return { valid: true, total_entries: entries.length };
}