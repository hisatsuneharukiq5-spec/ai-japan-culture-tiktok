@echo off
REM Schedule automatic retry upload after 24 hours
REM This batch file runs the upload script

cd /d "C:\Users\delio\ai-japan-youtube"
python scripts/upload_pexels_thumbnails.py
pause
