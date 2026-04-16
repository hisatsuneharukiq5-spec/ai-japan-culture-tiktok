:: Run PowerShell script as Administrator
:: スリープモードでもYouTubeサムネイル自動アップロード設定

@echo off
setlocal enabledelayedexpansion

:: Check if running as Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ This script must be run as Administrator!
    echo.
    echo Please right-click on this .bat file and select "Run as Administrator"
    echo Or run the PowerShell script directly:
    echo   C:\Users\delio\ai-japan-youtube\scripts\configure_sleep_schedule.ps1
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================
echo YouTube Thumbnail Upload Scheduler
echo ====================================
echo.

:: Run PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\delio\ai-japan-youtube\scripts\configure_sleep_schedule.ps1"

pause
