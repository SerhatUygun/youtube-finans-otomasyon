# Local Ollama agents -> Windows Task Scheduler (2 Oct 2026). ASCII only (non-ASCII breaks .ps1 on this PC).
#   YTBot_Haber       hourly            tools/agents/news_hunter.py
#   YTBot_Performans  10:30 and 22:30   tools/agents/perf_watch.py
#   YTBot_Sistem      every 10 min      tools/agents/sys_watch.py
# Remove: Unregister-ScheduledTask -TaskName YTBot_Haber -Confirm:$false  (same for others)
$ErrorActionPreference = "Stop"
$root = "$PSScriptRoot\.."
$py = "$root\.venv\Scripts\pythonw.exe"
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 50)

function Reg($name, $script, $triggers) {
    $act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 $script" -WorkingDirectory "$root\tools\agents"
    Register-ScheduledTask -TaskName $name -Action $act -Trigger $triggers -Settings $set -Force | Out-Null
    Write-Output "ok $name"
}

$start = (Get-Date).AddMinutes(2)
$hourly = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1)
$tenmin = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 10)
$am = New-ScheduledTaskTrigger -Daily -At "10:30"
$pm = New-ScheduledTaskTrigger -Daily -At "22:30"

Reg "YTBot_Haber" "news_hunter.py" $hourly
Reg "YTBot_Performans" "perf_watch.py" @($am, $pm)
Reg "YTBot_Sistem" "sys_watch.py" $tenmin
