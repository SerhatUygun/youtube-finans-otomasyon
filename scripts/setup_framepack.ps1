# FramePack (lllyasviel) kurulumu — uzun i2v, SABİT ~6GB VRAM (uzunluktan bağımsız).
# LTX/Wan'ın uzunluk+hız sınırını çözer. İzole venv. RTX 30/40/50xx desteklenir.
# !! Blackwell (RTX 50xx) -> torch cu128.
# Çalıştırma: scripts/run_framepack.py (bkz. o dosya) — statik görseli video'ya çevirir.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\FramePack"

Write-Host "1) FramePack repo klonlanıyor -> $vendor"
if (-not (Test-Path $vendor)) {
    git clone https://github.com/lllyasviel/FramePack $vendor
}

Write-Host "2) İzole venv (Python 3.10)"
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) { py -3.10 -m venv $venv }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel

Write-Host "3) PyTorch (Blackwell -> cu128)"
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "4) FramePack bağımlılıkları (requirements.txt) — Gradio arayüzü için"
Push-Location $vendor
try {
    & $vpy -m pip install -r requirements.txt
} finally { Pop-Location }

Write-Host "5) run_framepack.py'nin RESMİ diffusers rotası için güncel diffusers"
# run_framepack.py, repo'nun kararsız iç API'si yerine diffusers'ın resmi
# HunyuanVideoFramepackPipeline'ını kullanır -> güncel diffusers/transformers şart.
& $vpy -m pip install -U diffusers transformers accelerate sentencepiece imageio imageio-ffmpeg av

Write-Host ""
Write-Host "BITTI. Modeller (HunyuanVideo tabanı ~30GB) İLK çalıştırmada otomatik iner." -ForegroundColor Green
Write-Host "Batch kullanım (RESMİ diffusers rotası, önerilen):"
Write-Host "  vendor\FramePack\.venv\Scripts\python.exe scripts\run_framepack.py --image <png> --prompt `"<hareket>`" --seconds 5 --out <mp4>"
Write-Host "Alternatif (Gradio arayüzü): vendor\FramePack\.venv\Scripts\python.exe vendor\FramePack\demo_gradio.py"
