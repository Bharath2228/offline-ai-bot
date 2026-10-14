$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python was not found. Install Python 3.11 or newer and try again."
}

if (-not (Test-Path -LiteralPath ".venv")) {
    Write-Host "Creating the local Python environment..."
    python -m venv .venv
}

$pythonExe = Join-Path (Resolve-Path -LiteralPath ".venv").Path "Scripts\python.exe"
$runtimeReady = $false
& $pythonExe -c "import httpx, PySide6" 2>$null
if ($LASTEXITCODE -eq 0) {
    $runtimeReady = $true
}

if (-not $runtimeReady) {
    Write-Host "Installing the desktop runtime (internet is needed once)..."
    & $pythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Error "The desktop runtime could not be installed. Check your connection and try again."
    }
}

Write-Host ""
Write-Host "Opening Keep..."
& $pythonExe app\main.py
