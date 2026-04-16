# Obscura実行スクリプト（スリープ防止付き）
# PCがスリープしないようにしながらObscuraパイプラインを実行

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Obscura Pipeline - Sleep Prevention Enabled" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 現在のスリープ設定を保存
$originalSleepAC = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current AC Power Setting Index:" | ForEach-Object {$_ -replace '.*: 0x',''}).Trim()
$originalSleepDC = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current DC Power Setting Index:" | ForEach-Object {$_ -replace '.*: 0x',''}).Trim()

Write-Host "`nDisabling sleep mode..." -ForegroundColor Yellow
# スリープを無効化（ACアダプタ接続時とバッテリー駆動時の両方）
powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change standby-timeout-dc 0 | Out-Null
Write-Host "Sleep mode disabled. Running Obscura pipeline..." -ForegroundColor Green

try {
    # Obscura実行
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    Write-Host "`nStarting: $pythonPath main.py obscura-run`n" -ForegroundColor Cyan
    
    & $pythonPath main.py obscura-run
    
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
finally {
    # 元のスリープ設定に戻す
    Write-Host "`nRestoring original sleep settings..." -ForegroundColor Yellow
    if ($originalSleepAC) {
        powercfg /change standby-timeout-ac ([convert]::ToInt32($originalSleepAC, 16) / 60) | Out-Null
    }
    if ($originalSleepDC) {
        powercfg /change standby-timeout-dc ([convert]::ToInt32($originalSleepDC, 16) / 60) | Out-Null
    }
    Write-Host "Sleep settings restored." -ForegroundColor Green
}

Write-Host "`nPress any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
