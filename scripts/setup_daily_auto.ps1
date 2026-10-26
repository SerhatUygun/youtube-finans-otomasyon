# Daily automatic video (2 Oct 2026): 11:00 every day -> research + script + TTS + render -> YouTube scheduled publish
# (long 15:00, Shorts 19:30 and next day 10:00, see config.yaml youtube.auto_publish). ASCII only.
# Remove: Unregister-ScheduledTask -TaskName YTBot_GunlukVideo -Confirm:$false
$ErrorActionPreference = "Stop"
$root = "$PSScriptRoot\.."
$py = "$root\.venv\Scripts\pythonw.exe"
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 tools\daily_run.py --auto" -WorkingDirectory $root
$trg = New-ScheduledTaskTrigger -Daily -At "11:00"
Register-ScheduledTask -TaskName "YTBot_GunlukVideo" -Action $act -Trigger $trg -Settings $set -Force | Out-Null
Write-Output "ok YTBot_GunlukVideo"
