#!/usr/bin/env pwsh
# Wrapper to run ab_test_runner.py and append timestamped logs to logs/ab_tests
$LogDir = "C:\Users\delio\ai-japan-youtube\logs\ab_tests"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "ab_test_runner_$ts.log"
$ScriptPath = "C:\Users\delio\ai-japan-youtube\scripts\ab_test_runner.py"
Write-Output "Starting ab_test_runner at $(Get-Date)" | Tee-Object -FilePath $LogFile
try {
    & py -u $ScriptPath 2>&1 | Tee-Object -FilePath $LogFile
} catch {
    Write-Output "Error running ab_test_runner: $_" | Tee-Object -FilePath $LogFile
}
Write-Output "Finished ab_test_runner at $(Get-Date)" | Tee-Object -FilePath $LogFile
