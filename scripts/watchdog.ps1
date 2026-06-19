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
    Full path to the heartbeat file.  By default this is resolved from the
    Workflow 2 YAML ``logging.output_dir``.

.PARAMETER MaxAgeMinutes
    Maximum age in minutes before the process is considered dead (default: 5).

.PARAMETER WorkDir
    Project root directory (default: parent of this script's directory).

.PARAMETER PythonExe
    Path to Python executable (default: ``<WorkDir>\.venv\Scripts\python.exe``).

.PARAMETER WarmupDbPath
    Optional cleaned curve index passed to every restart.  Defaults to
    ``<WorkDir>\Results\raw_curves\index.cleaned.jsonl`` when present.

.EXAMPLE
    .\scripts\watchdog.ps1

    .\scripts\watchdog.ps1 -MaxAgeMinutes 10 -HeartbeatPath D:\Results\workflow_2_heartbeat.txt
#>

param(
    [string]$HeartbeatPath = "",
    [int]$MaxAgeMinutes = 5,
    [string]$PythonExe = "",
    [string]$WorkDir = "",
    [string]$WarmupDbPath = ""
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
    $ConfigPath = Join-Path $WorkDir "workflows\rfgun_hom_antenna\config.yaml"
    $ResolveOutputDir = @"
import pathlib
import sys
import yaml

cfg = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
wf2 = cfg.get("workflow_2", {})
logging_cfg = wf2.get("logging", cfg.get("logging", {}))
print(logging_cfg.get("output_dir", str(pathlib.Path(sys.argv[2]) / "Results")))
"@
    try {
        $OutputDir = (& $PythonExe -c $ResolveOutputDir $ConfigPath $WorkDir).Trim()
    } catch {
        Write-Error "Cannot resolve Workflow 2 output_dir from $ConfigPath`: $_"
        exit 1
    }
    $HeartbeatPath = Join-Path $OutputDir "workflow_2_heartbeat.txt"
}

$ScriptPath = Join-Path $WorkDir "run_workflow_2.py"
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Cannot find run_workflow_2.py at $ScriptPath"
    exit 1
}
if (-not $WarmupDbPath) {
    $DefaultWarmupDb = Join-Path $WorkDir "Results\raw_curves\index.cleaned.jsonl"
    if (Test-Path $DefaultWarmupDb) {
        $WarmupDbPath = $DefaultWarmupDb
    }
}

# Serialize watchdog checks and avoid launching when the Python process is
# already alive but the heartbeat is momentarily delayed.
$Mutex = [System.Threading.Mutex]::new(
    $false, "Global\CST_Workflow2_WatchdogLaunch"
)
if (-not $Mutex.WaitOne(0)) {
    exit 0
}

try {
    $RunningWorkflow = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -like '*run_workflow_2.py*'
        }
    if ($RunningWorkflow) {
        return
    }

    # ── Check heartbeat ────────────────────────────────────────────────────
    if (Test-Path $HeartbeatPath) {
        $hbAge = (Get-Date) - (Get-Item $HeartbeatPath).LastWriteTime
        if ($hbAge.TotalMinutes -lt $MaxAgeMinutes) {
            # Heartbeat is fresh — process is alive.  Do nothing.
            return
        }
        $ageStr = "{0:F1}" -f $hbAge.TotalMinutes
        Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): heartbeat stale (${ageStr} min > ${MaxAgeMinutes} min) — launching workflow"
    } else {
        Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): no heartbeat file — launching workflow"
    }

    # ── Launch workflow ────────────────────────────────────────────────────
    $WorkflowArgs = "`"$ScriptPath`" --auto-resume --heartbeat"
    if ($WarmupDbPath) {
        $WorkflowArgs += " --warmup-from-db `"$WarmupDbPath`""
    }
    $proc = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $WorkflowArgs `
        -WorkingDirectory $WorkDir `
        -WindowStyle Hidden `
        -PassThru

    Write-Host "Workflow 2 launched (PID=$($proc.Id))"
} catch {
    Write-Error "Failed to launch workflow: $_"
    exit 1
} finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
