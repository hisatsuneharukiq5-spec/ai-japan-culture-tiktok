# Obscura実行スクリプト（スリープ防止付き）
# PCがスリープしないようにしながらObscuraパイプラインを実行

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Obscura Pipeline - Sleep Prevention Enabled" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# スリープ防止はPython内部でSetThreadExecutionState経由で処理
Write-Host "Sleep prevention is handled inside Python." -ForegroundColor Green

try {
    $python = Join-Path $PSScriptRoot "..\\.venv\Scripts\python.exe"
    Write-Host "`nStarting: $python main.py obscura-run`n" -ForegroundColor Cyan
    & $python (Join-Path $PSScriptRoot "..\main.py") "obscura-run"
    $exitCode = $LASTEXITCODE
    Write-Host "`n======================================" -ForegroundColor Cyan
    if ($exitCode -eq 0) {
        Write-Host "Obscura pipeline completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "Obscura pipeline exited with code: $exitCode" -ForegroundColor Red
    }
    Write-Host "======================================" -ForegroundColor Cyan
}
catch {
    Write-Host "`nError occurred: $_" -ForegroundColor Red
}

Write-Host "`nPress any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
