# Resets the brain DB safely: refuses if the server is running, backs up first.
#
# Why this exists: on 2026-07-07 a manual Remove-Item ran while the server was
# up — SQLite kept the file handle alive and the "reset" silently never
# happened (the log showed "Schema up-to-date" instead of "Applying migration"
# and old memory survived). This script makes that mistake impossible.
#
# Usage: just reset-db
#        powershell.exe -File scripts/reset_db.ps1 -Port 9000
param(
    # Server port to health-check. 0 means "not provided" (ports are never 0);
    # falls back to SERVER_PORT in .env, then to 8000. See Resolve-ServerPort.
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

$dbPath = "data/omnibot.db"
$backupDir = "data/backups"
$envFilePath = ".env"

function Resolve-ServerPort {
    <#
    .SYNOPSIS
        Resolves the effective server port.
    .DESCRIPTION
        Order: -Port parameter (if provided) > SERVER_PORT read from a .env
        file at the repo root (if present) > 8000 as last-resort fallback.
        Keeps this script in sync with server/src/server/settings.py without
        needing to edit two files whenever the port changes.
    #>
    param(
        [int]$ParamPort,
        [string]$EnvFilePath
    )
    if ($ParamPort -ne 0) {
        return $ParamPort
    }
    if (Test-Path $EnvFilePath) {
        $match = Select-String -Path $EnvFilePath -Pattern '^\s*SERVER_PORT\s*=\s*(\d+)\s*$'
        if ($match) {
            return [int]$match[0].Matches[0].Groups[1].Value
        }
    }
    return 8000
}

$resolvedPort = Resolve-ServerPort -ParamPort $Port -EnvFilePath $envFilePath
$healthUrl = "http://localhost:$resolvedPort/health"

$dbFullPath = Join-Path (Get-Location).Path $dbPath
$backupDirFullPath = Join-Path (Get-Location).Path $backupDir

Write-Host "DB path:      $dbFullPath"
Write-Host "Backup dir:   $backupDirFullPath"
Write-Host "Health check: $healthUrl"

# 1. Refuse when the server is running.
$serverUp = $false
try {
    $null = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2 -UseBasicParsing
    $serverUp = $true
} catch {
    # Unreachable = server stopped. Safe to continue.
}
if ($serverUp) {
    Write-Host "ERROR: server is ONLINE at $healthUrl - stop it first (Ctrl+C in its terminal)."
    exit 1
}

if (-not (Test-Path $dbPath)) {
    Write-Host "No DB at $dbPath - nothing to reset."
    exit 0
}

# 2. Backup with timestamp before touching anything.
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupPath = Join-Path $backupDir "omnibot_${stamp}_pre-reset.db"
Copy-Item $dbPath $backupPath

# 3. Delete the DB and its WAL/SHM sidecars.
Remove-Item $dbPath -Force
foreach ($suffix in @("-wal", "-shm")) {
    $sidecar = "$dbPath$suffix"
    if (Test-Path $sidecar) { Remove-Item $sidecar -Force }
}

Write-Host "DB reset OK. Backup: $backupPath"
Write-Host "Next: just run-server and VERIFY the log shows 'Applying migration' lines (1 and 2)."
