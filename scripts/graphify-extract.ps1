# Code graph for daily-feed. Do not run `graphify install`.
# Usage from the repo root: .\scripts\graphify-extract.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

$graphify = Get-Command graphify -ErrorAction SilentlyContinue
if (-not $graphify) {
    $candidate = "C:\Users\bayla\.local\bin\graphify.exe"
    if (-not (Test-Path $candidate)) {
        Write-Error "graphify not found. Install the CLI yourself. Do not run graphify install inside this repo."
    }
    $graphify = $candidate
} else {
    $graphify = $graphify.Source
}

& $graphify extract . --code-only --no-label
if ($LASTEXITCODE -ne 0) {
    Write-Error "graphify extract failed (exit $LASTEXITCODE)"
}
