#Requires -Version 5.1
<#
.SYNOPSIS
    One-command Windows installer for GAGOS.

.DESCRIPTION
    Creates a Python virtual environment, installs the locked dependencies,
    creates a template .env file if missing, creates the local data directory,
    and runs the bootstrap health check.

.PARAMETER SkipBootstrap
    Skip the final `python -m aios bootstrap` health check.

.EXAMPLE
    .\install.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $repoRoot

try {
    if (-not (Test-Command python)) {
        if (Test-Command py) {
            $pythonCmd = "py"
        } else {
            Write-Error "Python is not installed or not on PATH. Install Python >= 3.11 and retry."
        }
    } else {
        $pythonCmd = "python"
    }

    Write-Step "Checking Python version..."
    $pyVersion = & $pythonCmd --version 2>&1
    Write-Host "Found $pyVersion"

    $venvPath = Join-Path $repoRoot ".venv"
    if (-not (Test-Path $venvPath)) {
        Write-Step "Creating virtual environment at .venv ..."
        & $pythonCmd -m venv .venv
    } else {
        Write-Step "Virtual environment .venv already exists"
    }

    $pip = Join-Path $venvPath "Scripts\python.exe"
    Write-Step "Upgrading pip..."
    & $pip -m pip install --upgrade pip

    Write-Step "Installing locked dependencies (this may take a few minutes)..."
    & $pip -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        # MEASURED 2026-09-07 on a fresh-clone run: pip died with an OSError
        # (a Windows MAX_PATH overrun inside torch's headers) and this script
        # carried on, wrote the .env, and printed "Installation complete."
        # with exit 0. `bootstrap` correctly reported eight missing packages
        # -- and that was a WARNING, so anything automating this saw success.
        #
        # An installer that reports success on a failed install is worse than
        # one that crashes: the crash is honest.
        throw "Dependency installation FAILED (pip exit $LASTEXITCODE). The install is incomplete -- do not start the server. Scroll up for pip's error. On Windows a long repository path can exceed MAX_PATH; try a shorter one such as C:\src\ai-editor, or enable LongPathsEnabled."
    }

    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envPath)) {
        Write-Step "Creating template .env file..."
        # ONE template, shared with `python -m aios bootstrap --create-env`.
        # This script used to keep its own copy, and that copy omitted
        # AIOS_VERIFICATION_AUTHORITY_KEY -- the value the README calls the one
        # genuinely required setting, and the key whose absence killed cohort
        # 27. Two templates could drift; one cannot.
        & $pip -c "from pathlib import Path; from aios.bootstrap import write_env_template; write_env_template(Path(r'$envPath'))"
    } else {
        Write-Step ".env already exists; skipped"
    }

    $dataPath = Join-Path $repoRoot "data"
    if (-not (Test-Path $dataPath)) {
        Write-Step "Creating data directory..."
        New-Item -ItemType Directory -Path $dataPath | Out-Null
    } else {
        Write-Step "data directory already exists"
    }

    if (-not $SkipBootstrap) {
        Write-Step "Running bootstrap health check..."
        & $pip -m aios bootstrap
        if ($LASTEXITCODE -ne 0) {
            # Also fatal. A failing bootstrap means a required check did not
            # pass -- the same run that exposed the pip bug above reported
            # "Missing packages: boto3, cryptography, fastapi, ..." and still
            # exited 0.
            throw "Bootstrap health check FAILED. The install is not usable as it stands; fix the blocking checks above before starting the server."
        }
    }

    Write-Step "Installation complete."
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Green
    Write-Host "  1. Edit .env if you need a real API token or different Ollama URL."
    Write-Host "  2. Start the API: .venv\Scripts\python -m aios"
    Write-Host "  3. Start the UI:  cd frontend; npm run dev"
    Write-Host ""
    # `install.sh` has printed this since the clean-box run and this script did
    # not, so a Windows newcomer was never told the diagnostic exists. `doctor`
    # checks RUNTIME health -- audit chain, backups, model runtime, executor --
    # which is a different question from `bootstrap`'s install-time checks.
    Write-Host "  Diagnose: .venv\Scripts\python -m aios doctor"
} finally {
    Pop-Location
}
