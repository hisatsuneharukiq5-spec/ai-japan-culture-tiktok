# Run as Administrator
# スリープモードでもタスクが実行されるように設定

Write-Host "================================" -ForegroundColor Cyan
Write-Host "YouTube Thumbnail Upload Scheduler" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Please right-click on this file and select 'Run as Administrator'" -ForegroundColor Yellow
    pause
    exit
}

Write-Host "✅ Running with Administrator privileges`n" -ForegroundColor Green

# Calculate time 24 hours from now
$startTime = (Get-Date).AddHours(24)

Write-Host "📅 Configuration:" -ForegroundColor Cyan
Write-Host "   Scheduled time: $startTime"
Write-Host "   Task name: YouTube_Pexels_Thumbnail_Upload_Retry"
Write-Host "   Script: C:\Users\delio\ai-japan-youtube\scripts\upload_pexels_thumbnails.py"
Write-Host ""

# Remove existing task
Write-Host "🔄 Removing existing task (if any)..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName "YouTube_Pexels_Thumbnail_Upload_Retry" -Confirm:$false -ErrorAction SilentlyContinue

# Create task action
$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "C:\Users\delio\ai-japan-youtube\scripts\upload_pexels_thumbnails.py" `
    -WorkingDirectory "C:\Users\delio\ai-japan-youtube"

# Create task trigger
$trigger = New-ScheduledTaskTrigger -Once -At $startTime

# Create task settings with WakeToRun enabled
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -StartWhenAvailable

# Register the task
Write-Host "📝 Creating scheduled task..." -ForegroundColor Yellow
$task = Register-ScheduledTask `
    -TaskName "YouTube_Pexels_Thumbnail_Upload_Retry" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "✅ Task successfully scheduled!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Task Details:" -ForegroundColor Cyan
Write-Host "   Task Name: $($task.TaskName)"
Write-Host "   State: $($task.State)"
Write-Host "   Scheduled for: $startTime"
Write-Host ""
Write-Host "🛌 Sleep Mode Support:" -ForegroundColor Cyan
Write-Host "   ✅ WakeToRun: Enabled (PC will wake from sleep)"
Write-Host "   ✅ StartWhenAvailable: Enabled (runs when system is available)"
Write-Host ""
Write-Host "💤 What happens when PC is in sleep mode:" -ForegroundColor Yellow
Write-Host "   · At $startTime, Windows will automatically wake the PC"
Write-Host "   · The upload script will run immediately"
Write-Host "   · Once complete, you can manually sleep the PC again"
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
