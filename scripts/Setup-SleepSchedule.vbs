' Setup-SleepSchedule.vbs
' ダブルクリックで管理者権限を自動取得してスケジュール設定

Set objShell = CreateObject("Shell.Application")
strPath = WScript.ScriptFullName
objShell.ShellExecute "powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File ""C:\Users\delio\ai-japan-youtube\scripts\configure_sleep_schedule.ps1""", , "runas", 1
