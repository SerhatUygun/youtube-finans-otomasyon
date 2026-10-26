# MMAudio (Sony AI) kurulumu — videoya/metne uygun arka plan müziği + ambiyans (~6GB VRAM).
# İzole venv. Çalıştırma: scripts/run_mmaudio.py (video.mp4'e ambiyans bed'i mikser).
# !! Blackwell (RTX 50xx) -> torch cu128 (MMAudio README cu118 der; Blackwell'de cu128 şart).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\MMAudio"

Write-Host "1) MMAudio repo klonlanıyor -> $vendor"
if (-not (Test-Path $vendor)) {
    git clone https://github.com/hkchengrex/MMAudio $vendor
}

Write-Host "2) İzole venv (Python 3.10)"
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "3) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "4) MMAudio kuruluyor (editable)"
Push-Location $vendor
try {
    & $vpy -m pip install -e .
} finally { Pop-Location }

Write-Host ""
Write-Host "BITTI. Modeller (large_44k_v2) İLK çalıştırmada otomatik iner." -ForegroundColor Green
Write-Host "Test (metinden ses): vendor\MMAudio\.venv\Scripts\python.exe vendor\MMAudio\demo.py --duration=8 --prompt `"calm ambient background`""
Write-Host "Pipeline kullanımı: python scripts\run_mmaudio.py --video output\<job>\video.mp4 --out <mp4>"
