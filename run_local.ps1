# Echo - local dev launcher (Windows / PowerShell)
#
#   .\run_local.ps1              -> start the backend on http://127.0.0.1:8010
#   .\run_local.ps1 -Port 8000   -> pick a different port
#   .\run_local.ps1 -Setup       -> create .venv, install deps, build dataset, train the model
#
# The backend must be started from the backend/ folder: main.py mounts ./static relative
# to the working directory.

param(
    [int]$Port = 8010,
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if ($Setup -or -not (Test-Path $python)) {
    Write-Host "== Creating virtual environment ==" -ForegroundColor Cyan
    if (-not (Test-Path $python)) { py -3 -m venv (Join-Path $root ".venv") }

    Write-Host "== Installing dependencies ==" -ForegroundColor Cyan
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $root "requirements.txt")

    Write-Host "== Generating synthetic fallback data ==" -ForegroundColor Cyan
    Push-Location (Join-Path $root "model")
    & $python generate_synthetic_data.py

    Write-Host "== Preparing dataset (real ESC-50/UrbanSound8K if present under model/data/raw and model/esc50_temp.zip, synthetic fallback otherwise) ==" -ForegroundColor Cyan
    & $python prepare_dataset.py

    Write-Host "== Training the YAMNet transfer-learning head (CPU, a few minutes) ==" -ForegroundColor Cyan
    & $python train_yamnet.py
    Pop-Location
}

$checkpoint = Join-Path $root "model\checkpoints\yamnet_head.keras"
if (-not (Test-Path $checkpoint)) {
    Write-Error "Model checkpoint missing at $checkpoint. Run: .\run_local.ps1 -Setup"
}

$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Error "Port $Port is already in use (PID $($inUse.OwningProcess)). Re-run with -Port <other>."
}

Write-Host "== Echo backend: http://127.0.0.1:$Port  (API docs at /docs) ==" -ForegroundColor Green
Push-Location (Join-Path $root "backend")
& $python -m uvicorn main:app --host 127.0.0.1 --port $Port
Pop-Location
