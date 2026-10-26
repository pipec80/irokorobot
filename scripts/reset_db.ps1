# Resets the brain DB safely: refuses if the server is running, backs up first.
#
# Why this exists: on 2026-07-07 a manual Remove-Item ran while the server was
# up — SQLite kept the file handle alive and the "reset" silently never
# happened (the log showed "Schema up-to-date" instead of "Applying migration"
# and old memory survived). This script makes that mistake impossible.
#
# Usage: just reset-db
#        powershell.exe -File scripts/reset_db.ps1 -Port 9000
# The database is the one the server would open: BRAIN_DB_PATH (environment, then
# .env), else data/omnibot.db (Plan 0071). Its -wal and -shm go into the backup too.
param(
    # Server port to health-check. 0 means "not provided" (ports are never 0);
    # falls back to SERVER_PORT in .env, then to 8000. See Resolve-ServerPort.
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

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

function Resolve-DbPath {
    <#
    .SYNOPSIS
        Resolves the database the server would open (Plan 0071).
    .DESCRIPTION
        Order: BRAIN_DB_PATH in the environment > BRAIN_DB_PATH read from a .env
        file at the repo root (if present) > data/omnibot.db. The same order the
        server's settings follow, so a scratch database set with BRAIN_DB_PATH is
        the one reset, never data/omnibot.db by accident. Returns a full path.
    #>
    param(
        [string]$EnvFilePath
    )
    $configured = $env:BRAIN_DB_PATH
    if (-not $configured -and (Test-Path $EnvFilePath)) {
        $match = Select-String -Path $EnvFilePath -Pattern '^\s*BRAIN_DB_PATH\s*=\s*(.+?)\s*$'
        if ($match) {
            $configured = $match[0].Matches[0].Groups[1].Value.Trim('"', "'")
        }
    }
    if (-not $configured) {
        $configured = "data/omnibot.db"
    }
    $combined = [System.IO.Path]::Combine((Get-Location).Path, $configured)
    return [System.IO.Path]::GetFullPath($combined)
}

function Copy-DbWithSidecars {
    <#
    .SYNOPSIS
        Copies the database and, when they exist, its -wal and -shm sidecars.
    .DESCRIPTION
        The write-ahead log may hold committed pages the main file does not have yet,
        and the sidecars are deleted after the backup, so they travel with it. After
        scripts/scrub_candidates.py the log is normally folded and gone already; the
        copy is the defence for the case it is not.
    #>
    param(
        [string]$DbPath,
        [string]$BackupPath
    )
    Copy-Item $DbPath $BackupPath
    foreach ($suffix in @("-wal", "-shm")) {
        $sidecar = "$DbPath$suffix"
        if (Test-Path $sidecar) { Copy-Item $sidecar "$BackupPath$suffix" }
    }
}

$resolvedPort = Resolve-ServerPort -ParamPort $Port -EnvFilePath $envFilePath
$healthUrl = "http://localhost:$resolvedPort/health"

$dbPath = Resolve-DbPath -EnvFilePath $envFilePath
$dbFullPath = $dbPath
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

# 1b. A live memory candidate holds something the owner said about themselves (ADR 0021):
#     void it and overwrite its bytes BEFORE the file is copied to the backup folder.
uv run python scripts/scrub_candidates.py $dbPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: could not void live memory candidates - the database was NOT copied."
    exit 1
}

# 2. Backup with timestamp before touching anything.
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$stem = [System.IO.Path]::GetFileNameWithoutExtension($dbPath)
$backupPath = Join-Path $backupDir "${stem}_${stamp}_pre-reset.db"
Copy-DbWithSidecars -DbPath $dbPath -BackupPath $backupPath
Write-Host "Esta copia contiene datos biometricos y de salud. El sistema no la borra: anota su ruta y la fecha en que la destruiras."

# 3. Delete the DB and its WAL/SHM sidecars.
Remove-Item $dbPath -Force
foreach ($suffix in @("-wal", "-shm")) {
    $sidecar = "$dbPath$suffix"
    if (Test-Path $sidecar) { Remove-Item $sidecar -Force }
}

Write-Host "DB reset OK. Backup: $backupPath"
Write-Host "Next: just run-server and VERIFY the log shows 'Applying migration' lines (1 and 2)."
