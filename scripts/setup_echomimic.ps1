# EchoMimic V2 setup - audio-driven half-body presenter (isolated venv).
# s03_avatar.py calls it via subprocess when avatar.engine=echomimic.
#
# BLACKWELL NOTE: EchoMimic V2 pins torch==2.5.1, which does NOT support RTX 50xx (sm_120).
# This script installs torch cu128 (2.7+) instead. The diffusers-based pipeline generally
# works on newer torch, but this override is UNVERIFIED - validate the first render.

# NOTE: 'Continue' (not 'Stop') on purpose. git/pip write normal progress to stderr;
# under 'Stop' PowerShell 5.1 treats that as a fatal error. We gate on $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\EchoMimicV2"

Write-Host "1) Cloning repo -> $vendor"
if ((Test-Path $vendor) -and -not (Test-Path (Join-Path $vendor ".git"))) {
    Write-Host "   (removing incomplete clone)"
    Remove-Item -Recurse -Force $vendor
}
if (-not (Test-Path $vendor)) {
    git clone https://github.com/antgroup/echomimic_v2.git $vendor
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: git clone failed"; exit 1 }
} else {
    Write-Host "   (already present, skipping clone)"
}

$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "2) PyTorch (Blackwell -> cu128, overriding the repo's torch==2.5.1 pin)"
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "3) EchoMimic deps (EXCLUDING torch pins - installed above)"
$req = Join-Path $vendor "requirements.txt"
$tmp = Join-Path $env:TEMP "echo_req_filtered.txt"
if (Test-Path $req) {
    Get-Content $req | Where-Object { $_ -notmatch "^torch|^torchvision|^torchaudio" } | Set-Content -Encoding utf8 $tmp
    & $vpy -m pip install -r $tmp
}
& $vpy -m pip install huggingface_hub

Write-Host "4) Downloading EchoMimic V2 weights (BadToBest/EchoMimicV2, several GB)"
$weights = Join-Path $vendor "pretrained_weights"
$dl = Join-Path $root "scripts\download_echomimic.py"
& $vpy $dl $weights

Write-Host ""
Write-Host "SETUP_COMPLETE_ECHOMIMIC"
Write-Host "Next: validate infer_acc.py config against a test render."
