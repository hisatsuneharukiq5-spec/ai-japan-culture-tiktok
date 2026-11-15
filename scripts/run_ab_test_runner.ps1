#!/usr/bin/env pwsh
# Wrapper to run ab_test_runner.py and append timestamped logs to logs/ab_tests
$root   = "C:\Users\delio\ai-japan-youtube"
$python = Join-Path $root ".venv\Scripts\python.exe"
$LogDir = Join-Path $root "logs\ab_tests"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "ab_test_runner_$ts.log"
$ScriptPath = Join-Path $root "scripts\ab_test_runner.py"
"Starting ab_test_runner at $(Get-Date)" | Out-File $LogFile -Encoding utf8
try {
    & $python -u $ScriptPath 2>&1 | Tee-Object -FilePath $LogFile -Append
} catch {
    "Error running ab_test_runner: $_" | Tee-Object -FilePath $LogFile -Append
}
"Finished ab_test_runner at $(Get-Date)" | Tee-Object -FilePath $LogFile -Append
Exit 0
