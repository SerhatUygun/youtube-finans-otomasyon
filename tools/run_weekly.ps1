# Haftalik ekonomi ozeti videosunu TAM DETACHED uretir (Start-Process ile cagrilir -> harness
# arka plan yoneticisinden bagimsiz, coklu-saatlik render kesilmez). tools/run_heroes.ps1 ile
# ayni desen: log dosyasina yonlendirme + tamamlanma flag dosyasi (yoklama ile tespit).
#
# Elle calistirma:
#   powershell -File tools\run_weekly.ps1
# Haftalik otomatik tetikleme icin (orn. Pazartesi 06:00), Windows Gorev Zamanlayici'ya ekle:
#   schtasks /create /tn "YTBot_HaftalikOzet" /tr "powershell -NoProfile -File tools\run_weekly.ps1" /sc weekly /d MON /st 06:00
Set-Location $PSScriptRoot\..
$ErrorActionPreference = "Continue"
$py = ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

Remove-Item output\_logs\weekly_done.flag -ErrorAction SilentlyContinue

& $py tools\make_weekly_video.py --target-words 2000 --job-suffix "$stamp" *> "output\_logs\weekly_$stamp.log"

"WEEKLY_DONE $(Get-Date -Format o)" | Out-File -Encoding utf8 output\_logs\weekly_done.flag
