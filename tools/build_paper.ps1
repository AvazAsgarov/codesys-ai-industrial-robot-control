<#
.SYNOPSIS
    Builds the IEEE paper with Tectonic into paper/build/main.pdf.
#>
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$paperDir = Join-Path $repoRoot 'paper'
$outDir = Join-Path $paperDir 'build'

if (-not (Get-Command tectonic -ErrorAction SilentlyContinue)) {
    Write-Error 'tectonic not found on PATH. See docs/user-guide/setup.md.'
    exit 1
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Push-Location $paperDir
try {
    tectonic -X compile main.tex --outdir $outDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
Write-Output "Built $outDir\main.pdf"
