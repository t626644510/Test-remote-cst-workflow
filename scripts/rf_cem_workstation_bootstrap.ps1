param(
    [string]$CstLibraryPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[cad,dev,review]"

if ($CstLibraryPath -ne "") {
    [Environment]::SetEnvironmentVariable("CST_LIBRARY_PATH", $CstLibraryPath, "User")
    Write-Host "Set user CST_LIBRARY_PATH=$CstLibraryPath"
}

Write-Host "Bootstrap complete."
Write-Host "No-CST smoke:"
Write-Host '$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m workflows.rf_cem_500mhz_parametric_opt.runner --output-dir runs\rf_cem_500mhz_parametric_opt_12d_no_cst_smoke'
