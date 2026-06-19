<#
.SYNOPSIS
    Lightweight heartbeat-based watchdog for Workflow 2 crash recovery.

.DESCRIPTION
    Checks ``workflow_2_heartbeat.txt`` age.  If the heartbeat is missing or
    older than the threshold, the process is considered dead and a new instance
    of ``run_workflow_2.py --auto-resume --heartbeat`` is launched.

    Designed to be called every 5 minutes by Task Scheduler.  Safe for long
    F2W solver runs (4000-4900 s): the heartbeat thread writes every 60 s,
    so a live process always keeps the file mtime fresh.

.PARAMETER HeartbeatPath
    Full path to the heartbeat file (default: ``<WorkDir>\Results\workflow_2_heartbeat.txt``).

.PARAMETER MaxAgeMinutes
    Maximum age in minutes before the process is considered dead (default: 5).

.PARAMETER WorkDir
    Project root directory (default: parent of this script's directory).

.PARAMETER PythonExe
    Path to Python executable (default: ``<WorkDir>\.venv\Scripts\python.exe``).

.EXAMPLE
    .\scripts\watchdog.ps1

    .\scripts\watchdog.ps1 -MaxAgeMinutes 10 -HeartbeatPath D:\Results\workflow_2_heartbeat.txt
#>

param(
    [string]$HeartbeatPath = "",
    [int]$MaxAgeMinutes = 5,
    [string]$PythonExe = "",
    [string]$WorkDir = ""
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ──────────────────────────────────────────────────────────
if (-not $WorkDir) {
    $WorkDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
if (-not $PythonExe) {
    $venvPython = Join-Path $WorkDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } else {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
}
if (-not $HeartbeatPath) {
    # Infer from the project output_dir.  Default: <WorkDir>\Results
    $HeartbeatPath = Join-Path $WorkDir "Results\workflow_2_heartbeat.txt"
}

$ScriptPath = Join-Path $WorkDir "run_workflow_2.py"
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Cannot find run_workflow_2.py at $ScriptPath"
    exit 1
}

# ── Check heartbeat ────────────────────────────────────────────────────────
if (Test-Path $HeartbeatPath) {
    $hbAge = (Get-Date) - (Get-Item $HeartbeatPath).LastWriteTime
    if ($hbAge.TotalMinutes -lt $MaxAgeMinutes) {
        # Heartbeat is fresh — process is alive.  Do nothing.
        exit 0
    }
    $ageStr = "{0:F1}" -f $hbAge.TotalMinutes
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): heartbeat stale (${ageStr} min > ${MaxAgeMinutes} min) — launching workflow"
} else {
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): no heartbeat file — launching workflow"
}

# ── Launch workflow ────────────────────────────────────────────────────────
try {
    $proc = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList "`"$ScriptPath`" --auto-resume --heartbeat" `
        -WorkingDirectory $WorkDir `
        -WindowStyle Hidden `
        -PassThru

    Write-Host "Workflow 2 launched (PID=$($proc.Id))"
} catch {
    Write-Error "Failed to launch workflow: $_"
    exit 1
}
