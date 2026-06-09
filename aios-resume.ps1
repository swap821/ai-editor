# =============================================================================
# aios-resume.ps1  —  Supervised auto-resume for Claude Code (Windows / PowerShell)
# -----------------------------------------------------------------------------
# WHY THIS EXISTS:
#   A prompt cannot watch the clock or relaunch Claude Code. That logic must live
#   OUTSIDE the model. This is that logic, for Windows.
#
# WHAT IT DOES:
#   1. Probes whether your Claude usage window is currently available.
#   2. If AVAILABLE  -> resumes your last Claude Code session and asks it to run
#                       the Session Bootstrap Protocol from AGENTS.md (read
#                       RESUME.md, summarise, propose the next step for approval).
#   3. If NOT yet    -> prints the usage/reset message and exits (default), or
#                       polls until reset if you pass  -Wait.
#
# SAFETY (this matters):
#   This script NEVER passes --dangerously-skip-permissions. Approvals stay ON.
#   It resumes the *context and the plan*; it never auto-executes edits, installs,
#   deletes, or network calls. A human approves those. That is the whole point.
#
# USAGE:
#   ./aios-resume.ps1            # check once; resume if ready, else print + exit
#   ./aios-resume.ps1 -Wait      # poll until the window resets
# =============================================================================
[CmdletBinding()]
param(
    [switch]$Wait,
    [int]$RetrySeconds = 900,   # 15 min
    [int]$MaxRetries  = 96      # ~24h
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
$StateDir   = Join-Path $ProjectDir '.aios/state'
$SidFile    = Join-Path $StateDir 'last_session_id'
$ResumePrompt = 'Run the Session Bootstrap Protocol from AGENTS.md: read .aios/state/RESUME.md, summarise where we left off in one short paragraph, then present the single next step for my approval. Do NOT execute YELLOW or RED actions yet.'

# Update this if Anthropic changes the limit wording. The probe is a heuristic.
$LimitPattern = 'usage limit|rate limit|limit reached|reset|try again later|out of (usage|capacity)'

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "[aios-resume] 'claude' CLI not found on PATH. Install Claude Code first." -ForegroundColor Yellow
    exit 127
}

function Test-WindowAvailable {
    # Cheapest possible call; react to the result. Fail-closed: any limit wording
    # or non-zero exit => treat as NOT available.
    try {
        $out = (claude -p 'reply with exactly: OK' 2>&1 | Out-String)
    } catch {
        $script:LastMsg = "$_"; return $false
    }
    if ($LASTEXITCODE -ne 0)            { $script:LastMsg = $out; return $false }
    if ($out -imatch $LimitPattern)     { $script:LastMsg = $out; return $false }
    return $true
}

function Resume-Session {
    $sid = ''
    if (Test-Path $SidFile) { $sid = (Get-Content $SidFile -Raw).Trim() }
    Write-Host "[aios-resume] Usage window available. Resuming Claude Code (approvals ON)..." -ForegroundColor Green
    if ($sid) {
        & claude --resume $sid $ResumePrompt        # exact-session continuity
    } else {
        # No saved id yet: capture one from JSON, then drop into an interactive session.
        $first = (claude -c -p $ResumePrompt --output-format json 2>$null | Out-String)
        $m = [regex]::Match($first, '"session_id"\s*:\s*"([^"]+)"')
        if ($m.Success) { $m.Groups[1].Value | Set-Content -NoNewline $SidFile }
        & claude -c
    }
}

$attempt = 0
while ($true) {
    if (Test-WindowAvailable) { Resume-Session; break }

    Write-Host "[aios-resume] Usage window NOT yet available." -ForegroundColor Yellow
    if ($script:LastMsg) {
        Write-Host "----- message from Claude -----"
        Write-Host $script:LastMsg.Trim()
        Write-Host "-------------------------------"
    }
    if (-not $Wait) {
        Write-Host "[aios-resume] Re-run with -Wait to poll until reset, or try later."
        Write-Host "[aios-resume] (On Pro, the session window resets ~5 hours after you hit it.)"
        break
    }
    $attempt++
    if ($attempt -ge $MaxRetries) { Write-Host "[aios-resume] Gave up after $attempt attempts."; break }
    Write-Host "[aios-resume] Waiting ${RetrySeconds}s, then retry ($attempt/$MaxRetries)..."
    Start-Sleep -Seconds $RetrySeconds
}
