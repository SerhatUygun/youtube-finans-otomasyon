# F5-TTS kurulumu — daha doğal + temiz ses klonlama (izole venv).
# XTTS'in (Coqui kapandı, 2024) alternatifi. s02_tts.py engine=f5tts ile subprocess çağırır.
# !! Blackwell (RTX 50xx) -> torch cu128 (F5 resmi cu118/cu121 der; Blackwell'de cu128 şart).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\F5-TTS"

Write-Host "1) İzole venv (Python 3.10) -> $vendor\.venv"
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "2) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "3) F5-TTS kuruluyor (pip paketi -> f5-tts_infer-cli + f5_tts modülü)"
& $vpy -m pip install f5-tts

Write-Host ""
Write-Host "BITTI. Sonraki adımlar:" -ForegroundColor Green
Write-Host "  a) config.yaml -> tts.f5_ref_text = assets/voice_reference/sample.wav'daki sözlerin BİREBİR metni"
Write-Host "  b) Test (modeller ilk çalışmada iner):"
Write-Host '       vendor\F5-TTS\.venv\Scripts\python.exe -m f5_tts.infer.infer_cli --model F5TTS_v1_Base --ref_audio assets\voice_reference\sample.wav --ref_text "<referans metni>" --gen_text "Merhaba, bu bir testtir." --output_dir output\_f5test --output_file test.wav'
Write-Host "  c) Ses iyiyse config.yaml -> tts.engine: f5tts"
