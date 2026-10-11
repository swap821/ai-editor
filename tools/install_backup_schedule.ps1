# Registers GAGOS's daily backup with Windows Task Scheduler. The operator runs
# this himself: a scheduled task is persistent configuration on his machine.
#
#   powershell -ExecutionPolicy Bypass -File tools\install_backup_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_backup_schedule.ps1 -DataDir C:\gagos-drill\data
#
# It runs `python -m aios backup create --if-stale` once a day. --if-stale makes
# a missed or repeated run harmless: a fresh archive means nothing is written.
# StartWhenAvailable runs a missed backup as soon as the laptop wakes.
# The backup is safe while GAGOS runs: each database is snapshotted through
# SQLite's online backup API (aios/operations/recovery.py, 2026-10-11).
param(
    [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DataDir = "",
    [string]$At = "03:00",
    [string]$TaskName = "GAGOS daily backup"
)
$ErrorActionPreference = "Stop"
$python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "no virtualenv python at $python" }
$backup = "`"$python`" -m aios backup create --if-stale --stale-after-seconds 86400"
$command = if ($DataDir) { "set `"AIOS_DATA_DIR=$DataDir`" && $backup" } else { $backup }
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $command" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "GAGOS: snapshot-consistent backup of the data directory (python -m aios backup create --if-stale)." -Force | Out-Null
Write-Host "Registered '$TaskName' daily at $At."
Write-Host "Run it now once:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then measure:     python tools\production_readiness.py"
