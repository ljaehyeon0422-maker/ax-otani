$ErrorActionPreference = "Stop"
$taskName = "YongsanIMAXWatcher"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed scheduled task: $taskName"
} else {
    Write-Host "Scheduled task not found: $taskName"
}

Write-Host "Power settings are not automatically restored because the previous values are unknown."
Write-Host "If needed, restore sleep settings from Windows Settings > System > Power & battery."
