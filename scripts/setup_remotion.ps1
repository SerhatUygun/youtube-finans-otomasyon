# Remotion (React + Chromium render) kurulumu -- animasyonlu piyasa grafigi icin.
# pipeline/stages/s05b_motion_graphics.py bu klasordeki npm bagimliliklarini kullanir.
# GPU gerekmez; sadece Node.js (LTS onerilir) ve npm gerekir.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$remotion = Join-Path $root "remotion"

Write-Host "1) Node.js kontrolu"
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "Node.js bulunamadi. https://nodejs.org adresinden LTS surumu kurup bu scripti tekrar calistir." -ForegroundColor Red
    exit 1
}
node --version

Write-Host "2) npm bagimliliklari kuruluyor -> $remotion"
Push-Location $remotion
try {
    npm install
} finally { Pop-Location }

Write-Host ""
Write-Host "BITTI. config.yaml -> visuals.motion_graphics.enabled: true yaparak acabilirsin." -ForegroundColor Green
Write-Host "Manuel test: npx remotion studio  (remotion/ klasorunden, tarayicida onizleme acar)"
