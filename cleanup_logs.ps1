# cleanup_logs.ps1 — Archive bot logs older than 7 days
$logDir    = Join-Path $PSScriptRoot "logs"
$archDir   = Join-Path $logDir "archive"
$keepDays  = 7

if (-not (Test-Path $archDir)) {
    New-Item -ItemType Directory -Path $archDir | Out-Null
}

$cutoff = (Get-Date).AddDays(-$keepDays)
$oldLogs = Get-ChildItem -Path $logDir -Filter "*.log" -File |
           Where-Object { $_.LastWriteTime -lt $cutoff }

if ($oldLogs.Count -gt 0) {
    $zipName = Join-Path $archDir ("log_archive_" + (Get-Date -Format "yyyyMMdd") + ".zip")
    # Compress-Archive -Update appends to existing zip
    $oldLogs | ForEach-Object {
        Compress-Archive -Path $_.FullName -DestinationPath $zipName -Update -ErrorAction SilentlyContinue
    }
    $oldLogs | Remove-Item -Force
    Write-Host "[OK] Archived $($oldLogs.Count) log file(s) older than $keepDays days -> $zipName"
} else {
    Write-Host "[OK] No old logs to archive (all within last $keepDays days)."
}

# Also report current log count
$current = (Get-ChildItem -Path $logDir -Filter "*.log" -File).Count
Write-Host "[INFO] Current log count: $current file(s) in $logDir"
