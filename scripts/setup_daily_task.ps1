# Saglam Para - daily 14:00 automation task (tools/daily_run.py)
# ASCII only (non-ASCII .ps1 breaks under Windows PowerShell 5.1).
# Usage:   powershell -ExecutionPolicy Bypass -File scripts\setup_daily_task.ps1 [-Time 14:00] [-Remove]
param(
    [string]$Time = "14:00",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$TaskName = "YTBot_Daily"
$Root = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed $TaskName"
    exit 0
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "venv python not found: $Python" }
$LogDir = Join-Path $Root "output\_daily"
New-Item -ItemType Directory -Force $LogDir | Out-Null

# cmd /c wrapper: stdout/stderr go to a file (Task Scheduler does not capture output)
$Cmd = "/c `"`"$Python`" -X utf8 tools\daily_run.py >> `"$LogDir\scheduler_stdout.log`" 2>&1`""
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $Cmd -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 10)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal `
    -Description "Saglam Para daily video: Claude research -> TTS -> Remotion -> YouTube private + Drive reels" -Force | Out-Null

Write-Host "OK: $TaskName daily at $Time (working dir: $Root)"
Write-Host "Run now:  schtasks /Run /TN $TaskName"
Write-Host "Logs:     $LogDir"
Write-Host "Note: allow wake timers in Power Options (Sleep > Allow wake timers = Enable)."
