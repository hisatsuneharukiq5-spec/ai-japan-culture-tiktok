powershell -Command {
    $startTime = (Get-Date).AddHours(24)
    $action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Users\delio\ai-japan-youtube\scripts\upload_pexels_thumbnail_only.py" -WorkingDirectory "C:\Users\delio\ai-japan-youtube"
    $trigger = New-ScheduledTaskTrigger -Once -At $startTime
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -WakeToRun -StartWhenAvailable
    
    Unregister-ScheduledTask -TaskName "YouTube_Vending_Thumbnail_Upload" -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName "YouTube_Vending_Thumbnail_Upload" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
    
    Write-Host "✅ Thumbnail upload scheduled for: $startTime" -ForegroundColor Green
}
