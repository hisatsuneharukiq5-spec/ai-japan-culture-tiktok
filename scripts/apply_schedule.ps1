powershell -NoProfile -ExecutionPolicy Bypass -Command {
    # Check Admin
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host "❌ Admin rights required!" -ForegroundColor Red
        Write-Host "Please run this script as Administrator"
        Read-Host "Press Enter to exit"
        exit
    }
    
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host "YouTube Thumbnail Task Installer" -ForegroundColor Cyan
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host ""
    
    $xmlPath = "C:\Users\delio\ai-japan-youtube\task_config.xml"
    
    # Remove old task
    Write-Host "🔄 Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName "AIJapan_ThumbnailUpload" -Confirm:$false -ErrorAction SilentlyContinue
    
    # Import updated task
    Write-Host "📝 Importing updated task configuration..." -ForegroundColor Yellow
    Register-ScheduledTask -Xml (Get-Content $xmlPath | Out-String) -TaskName "AIJapan_ThumbnailUpload" -Force
    
    Write-Host ""
    Write-Host "✅ Task Successfully Updated!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Configuration:" -ForegroundColor Cyan
    Write-Host "   Task Name: AIJapan_ThumbnailUpload"
    Write-Host "   Next Run: 2026-03-07 04:15:00 (約24時間後)"
    Write-Host ""
    Write-Host "🛌 Sleep Mode Support:" -ForegroundColor Green
    Write-Host "   ✅ WakeToRun: ENABLED"
    Write-Host "   ✅ StartWhenAvailable: ENABLED"
    Write-Host "   ✅ RunLevel: HighestAvailable"
    Write-Host "   ✅ RequiresNetwork: true"
    Write-Host ""
    Write-Host "💤 What happens:" -ForegroundColor Yellow
    Write-Host "   • PCがスリープ中でも指定時刻に自動起動"
    Write-Host "   • YouTube サムネイル自動アップロード実行"
    Write-Host "   • 完了後、PCをスリープに戻す（手動）"
    Write-Host ""
    Write-Host "Press Enter to close..."
    Read-Host
}
