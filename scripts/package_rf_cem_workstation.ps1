param(
    [string]$OutputPath = "dist\rf_cem_workstation_package.zip"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputFullPath = Join-Path $Root $OutputPath
$Stage = Join-Path $env:TEMP ("rf_cem_workstation_package_" + [guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Force -Path $Stage | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $OutputFullPath) | Out-Null

$Items = @(
    "pyproject.toml",
    "src",
    "workflows\rf_cem_500mhz_parametric_opt",
    "scripts\rf_cem_workstation_bootstrap.ps1",
    "docs\rf_cem_expert_prior_schema.md",
    "docs\rf_cem_parametric_geometry_status.md",
    "docs\rf_cem_parametric_geometry_status.zh.md",
    "docs\rf_cem_cst_postprocessing_template_notes.md",
    "tests\test_rf_cem_parametric_optimization.py",
    "tests\test_rf_cem_parametric_geometry_500mhz.py",
    "tests\test_rf_cem_500mhz.py"
)

foreach ($Item in $Items) {
    $Source = Join-Path $Root $Item
    if (Test-Path $Source) {
        $Destination = Join-Path $Stage $Item
        New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
        Copy-Item -Path $Source -Destination $Destination -Recurse -Force
    }
}

if (Test-Path $OutputFullPath) {
    Remove-Item -LiteralPath $OutputFullPath -Force
}
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $OutputFullPath
$ResolvedStage = (Resolve-Path $Stage).Path
$ResolvedTemp = (Resolve-Path $env:TEMP).Path
if (-not $ResolvedStage.StartsWith($ResolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove staging directory outside TEMP: $ResolvedStage"
}
Remove-Item -LiteralPath $ResolvedStage -Recurse -Force

Write-Host "Wrote $OutputFullPath"
Write-Host "The package intentionally excludes runs, Appendix, .venv, CST projects, and local output databases."
