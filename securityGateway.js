// securityGateway.js
// Deterministic, fail-closed security classifier.
//
// Design invariants (from the AI-OS blueprint, Section 06):
//   - Same input always produces the same zone (no LLM judgement).
//   - Ambiguity, parser errors, and unknown patterns default to RED (fail-closed).
//   - Classification is independent of model confidence.
//
// Zone -> action mapping used by the server:
//   GREEN  -> ALLOW         (auto-execute)
//   YELLOW -> REQUIRE_HUMAN (one-click human approval)
//   RED    -> BLOCK         (refused; destructive / out-of-scope / injection)

import { commandStaysInScope } from './scopeLock.js';

export const Zone = Object.freeze({ GREEN: 'GREEN', YELLOW: 'YELLOW', RED: 'RED' });

// 1. Destructive / high-risk commands -> RED (blocked outright).
const RED_PATTERNS = [
  /\brm\s+-rf\b/i, /\brm\s+/i, /\bdel\s+\/s\b/i, /\bdel\s+\*/i,
  /\bformat\s+/i, /\bmkfs\b/i, /\bdd\s+if=/i, /\bdd\s+/i,
  />\s*\/dev\/sd[a-z]/i, /\bchmod\s+777\b/i, /\bchown\b/i,
  /\bremove-item\b/i, /\brmdir\s+\/s\b/i,
  /\b:\(\)\s*\{.*\}\s*;/, // fork bomb
  /\bshutdown\b/i, /\breboot\b/i, /\bmkfs\./i,
];

// 2. Network egress -> RED (data exfiltration / supply-chain risk).
const NETWORK_PATTERNS = [
  /\bcurl\s+/i, /\bwget\s+/i, /\binvoke-webrequest\b/i,
  /\bnc\s+-/i, /\bnetcat\b/i, /\bscp\s+/i, /\bftp\s+/i,
];

// 3. Caution operations -> YELLOW (require explicit human approval).
const YELLOW_PATTERNS = [
  /\bpip\s+install\b/i, /\bnpm\s+install\b/i, /\byarn\s+add\b/i,
  /\bgit\s+(commit|push|reset|clone)\b/i,
  /\bset-content\b/i, /\bout-file\b/i, /\bnew-item\b.*-itemtype\s+file/i,
  /\bmkdir\b/i, /\bnew-item\b.*-itemtype\s+directory/i,
  /\bmv\s+/i, /\bmove-item\b/i, /\bcp\s+/i, /\bcopy-item\b/i,
];

// 4. Prompt-injection patterns -> RED. Catches attempts to override the
//    system policy through the action payload itself.
const INJECTION_PATTERNS = [
  /ignore\s+(all\s+)?previous\s+instructions/i,
  /disregard\s+(the\s+)?(system|above|prior)/i,
  /you\s+are\s+now\s+(dan|in\s+developer\s+mode)/i,
  /\bdo\s+anything\s+now\b/i,
  /override\s+(the\s+)?security/i,
  /reveal\s+(your\s+)?(system\s+)?prompt/i,
];

// 5. Secret patterns -> RED. A literal credential in a payload must never run.
const SECRET_PATTERNS = [
  /sk-[a-zA-Z0-9]{48}/,
  /(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}/,
  /(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}/,
];

// --- Per-session rate limiter for sensitive (YELLOW+) actions ---
const MAX_SENSITIVE_PER_SESSION = 3;
const sessionCounters = new Map();

export function resetRateLimiter(sessionId = null) {
  if (sessionId) sessionCounters.delete(sessionId);
  else sessionCounters.clear();
}

function recordSensitive(sessionId) {
  if (!sessionId) return 1;
  const n = (sessionCounters.get(sessionId) || 0) + 1;
  sessionCounters.set(sessionId, n);
  return n;
}

/**
 * Deterministically classify a command into a security zone.
 * @param {string} command
 * @returns {{ zone: string, confidence: number, reason: string }}
 */
export function classify(command) {
  try {
    if (!command || typeof command !== 'string' || !command.trim()) {
      return { zone: Zone.RED, confidence: 1.0, reason: 'Empty/invalid command (fail-closed).' };
    }

    for (const p of INJECTION_PATTERNS) {
      if (p.test(command)) {
        return { zone: Zone.RED, confidence: 1.0, reason: `Prompt-injection pattern detected: ${p}` };
      }
    }
    for (const p of SECRET_PATTERNS) {
      if (p.test(command)) {
        return { zone: Zone.RED, confidence: 1.0, reason: 'Hardcoded secret/credential detected in payload.' };
      }
    }
    for (const p of RED_PATTERNS) {
      if (p.test(command)) {
        return { zone: Zone.RED, confidence: 1.0, reason: `Destructive command blocked: ${p}` };
      }
    }
    for (const p of NETWORK_PATTERNS) {
      if (p.test(command)) {
        return { zone: Zone.RED, confidence: 1.0, reason: `Network egress blocked: ${p}` };
      }
    }

    // Path traversal / out-of-scope file access -> RED.
    const scope = commandStaysInScope(command);
    if (!scope.inScope) {
      return { zone: Zone.RED, confidence: 1.0, reason: `Scope violation: ${scope.reason}` };
    }

    for (const p of YELLOW_PATTERNS) {
      if (p.test(command)) {
        return { zone: Zone.YELLOW, confidence: 0.9, reason: `Caution operation requires approval: ${p}` };
      }
    }

    return { zone: Zone.GREEN, confidence: 1.0, reason: 'No dangerous patterns; within scope.' };
  } catch (e) {
    // Fail-closed: any classifier exception defaults to RED, never permissive.
    return { zone: Zone.RED, confidence: 1.0, reason: `Fail-closed on classifier exception: ${e.message}` };
  }
}

/**
 * Validate an AI intent. Backward-compatible with the existing server contract
 * ({ status, reason }) while also exposing the resolved zone.
 * @param {string} command
 * @param {{ sessionId?: string }} [opts]
 * @returns {{ status: 'ALLOW'|'BLOCK'|'REQUIRE_HUMAN', reason: string, zone: string }}
 */
export function validateCommand(command, opts = {}) {
  const { zone, reason } = classify(command);

  if (zone === Zone.RED) {
    return { status: 'BLOCK', reason: `[SECURITY BLOCK] ${reason}`, zone };
  }

  if (zone === Zone.YELLOW) {
    const count = recordSensitive(opts.sessionId);
    if (count > MAX_SENSITIVE_PER_SESSION) {
      return {
        status: 'BLOCK',
        reason: `[RATE LIMIT] ${MAX_SENSITIVE_PER_SESSION} sensitive actions already used this session. Human re-authorisation required.`,
        zone: Zone.RED,
      };
    }
    return { status: 'REQUIRE_HUMAN', reason: `[AUTHORIZATION REQUIRED] ${reason}`, zone };
  }

  return { status: 'ALLOW', reason: 'Command passed security gateway.', zone };
}
