#!/usr/bin/env bash
# =============================================================================
# aios-resume.sh  —  Supervised auto-resume for Claude Code (Git Bash / WSL / macOS / Linux)
# -----------------------------------------------------------------------------
# Windows users: prefer aios-resume.ps1 (native PowerShell). This bash version is
# for Git Bash / WSL. Behaviour is identical.
#
# WHY THIS EXISTS: a prompt cannot watch the clock or relaunch Claude Code; that
# logic lives outside the model. This is that logic.
#
# SAFETY: NEVER passes --dangerously-skip-permissions. Approvals stay ON. It
# resumes context + the plan; a human approves every edit/install/delete.
#
# USAGE:
#   ./aios-resume.sh           # check once; resume if ready, else print + exit
#   ./aios-resume.sh --wait    # poll until the window resets
# =============================================================================
set -euo pipefail

PROJECT_DIR="${AIOS_PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
STATE_DIR="$PROJECT_DIR/.aios/state"
SID_FILE="$STATE_DIR/last_session_id"
RESUME_PROMPT="${AIOS_RESUME_PROMPT:-Run the Session Bootstrap Protocol from AGENTS.md. Also run python agent_coord.py brief --agent claude and surface any inbox/handoff item. Read .aios/state/RESUME.md, summarise where we left off in one short paragraph, then present the single next step for my approval. Do NOT execute YELLOW or RED actions yet.}"

WAIT=false
RETRY_SECONDS="${AIOS_RETRY_SECONDS:-900}"
MAX_RETRIES="${AIOS_MAX_RETRIES:-96}"
LAST_MSG=""
LIMIT_PATTERN='usage limit|rate limit|limit reached|reset|try again later|out of (usage|capacity)'

for arg in "$@"; do
  case "$arg" in
    --wait) WAIT=true ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "[aios-resume] unknown arg: $arg"; exit 2 ;;
  esac
done

mkdir -p "$STATE_DIR"
command -v claude >/dev/null 2>&1 || { echo "[aios-resume] 'claude' CLI not found on PATH."; exit 127; }

probe_available() {
  local out
  if out="$(claude -p 'reply with exactly: OK' 2>&1)"; then
    if printf '%s' "$out" | grep -qiE "$LIMIT_PATTERN"; then LAST_MSG="$out"; return 1; fi
    return 0
  else
    LAST_MSG="$out"; return 1
  fi
}

resume_session() {
  local sid=""
  [ -f "$SID_FILE" ] && sid="$(cat "$SID_FILE" 2>/dev/null || true)"
  echo "[aios-resume] Usage window available. Resuming Claude Code (approvals ON)..."
  if [ -n "$sid" ]; then
    exec claude --resume "$sid" "$RESUME_PROMPT"
  else
    local first
    first="$(claude -c -p "$RESUME_PROMPT" --output-format json 2>/dev/null || true)"
    printf '%s' "$first" | grep -oE '"session_id"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 \
      | sed -E 's/.*"([^"]+)"$/\1/' > "$SID_FILE" 2>/dev/null || true
    exec claude -c
  fi
}

attempt=0
while true; do
  if probe_available; then resume_session; fi
  echo "[aios-resume] Usage window NOT yet available."
  [ -n "$LAST_MSG" ] && { echo "----- message from Claude -----"; echo "$LAST_MSG"; echo "-------------------------------"; }
  if ! $WAIT; then
    echo "[aios-resume] Re-run with --wait to poll until reset, or try again later."
    exit 0
  fi
  attempt=$((attempt + 1))
  [ "$attempt" -ge "$MAX_RETRIES" ] && { echo "[aios-resume] Gave up after $attempt attempts."; exit 1; }
  echo "[aios-resume] Waiting ${RETRY_SECONDS}s, then retry ($attempt/$MAX_RETRIES)..."
  sleep "$RETRY_SECONDS"
done
