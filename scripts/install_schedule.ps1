powershell -Command {
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host "YouTube Thumbnail Upload Scheduler" -ForegroundColor Cyan
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Check Admin
    `$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not `$isAdmin) {
        Write-Host "❌ Admin permission required!" -ForegroundColor Red
        exit
    }
    
    Write-Host "✅ Admin confirmed`n" -ForegroundColor Green
    
    # Remove old task
    Unregister-ScheduledTask -TaskName "YouTube_Pexels_Thumbnail_Upload_Retry" -Confirm:`$false -ErrorAction SilentlyContinue
    
    `$startTime = (Get-Date).AddHours(24)
    
    `$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\Users\delio\ai-japan-youtube\scripts\upload_pexels_thumbnails.py" -WorkingDirectory "C:\Users\delio\ai-japan-youtube"
    `$trigger = New-ScheduledTaskTrigger -Once -At `$startTime
    `$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -WakeToRun -StartWhenAvailable
    
    `$task = Register-ScheduledTask -TaskName "YouTube_Pexels_Thumbnail_Upload_Retry" -Action `$action -Trigger `$trigger -Settings `$settings -RunLevel Highest -Force
    
    Write-Host "✅ Task Successfully Scheduled!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Task Details:" -ForegroundColor Cyan
    Write-Host "   Name: `$(`$task.TaskName)"
    Write-Host "   State: `$(`$task.State)"
    Write-Host "   Scheduled for: `$startTime"
    Write-Host ""
    Write-Host "🛌 Sleep Mode Support:" -ForegroundColor Cyan
    Write-Host "   ✅ WakeToRun is ENABLED"
    Write-Host "   ✅ StartWhenAvailable is ENABLED"
    Write-Host "   ✅ RunLevel: Highest (Admin)"
    Write-Host ""
    Write-Host "Press Enter to close..."
    `$null = Read-Host
}
