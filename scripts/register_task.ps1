# Registers a Windows scheduled task that refreshes data every 3 hours, even when
# the dashboard is not running. Stale-only: a run when data is current costs nothing.
# Usage (PowerShell):  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
#   Remove:            powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove
param([switch]$Remove, [int]$EveryHours = 3)
$name = "BreadthRefresh"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "Removed task $name"
    exit 0
}
$bat = Join-Path $PSScriptRoot "refresh.bat"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Description "Breadth data refresh (stale sources only)" -Force | Out-Null
Write-Host "Registered task '$name' (every $EveryHours h). Log: data\refresh_task.log"
