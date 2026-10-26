# Faz 4 — Windows Görev Zamanlayıcı entegrasyonu.
# topics.json kuyruğundaki bekleyen konuları belirlenen saatte otomatik işler.
# Güvenlik: YouTube'a yükleme kapalı (--auto-upload verilmedi) — video output/ klasöründe
# insan onayı bekler; onay/yükleme web arayüzünden (http://127.0.0.1:8000) yapılır.
#
# Kullanım:
#   powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1 -Time "04:00" -TaskName "YoutubeBotGunluk"
#   powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1 -Unregister   # görevi kaldır

param(
    [string]$Time = "03:00",
    [string]$TaskName = "YoutubeBotPipeline",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Görev kaldırıldı: $TaskName" -ForegroundColor Yellow
    } else {
        Write-Host "Görev zaten yok: $TaskName" -ForegroundColor Yellow
    }
    exit 0
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "output\_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "scheduled_run.log"

# orchestrator'ı çalıştırıp çıktısını log dosyasına ekleyen küçük bir wrapper .bat,
# çünkü Task Scheduler'da doğrudan yönlendirme (>>) güvenilir çalışmayabiliyor.
$wrapperPath = Join-Path $root "scripts\_scheduled_run.bat"
@"
@echo off
cd /d "$root"
echo ==== %date% %time% ==== >> "$logFile"
"$python" -m pipeline.orchestrator >> "$logFile" 2>&1
"@ | Set-Content -Path $wrapperPath -Encoding ASCII

$action = New-ScheduledTaskAction -Execute $wrapperPath
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 6)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "YouTube icerik pipeline'ini gunluk calistirir (yukleme kapali, onay web arayuzunden)." | Out-Null

Write-Host "Görev kaydedildi: $TaskName (her gün $Time)" -ForegroundColor Green
Write-Host "Log dosyası: $logFile"
Write-Host "Not: video üretimi bittiğinde otomatik YouTube'a YÜKLENMEZ. Onay için web arayüzünü aç:" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\python.exe -m pipeline.web.app"
Write-Host "Görevi kaldırmak için: powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1 -Unregister"
