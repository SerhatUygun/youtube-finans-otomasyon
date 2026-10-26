# Gunde 3x otomatik piyasa/haber Shorts uretimi icin Windows Task Scheduler kurulumu.
# Her gorev tools/run_scheduled_short.py --slot <ad> calistirir (bkz. o dosyadaki SLOTS).
# Video HER ZAMAN private yuklenir (config.yaml youtube.privacy_status) -- public'e alma
# karari web panelden insanda kalir (yari-otomatik onay akisi).
#
# Kullanim: PowerShell'i YONETICI olarak ac, sonra:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_scheduled_tasks.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "UYARI: $python bulunamadi, sistem PATH'indeki python kullanilacak." -ForegroundColor Yellow
    $python = "python"
}

# slot adi -> (gorev adi, saat:dakika)
$tasks = @(
    @{ Name = "YoutubeBot_MorningOpen"; Slot = "morning_open"; Time = "10:30" },
    @{ Name = "YoutubeBot_USMarket";    Slot = "us_market";    Time = "15:30" },
    @{ Name = "YoutubeBot_EveningWrap"; Slot = "evening_wrap"; Time = "18:00" }
)

foreach ($t in $tasks) {
    $taskArgs = "-m tools.run_scheduled_short --slot $($t.Slot)"
    Write-Host "Gorev olusturuluyor: $($t.Name) -> gunluk $($t.Time)"

    # schtasks stderr yazsa bile PowerShell'in -Stop moduyla script'i durdurmamasi icin
    # native exe cikis kodu $LASTEXITCODE ile ayrica kontrol edilir (bkz. proje hafizasi:
    # PowerShell setup scripti tuzaklari -- git/schtasks gibi native araclar icin Continue).
    $ErrorActionPreference = "Continue"
    schtasks /Create /F `
        /TN "$($t.Name)" `
        /TR "`"$python`" $taskArgs" `
        /SC DAILY `
        /ST $($t.Time) `
        /RL LIMITED
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"

    if ($exitCode -ne 0) {
        Write-Host "HATA: $($t.Name) olusturulamadi (kod $exitCode)." -ForegroundColor Red
    } else {
        Write-Host "OK: $($t.Name)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Kontrol: schtasks /Query /TN YoutubeBot_MorningOpen /V /FO LIST"
Write-Host "Silmek icin: schtasks /Delete /TN <gorev-adi> /F"
