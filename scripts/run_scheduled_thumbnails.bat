@echo off
REM Start scheduled thumbnail upload (24 hours delay, 1 hour interval)
echo ========================================
echo Scheduled Thumbnail Upload
echo ========================================
echo.
echo This will:
echo - Wait 24 hours before starting
echo - Upload 1 thumbnail per hour
echo - Prevent YouTube API rate limits
echo.
echo Press Ctrl+C to cancel anytime
echo.
pause

py scripts\scheduled_thumbnail_upload.py

pause
