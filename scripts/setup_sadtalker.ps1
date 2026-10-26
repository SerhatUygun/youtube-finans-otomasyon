# Faz 2 — SadTalker kurulumu (konuşan karakter).
# Ana pipeline venv'inden (Python 3.12, güncel PyTorch) BAĞIMSIZ, izole bir Python 3.10
# venv'inde kurar; çünkü SadTalker'ın bağımlılıkları (numpy==1.23.4 vb.) yeni Python/
# paket sürümleriyle çakışıyor.
#
# Kullanım: powershell -ExecutionPolicy Bypass -File scripts\setup_sadtalker.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendorDir = Join-Path $root "vendor"
$repoDir = Join-Path $vendorDir "SadTalker"

New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null

Write-Host "== Python 3.10 kontrol ediliyor ==" -ForegroundColor Cyan
$py310 = "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python310\python.exe"
if (-not (Test-Path $py310)) {
    Write-Host "Python 3.10 kuruluyor (winget)..." -ForegroundColor Yellow
    winget install --id Python.Python.3.10 -e --accept-source-agreements --accept-package-agreements --silent
}

Write-Host "== SadTalker repo klonlanıyor ==" -ForegroundColor Cyan
if (-not (Test-Path $repoDir)) {
    git clone --depth 1 https://github.com/OpenTalker/SadTalker.git $repoDir
}

Set-Location $repoDir

Write-Host "== izole venv oluşturuluyor ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv310")) {
    & $py310 -m venv .venv310
}
$pip = ".\.venv310\Scripts\pip.exe"
$python = ".\.venv310\Scripts\python.exe"

Write-Host "== PyTorch (cu128) kuruluyor ==" -ForegroundColor Cyan
& $python -m pip install --upgrade pip
& $pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "== SadTalker bağımlılıkları kuruluyor ==" -ForegroundColor Cyan
& $pip install -r requirements.txt

Write-Host "== torchvision uyumluluk shim'i uygulanıyor ==" -ForegroundColor Cyan
# basicsr/gfpgan yeni torchvision'da kaldırılmış functional_tensor modülünü import ediyor.
$shimPath = ".venv310\Lib\site-packages\torchvision\transforms\functional_tensor.py"
$shimContent = @"
from torchvision.transforms._functional_tensor import *  # noqa: F401,F403
from torchvision.transforms._functional_tensor import rgb_to_grayscale  # noqa: F401
"@
Set-Content -Path $shimPath -Value $shimContent -Encoding UTF8

Write-Host "== checkpoint'ler indiriliyor ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "checkpoints" | Out-Null
$files = @(
    "mapping_00109-model.pth.tar",
    "mapping_00229-model.pth.tar",
    "SadTalker_V0.0.2_256.safetensors",
    "SadTalker_V0.0.2_512.safetensors"
)
foreach ($f in $files) {
    $dest = "checkpoints\$f"
    if (-not (Test-Path $dest) -or (Get-Item $dest).Length -lt 1000) {
        Write-Host "İndiriliyor: $f"
        curl.exe -L --speed-limit 20000 --speed-time 20 --retry 5 --retry-delay 3 `
            -o $dest "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/$f"
    }
}

Write-Host "== BFM_Fitting indiriliyor (3DMM model dosyaları) ==" -ForegroundColor Cyan
if (-not (Test-Path "checkpoints\BFM_Fitting")) {
    curl.exe -L --retry 3 -o "checkpoints\BFM_Fitting.zip" `
        "https://github.com/Winfredy/SadTalker/releases/download/v0.0.2/BFM_Fitting.zip"
    Expand-Archive -Path "checkpoints\BFM_Fitting.zip" -DestinationPath "checkpoints" -Force
}

Write-Host "== checkpoint bütünlüğü doğrulanıyor ==" -ForegroundColor Cyan
& $python -c "
import safetensors.torch as st
for f in ['checkpoints/SadTalker_V0.0.2_256.safetensors', 'checkpoints/SadTalker_V0.0.2_512.safetensors']:
    d = st.load_file(f)
    print(f, 'OK', len(d), 'tensors')
"

Set-Location $root
Write-Host ""
Write-Host "SadTalker kurulumu tamamlandı." -ForegroundColor Green
Write-Host "Sonraki adım: assets\avatar\photo.png dosyasını ekle (net, önden çekilmiş fotoğraf)."
