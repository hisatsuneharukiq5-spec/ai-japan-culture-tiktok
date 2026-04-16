@echo off
REM Wrapper to run the Python upload scheduler with args (used by Task Scheduler)
py -u "C:\Users\delio\ai-japan-youtube\scripts\schedule_uploads.py" --run-due
EXIT /B %ERRORLEVEL%
