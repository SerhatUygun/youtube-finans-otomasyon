# VoxCPM2 setup - 30-language (incl. Turkish) zero-shot voice cloning, 48kHz output (isolated venv).
# s02_tts.py calls scripts/run_voxcpm.py via subprocess when tts.engine=voxcpm.
# Blackwell (RTX 50xx) -> torch cu128. ~8GB VRAM. Model (openbmb/VoxCPM2) downloads on first run.
#
# NOTE: 'Continue' (not 'Stop') on purpose. pip writes progress to stderr; under 'Stop'
# PowerShell 5.1 treats that as fatal. We gate on $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\VoxCPM"

Write-Host "1) Isolated venv (Python 3.10) -> $vendor\.venv"
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "2) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: torch install failed"; exit 1 }

Write-Host "3) voxcpm + soundfile"
& $vpy -m pip install voxcpm soundfile
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: voxcpm install failed"; exit 1 }

# voxcpm may pull a CPU-only torch from PyPI as a dependency; re-pin the cu128 build.
& $vpy -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   torch lost CUDA after voxcpm install -> reinstalling cu128 build"
    & $vpy -m pip install --force-reinstall --no-deps torch torchaudio --index-url https://download.pytorch.org/whl/cu128
}

Write-Host "4) Download model weights (openbmb/VoxCPM2)"
& $vpy -c "from huggingface_hub import snapshot_download; print(snapshot_download('openbmb/VoxCPM2'))"

Write-Host ""
Write-Host "DONE. Test:" -ForegroundColor Green
Write-Host "  vendor\VoxCPM\.venv\Scripts\python.exe scripts\run_voxcpm.py --ref assets\voice_reference\sample.wav --text 'Merhaba, bu bir testtir.' --out output\_voxcpm_test\test.wav"
Write-Host "  If the voice is good -> config.yaml tts.engine: voxcpm"
