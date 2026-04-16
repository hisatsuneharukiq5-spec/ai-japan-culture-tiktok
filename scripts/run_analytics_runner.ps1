#!/usr/bin/env pwsh
# Run analytics fetch, append timeseries, and experiment tracker; log output.
$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logdir = Join-Path $root "logs\analytics"
New-Item -ItemType Directory -Path $logdir -Force | Out-Null
$log = Join-Path $logdir ("analytics_" + $timestamp + ".log")
"Starting analytics runner: $timestamp" | Tee-Object -FilePath $log -Append

& py -u "${root}\scripts\fetch_analytics.py" 2>&1 | Tee-Object -FilePath $log -Append
& py -u "${root}\scripts\append_analytics_timeseries.py" 2>&1 | Tee-Object -FilePath $log -Append
& py -u "${root}\scripts\experiment_tracker.py" 2>&1 | Tee-Object -FilePath $log -Append
& py -u "${root}\scripts\alerts_runner.py" 2>&1 | Tee-Object -FilePath $log -Append

"Finished analytics runner: $timestamp" | Tee-Object -FilePath $log -Append
Exit 0
