# Faz 1 ortam kurulumu — RTX 5060 Ti (Blackwell, 16GB VRAM), Windows 11
# Kullanim: powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Set-Location $root

Write-Host "== venv olusturuluyor ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$pip = ".\.venv\Scripts\pip.exe"
$python = ".\.venv\Scripts\python.exe"

Write-Host "== pip guncelleniyor ==" -ForegroundColor Cyan
& $python -m pip install --upgrade pip

Write-Host "== PyTorch (CUDA 12.8 / Blackwell sm_120 destekli) kuruluyor ==" -ForegroundColor Cyan
& $pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "== proje bagimliliklari kuruluyor ==" -ForegroundColor Cyan
& $pip install -r requirements.txt

Write-Host "== dogrulama: CUDA gorunur mu? ==" -ForegroundColor Cyan
& $python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'yok')"

Write-Host ""
Write-Host "Kurulum tamamlandi. Sonraki adimlar:" -ForegroundColor Green
Write-Host "  1) .env.example dosyasini .env olarak kopyala, ANTHROPIC_API_KEY doldur"
Write-Host "  2) assets/voice_reference/sample.wav olustur (10-30sn temiz ses ornegi)"
Write-Host "  3) secrets/youtube_client_secret.json dosyasini Google Cloud Console'dan indir"
Write-Host "  4) .venv\Scripts\python.exe -m pipeline.orchestrator --skip-upload  (ilk test icin)"
