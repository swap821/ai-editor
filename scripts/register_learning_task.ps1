<#
.SYNOPSIS
    Register the unattended learning drive with Windows Task Scheduler.

.DESCRIPTION
    THE OPERATOR RUNS THIS, not an agent. Registering a scheduled task changes
    machine configuration and creates something that will run on its own long
    after the session that made it ended; that is a decision, not a step.

    What it schedules is deliberately modest: the LOCAL clerk ladder only. No
    credentials, no cloud spend, nothing leaves the machine. Cloud tiers stay
    opt-in by passing -Models when you want them, and the drive's own lock
    means a firing that lands while a run is live skips instead of colliding.

    Run with -WhatIf first to see exactly what would be registered.

.PARAMETER Time
    Daily start time, 24h (default 03:20). Deliberately not on the hour: this
    machine is not the only thing with a schedule.

.PARAMETER Cycles
    Learning cycles per firing (default 2). A cycle is roughly 5-10 minutes on
    the local 7B.

.PARAMETER Models
    Ladder to drive, weakest first. Defaults to the local clerk alone.

.EXAMPLE
    pwsh -File scripts/register_learning_task.ps1 -WhatIf
    pwsh -File scripts/register_learning_task.ps1
    pwsh -File scripts/register_learning_task.ps1 -Time 02:40 -Cycles 3

.EXAMPLE
    # Remove it again
    Unregister-ScheduledTask -TaskName 'GAGOS Learning Drive' -Confirm:$false
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Time = '03:20',
    [int]$Cycles = 2,
    [string]$Models = 'ollama.qwen2.5-coder:7b',
    [string]$TaskName = 'GAGOS Learning Drive'
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$driver = Join-Path $repo 'tools\learning_drive.py'

foreach ($required in @($python, $driver)) {
    if (-not (Test-Path $required)) {
        throw "missing: $required — run this from a checkout with its .venv built"
    }
}

# Fail early and loudly rather than registering a task that can never work:
# a schedule whose first firing dies at 03:20 is a schedule nobody notices is
# broken, which is the failure mode this whole effort exists to end.
& $python -c "import sys; sys.path.insert(0, r'$repo'); import tools.learning_drive" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "the driver does not import cleanly; fix that before scheduling it"
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-u `"$driver`" --cycles $Cycles --models `"$Models`"" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

# StartWhenAvailable: a laptop that was asleep at 03:20 should still run the
# drive when it wakes, or the trend quietly becomes "whenever the machine
# happened to be on", which is not a trend.
# DontStopOnIdleEnd / no ExecutionTimeLimit cap: the drive enforces its OWN
# wall-clock budget and its own lock, and a scheduler-level kill would leave a
# half-finished cycle with no summary row.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::FromHours(4))

if ($PSCmdlet.ShouldProcess($TaskName, "register daily at $Time ($Cycles cycle(s), $Models)")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description 'Drives the GAGOS learning loop against its own source, locally. Local models only unless -Models says otherwise.' `
        -Force | Out-Null

    Write-Output "registered '$TaskName' — daily at $Time, $Cycles cycle(s), ladder: $Models"
    Write-Output ""
    Write-Output "  inspect : Get-ScheduledTask -TaskName '$TaskName'"
    Write-Output "  run now : Start-ScheduledTask -TaskName '$TaskName'"
    Write-Output "  remove  : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
    Write-Output "  results : .aios/audit/learning-drive.jsonl  and  scripts/learning_scoreboard.py --check"
}
