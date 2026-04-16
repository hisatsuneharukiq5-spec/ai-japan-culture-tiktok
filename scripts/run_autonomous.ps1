#!/usr/bin/env pwsh
$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logdir = Join-Path $root "logs\autonomous"
New-Item -ItemType Directory -Path $logdir -Force | Out-Null
$log = Join-Path $logdir ("autonomous_" + $timestamp + ".log")
"Starting autonomous runner: $timestamp" | Tee-Object -FilePath $log -Append

# Set AUTONOMOUS_RUN=1 to perform actions; otherwise this will be a dry-run.
if (-not (Get-ChildItem Env:AUTONOMOUS_RUN)) {
    "AUTONOMOUS_RUN not set; running dry-run. To enable actions set AUTONOMOUS_RUN=1 in Task Scheduler." | Tee-Object -FilePath $log -Append
}

& py -u "${root}\main.py" autonomous 2>&1 | Tee-Object -FilePath $log -Append

"Finished autonomous runner: $timestamp" | Tee-Object -FilePath $log -Append
Exit 0
