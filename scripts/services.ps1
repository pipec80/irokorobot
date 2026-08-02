# services.ps1 — check and manage OMNiBot project services
# Usage:
#   just services        check + start what is needed
#   just services-down   stop what was started

param([switch]$Down)

$OLLAMA_URL = "http://localhost:11434"
$REQUIRED_MODELS = @(
    @{ Name = "nomic-embed-text"; Desc = "embeddings (memory)" },
    @{ Name = "qwen2.5:3b";       Desc = "consolidation (extract facts)" }
)

function Test-Ollama {
    try {
        $r = Invoke-WebRequest -Uri $OLLAMA_URL -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch [System.Net.WebException] {
        # Got a response (non-2xx) — port is open, Ollama is up
        if ($_.Exception.Response) { return $true }
        return $false
    } catch {
        return $false
    }
}

# ── stop mode ────────────────────────────────────────────────────────────────
if ($Down) {
    $proc = Get-Process ollama -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Name "ollama" -Force
        Write-Host "Ollama stopped."
    } else {
        Write-Host "Ollama was not running."
    }
    exit 0
}

# ── start / check mode ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== OMNiBot services ==="
Write-Host ""

# Ollama
if (Test-Ollama) {
    Write-Host "  Ollama   [OK]   $OLLAMA_URL"
} else {
    Write-Host "  Ollama   [starting...]"
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $waited = 0
    while ($waited -lt 10) {
        Start-Sleep 2
        $waited += 2
        if (Test-Ollama) { break }
    }
    if (Test-Ollama) {
        Write-Host "  Ollama   [OK]   started after ${waited}s"
    } else {
        Write-Host "  Ollama   [WARN] could not auto-start -- run in a separate terminal: ollama serve"
    }
}

# Models
Write-Host ""
Write-Host "  Models:"
$modelOutput = ollama list 2>&1 | Out-String
foreach ($m in $REQUIRED_MODELS) {
    if ($modelOutput -match [regex]::Escape($m.Name)) {
        Write-Host ("    {0,-26} [OK]  ({1})" -f $m.Name, $m.Desc)
    } else {
        Write-Host ("    {0,-26} [MISSING]  run: ollama pull {1}" -f $m.Name, $m.Name)
    }
}

Write-Host ""
