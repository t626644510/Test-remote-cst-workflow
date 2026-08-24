param(
    [string]$Python,
    [switch]$SkipSelfTest
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python executable not found: $Python"
}

$EntryPoint = Join-Path $RepositoryRoot "scripts\rf_cem_workbench_desktop.py"
$Executable = Join-Path $RepositoryRoot "dist\RF-CEM-Workbench.exe"

Push-Location $RepositoryRoot
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --noupx `
        --name "RF-CEM-Workbench" `
        --paths (Join-Path $RepositoryRoot "src") `
        --specpath (Join-Path $RepositoryRoot "build") `
        --workpath (Join-Path $RepositoryRoot "build\rf_cem_workbench") `
        --distpath (Join-Path $RepositoryRoot "dist") `
        --exclude-module "cst" `
        --exclude-module "cst_optimization" `
        --exclude-module "cadquery" `
        --exclude-module "OCP" `
        --exclude-module "numpy" `
        --exclude-module "pandas" `
        --exclude-module "scipy" `
        --exclude-module "matplotlib" `
        --exclude-module "plotly" `
        --exclude-module "PIL" `
        --exclude-module "pytest" `
        --exclude-module "sklearn" `
        --exclude-module "pymoo" `
        $EntryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Expected launcher executable was not produced: $Executable"
    }
    if (-not $SkipSelfTest) {
        & $Executable --self-test --repo-root $RepositoryRoot --no-browser
        if ($LASTEXITCODE -ne 0) {
            throw "Launcher executable self-test failed with exit code $LASTEXITCODE"
        }
    }
    Write-Output $Executable
}
finally {
    Pop-Location
}
