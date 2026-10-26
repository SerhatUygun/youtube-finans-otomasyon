# CosyVoice2 setup - fluent multilingual zero-shot voice cloning (isolated venv).
# s02_tts.py calls it via subprocess when tts.engine=cosyvoice. Blackwell -> torch cu128.
#
# WINDOWS NOTE: CosyVoice's WeTextProcessing/pynini dependency cannot be built with pip
# on Windows (needs OpenFst). This script SKIPS it; run_cosyvoice.py runs without text
# normalization (Turkish plain text is relatively clean). For full number/abbreviation
# normalization, conda-forge (pynini) or WSL is required.

# NOTE: 'Continue' (not 'Stop') on purpose. git/pip write normal progress to stderr;
# under 'Stop' PowerShell 5.1 treats that as a fatal error. We gate on $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\CosyVoice"

Write-Host "1) Cloning repo (with submodules: third_party/Matcha-TTS) -> $vendor"
if ((Test-Path $vendor) -and -not (Test-Path (Join-Path $vendor ".git"))) {
    Write-Host "   (removing incomplete clone)"
    Remove-Item -Recurse -Force $vendor
}
if (-not (Test-Path $vendor)) {
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git $vendor
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: git clone failed"; exit 1 }
} else {
    Write-Host "   (already present, skipping clone)"
}

$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "2) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "3) CosyVoice deps (EXCLUDING pynini/WeTextProcessing/ttsfrd - Windows incompatible)"
$req = Join-Path $vendor "requirements.txt"
$tmp = Join-Path $env:TEMP "cosy_req_filtered.txt"
if (Test-Path $req) {
    Get-Content $req | Where-Object { $_ -notmatch "pynini|WeTextProcessing|ttsfrd" } | Set-Content -Encoding utf8 $tmp
    & $vpy -m pip install -r $tmp
}
& $vpy -m pip install huggingface_hub modelscope faster-whisper soundfile

Write-Host "4) Downloading CosyVoice2-0.5B model (~1.2GB)"
$model = Join-Path $vendor "pretrained_models\CosyVoice2-0.5B"
$dl = Join-Path $root "scripts\download_cosyvoice.py"
& $vpy $dl $model

Write-Host ""
Write-Host "SETUP_COMPLETE_COSYVOICE"
Write-Host "Test: scripts/run_cosyvoice.py --ref assets/voice_reference/sample.wav --text Merhaba --out output/_cosytest/test.wav"
