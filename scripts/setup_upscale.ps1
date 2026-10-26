# Real-ESRGAN (+ GFPGAN/CodeFormer yüz restorasyonu) kurulumu — final video/görsel upscale.
# 960x544 render -> keskin 1080p, ve avatar yüzü restorasyonu. İzole venv.
# Çalıştırma: scripts/run_upscale.py (video karelerini upscale eder).
# !! Blackwell (RTX 50xx) -> torch cu128.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\Real-ESRGAN"

Write-Host "1) Real-ESRGAN repo klonlanıyor -> $vendor"
if (-not (Test-Path $vendor)) {
    git clone https://github.com/xinntao/Real-ESRGAN $vendor
}

Write-Host "2) İzole venv (Python 3.10)"
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "3) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "4) basicsr / realesrgan / gfpgan kuruluyor"
& $vpy -m pip install basicsr facexlib gfpgan
Push-Location $vendor
try {
    & $vpy -m pip install -r requirements.txt
    & $vpy setup.py develop
} finally { Pop-Location }

Write-Host ""
Write-Host "!! BİLİNEN SORUN: basicsr, torchvision>=0.17'de 'functional_tensor' import hatası verir." -ForegroundColor Yellow
Write-Host "   Fix: site-packages\basicsr\data\degradations.py içinde"
Write-Host "   'torchvision.transforms.functional_tensor' -> 'torchvision.transforms.functional' yap."
Write-Host ""
Write-Host "BITTI. Test: vendor\Real-ESRGAN\.venv\Scripts\python.exe vendor\Real-ESRGAN\inference_realesrgan.py -n RealESRGAN_x2plus -i <görsel> --face_enhance" -ForegroundColor Green
