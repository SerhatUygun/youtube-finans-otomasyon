# 16 Eki: gece ajan turu — sırayla (GPU/bellek çakışması yok): sistem -> haber -> performans -> gece editörü. 10:00'da kalan işi keser.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot\..
$py = '.venv\Scripts\python.exe'
$log = 'output\_agents\gece_tur.log'
$dead = (Get-Date).Date.AddHours(10)
if ((Get-Date) -gt $dead) { $dead = $dead.AddDays(1) }
foreach ($a in 'sys_watch', 'news_hunter', 'perf_watch', 'night_editor') {
  if ((Get-Date) -ge $dead) { "$(Get-Date -f 'HH:mm:ss') SÜRE DOLDU, $a atlandı" | Add-Content $log -Encoding utf8; continue }
  "$(Get-Date -f 'HH:mm:ss') başlıyor: $a" | Add-Content $log -Encoding utf8
  $p = Start-Process -FilePath $py -ArgumentList '-X', 'utf8', "tools\agents\$a.py" -PassThru -WindowStyle Hidden -RedirectStandardOutput "output\_agents\gece_$a.out.log" -RedirectStandardError "output\_agents\gece_$a.err.log"
  while (-not $p.HasExited) {
    if ((Get-Date) -ge $dead) { Stop-Process -Id $p.Id -Force; "$(Get-Date -f 'HH:mm:ss') 10:00 kesildi: $a" | Add-Content $log -Encoding utf8; break }
    Start-Sleep 20
  }
  "$(Get-Date -f 'HH:mm:ss') bitti: $a (kod $($p.ExitCode))" | Add-Content $log -Encoding utf8
}
"$(Get-Date -f 'HH:mm:ss') TUR TAMAM" | Add-Content $log -Encoding utf8
