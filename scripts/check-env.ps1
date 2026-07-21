# check-env.ps1 - Validate AI-OS environment prerequisites

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "       AI-OS Environment Diagnostics         " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

$AllPassed = $true

# 1. Check Python & Virtual Environment
Write-Host "`n[1/4] Checking Python & Virtual Environment..." -ForegroundColor Yellow
$VenvPython = ".\.venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PyVersion = & $VenvPython --version 2>&1
    Write-Host "  [OK] Virtual Environment Python found: $PyVersion" -ForegroundColor Green
} else {
    Write-Host "  [WARN] .venv python not found at $VenvPython." -ForegroundColor Red
    Write-Host "         Run: uv venv && uv pip install -e ." -ForegroundColor Gray
    $AllPassed = $false
}

# 2. Check Docker Daemon
Write-Host "`n[2/4] Checking Docker Daemon..." -ForegroundColor Yellow
try {
    $DockerStatus = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Docker daemon is running and reachable." -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Docker daemon unreachable (local pipe / socket unavailable)." -ForegroundColor Yellow
        Write-Host "         Isolated Docker execution will fallback or fail closed." -ForegroundColor Gray
    }
} catch {
    Write-Host "  [WARN] Docker CLI not installed or not in PATH." -ForegroundColor Yellow
}

# 3. Check Node.js & npm
Write-Host "`n[3/4] Checking Node.js & npm..." -ForegroundColor Yellow
try {
    $NodeVer = node --version 2>&1
    $NpmVer = npm --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Node.js ($NodeVer) & npm ($NpmVer) available." -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Node.js or npm command failed." -ForegroundColor Red
        $AllPassed = $false
    }
} catch {
    Write-Host "  [FAIL] Node.js is not installed or not in PATH." -ForegroundColor Red
    $AllPassed = $false
}

# 4. Check AI-OS Environment Variables & Config
Write-Host "`n[4/4] Checking AI-OS Configuration Keys..." -ForegroundColor Yellow
$EnvKeys = @("AIOS_API_HOST", "AIOS_API_PORT", "AIOS_API_TOKEN")
foreach ($Key in $EnvKeys) {
    $Val = [System.Environment]::GetEnvironmentVariable($Key)
    if ($Val) {
        Write-Host "  [OK] $Key is set." -ForegroundColor Green
    } else {
        Write-Host "  [INFO] $Key is not explicitly set (will use default)." -ForegroundColor DarkGray
    }
}

Write-Host "`n=============================================" -ForegroundColor Cyan
if ($AllPassed) {
    Write-Host "  [SUCCESS] Environment check passed!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "  [WARNING] Some optional/required components need attention." -ForegroundColor Yellow
    exit 1
}
