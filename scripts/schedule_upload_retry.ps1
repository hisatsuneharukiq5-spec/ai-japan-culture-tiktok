# Schedule automatic thumbnail upload retry after 24 hours
# Run as Administrator

$taskName = "YouTube_Pexels_Thumbnail_Upload_Retry"
$scriptPath = "C:\Users\delio\ai-japan-youtube\scripts\upload_pexels_thumbnails.py"
$pythonExe = "python"

# Calculate time 24 hours from now
$startTime = (Get-Date).AddHours(24)

# Remove existing task if it exists
Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Create new scheduled task
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath -WorkingDirectory "C:\Users\delio\ai-japan-youtube"
$trigger = New-ScheduledTaskTrigger -Once -At $startTime
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "✅ Task scheduled!"
Write-Host "Task Name: $taskName"
Write-Host "Run Time: $startTime"
Write-Host "Status: Will run in approximately 24 hours"
