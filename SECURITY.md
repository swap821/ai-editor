# Security Policy

## Supported Versions

This project is pre-1.0. Only the latest commit on `main` receives security
fixes. There are no backported patch branches.

| Branch | Supported |
| ------ | --------- |
| `main` (latest) | Yes |
| Anything else | No |

## Reporting a Vulnerability

If you discover a security issue, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Use [GitHub Security Advisories](../../security/advisories/new) to file a
   private report, or email the maintainer directly.
3. Include: affected component, reproduction steps, and impact assessment.
4. You can expect an initial response within 72 hours and a fix timeline within
   7 days for confirmed issues.

## Security Architecture

AIOS enforces defense-in-depth across multiple layers:

### Execution Sandbox

- **Zone classification** (`aios/security/gateway.py`): Every command is
  deterministically classified into a security zone (GREEN/YELLOW/RED) before
  execution. RED-zone commands are blocked unconditionally.
- **Scope lock** (`aios/security/scope_lock.py`): File-system access is
  confined to the declared workspace. Path traversal is rejected at the gateway.
- **Approval-gated execution** (`aios/core/approvals.py`): Destructive or
  elevated actions require an explicit human approval token (HMAC-signed,
  single-use, session-bound) before they can proceed.

### Tamper-Evident Audit Chain

- **Ed25519-signed audit log** (`aios/security/audit_logger.py`): Every
  significant action is appended to a hash-chained log. Each entry carries a
  cryptographic signature (Ed25519, key in memory only) and references the hash
  of the previous entry, so any insertion, deletion, or modification is
  detectable.
- **Chain verification** exposed via `GET /api/v1/audit/verify`.

### Secret Handling

- API keys and signing keys live only in volatile environment variables — never
  persisted to disk, logs, or the `.aios/` data directory.
- `aios/security/secret_scanner.py` scans outbound content for accidental key
  leakage before it reaches any LLM provider.

### LLM Safety

- **Prompt-injection shield** (`aios/security/injection_shield.py`): **user
  input only** — the chat message and the voice transcript. These are the only
  two call sites of `_check_prompt_injection` (`aios/api/main.py:1215`, `:1456`),
  and `classify()` / `is_injection()` appear nowhere outside `aios/security/*`
  and those handlers.

  **Tool output is NOT scanned for injection.** File content returned by
  `read_file` and command stdout/stderr pass through the *secret* scanner
  (`scan_and_redact`) only, and are appended to the model's context at
  `aios/agents/tool_agent.py:1264` without ever reaching the injection gate.
  An instruction planted in a file the agent reads is therefore not detected
  today.

  This entry previously read "User and tool output is scanned", which was
  false. Corrected 2026-09-03 after organ 55's M3 mission was written to measure
  precisely this gap; the mission is expected to FAIL until the gap is closed,
  and it is recorded as a ledger blocker rather than a footnote here.
- **Privacy filter** on all cloud LLM drivers: sensitive tokens are stripped
  before transmission; the local-first router default (`ROUTER_CLOUD_TASKS=()`)
  ensures nothing leaves the machine unless explicitly opted in.

### Foundation Lock

The following files constitute the security spine and must never be modified
outside of a dedicated, reviewed security PR:

- `aios/security/*`
- `aios/core/executor.py`
- `aios/core/approvals.py`
- `aios/core/verifier.py`
- `aios/core/self_apply.py`

## Scope

The following are **in scope** for security reports:

- Sandbox escapes (command execution outside declared zone/scope)
- Approval bypass (executing without a valid token)
- Audit chain forgery or silent truncation
- Secret leakage to logs, disk, or external services
- Prompt-injection vectors that bypass the shield

The following are **out of scope**:

- Denial of service against the local development server
- Issues requiring physical access to the host machine
- Vulnerabilities in upstream dependencies (report to them directly)
