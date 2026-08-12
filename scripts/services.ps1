# services.ps1 — check and manage OMNiBot project services
# Usage:
#   just services        check + start what is needed
#   just services-down   stop what was started

param([switch]$Down)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    $ConfigPath = Join-Path $ProjectRoot ".env.example"
}

$ConfiguredValues = @{}
foreach ($rawLine in Get-Content -LiteralPath $ConfigPath) {
    if ($rawLine -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $ConfiguredValues[$Matches[1]] = $value
    }
}

function Get-ConfiguredValue {
    param(
        [string]$Name,
        [string]$Default
    )

    if ($ConfiguredValues.ContainsKey($Name) -and $ConfiguredValues[$Name]) {
        return $ConfiguredValues[$Name]
    }
    return $Default
}

$OLLAMA_URL = Get-ConfiguredValue "OLLAMA_URL" "http://localhost:11434"
$RequiredModels = @(
    @{ Name = (Get-ConfiguredValue "OLLAMA_MODEL" "qwen2.5:3b"); Desc = "chat" },
    @{ Name = (Get-ConfiguredValue "EMBEDDING_MODEL" "nomic-embed-text"); Desc = "embeddings (memory)" },
    @{ Name = (Get-ConfiguredValue "CONSOLIDATION_MODEL" "qwen2.5:3b"); Desc = "consolidation (extract facts)" }
)
if ((Get-ConfiguredValue "VISION_ENABLED" "false").ToLowerInvariant() -eq "true") {
    $RequiredModels += @{
        Name = (Get-ConfiguredValue "VLM_MODEL" "qwen3-vl:2b-instruct")
        Desc = "vision"
    }
}

function Test-Ollama {
    try {
        # `ollama list` checks the same local daemon used below for model
        # inspection and avoids Windows PowerShell `localhost` resolution
        # timeouts that can produce a false unavailable result.
        $null = & ollama list 2>$null
        return $LASTEXITCODE -eq 0
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
Write-Host "  Config: $ConfigPath"
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
foreach ($m in $RequiredModels) {
    if ($modelOutput -match [regex]::Escape($m.Name)) {
        Write-Host ("    {0,-26} [OK]  ({1})" -f $m.Name, $m.Desc)
    } else {
        Write-Host ("    {0,-26} [MISSING]  run: ollama pull {1}" -f $m.Name, $m.Name)
    }
}

Write-Host ""
