<#
.SYNOPSIS
    Register a Windows Task Scheduler job to auto-restart Workflow 2 after reboot.

.DESCRIPTION
    Creates a startup task plus a five-minute heartbeat watchdog.  The
    watchdog is the recurring health trigger; the workflow task itself is not
    periodically restarted while a healthy process is running.

    The task runs as the current user and is configured to:
    - Trigger at system startup
    - Auto-terminate after 72 hours
    - Reject overlapping launches through the runner's process lock

.EXAMPLE
    .\scripts\schedule_workflow2.ps1

    .\scripts\schedule_workflow2.ps1 -TaskName "CST_WF2_Auto" -DelayMinutes 5
#>

param(
    [string]$TaskName = "CST_Workflow2_AutoResume",
    [int]$DelayMinutes = 2,
    [string]$PythonExe = "",
    [string]$WorkDir = "",
    [string]$WarmupDbPath = ""
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ──────────────────────────────────────────────────────
if (-not $WorkDir) {
    $WorkDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
if (-not $PythonExe) {
    # Try to find the venv Python
    $venvPython = Join-Path $WorkDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    } else {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
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

Write-Host "Task Name:    $TaskName"
Write-Host "Python:       $PythonExe"
Write-Host "Script:       $ScriptPath"
Write-Host "Work Dir:     $WorkDir"
Write-Host "Warmup DB:    $WarmupDbPath"
Write-Host "Delay:        ${DelayMinutes} min after startup"
Write-Host ""

# ── Build the action ──────────────────────────────────────────────────
$ActionArgs = "`"$ScriptPath`" --auto-resume --heartbeat"
if ($WarmupDbPath) {
    $ActionArgs += " --warmup-from-db `"$WarmupDbPath`""
}
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ActionArgs `
    -WorkingDirectory $WorkDir

# ── Build triggers ────────────────────────────────────────────────────
# Trigger 1: at system startup (with delay for CST license)
$TriggerStartup = New-ScheduledTaskTrigger `
    -AtStartup `
    -RandomDelay (New-TimeSpan -Minutes $DelayMinutes)

# ── Build settings ────────────────────────────────────────────────────
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 72) `
    -MultipleInstances IgnoreNew

# ── Register the workflow task ────────────────────────────────────────
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

try {
    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $TriggerStartup `
        -Settings $Settings `
        -Principal $Principal `
        -Description "CST Workflow 2 — startup launch; watchdog handles crash recovery"

    Write-Host "SUCCESS: Workflow task '$TaskName' registered."
    Write-Host "  Trigger: AtStartup"
    Write-Host ""

    # ── Register the watchdog task (every 5 min heartbeat check) ──────
    $WatchdogName = "${TaskName}_Watchdog"
    $WatchdogScript = Join-Path $WorkDir "scripts\watchdog.ps1"
    if (-not (Test-Path $WatchdogScript)) {
        Write-Warning "Watchdog script not found at $WatchdogScript — skipping watchdog registration"
    } else {
        Unregister-ScheduledTask -TaskName $WatchdogName -Confirm:$false -ErrorAction SilentlyContinue

        $WatchdogArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$WatchdogScript`""
        if ($WarmupDbPath) {
            $WatchdogArgs += " -WarmupDbPath `"$WarmupDbPath`""
        }
        $WatchdogAction = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument $WatchdogArgs `
            -WorkingDirectory $WorkDir

        # Trigger: every 5 minutes, indefinitely
        $WatchdogTrigger = New-ScheduledTaskTrigger `
            -Once `
            -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 3650)

        $WatchdogSettings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
            -MultipleInstances IgnoreNew `
            -Hidden

        Register-ScheduledTask `
            -TaskName $WatchdogName `
            -Action $WatchdogAction `
            -Trigger $WatchdogTrigger `
            -Settings $WatchdogSettings `
            -Principal $Principal `
            -Description "Heartbeat watchdog for CST Workflow 2 — checks every 5 min and launches if dead"

        Write-Host "SUCCESS: Watchdog task '$WatchdogName' registered."
        Write-Host "  Trigger: every 5 minutes"
    }

    Write-Host ""
    Write-Host "To view:   taskschd.msc"
    Write-Host "To remove: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
    Write-Host "           Unregister-ScheduledTask -TaskName '$WatchdogName' -Confirm:`$false"
    Write-Host "To run now: Start-ScheduledTask -TaskName '$TaskName'"
} catch {
    Write-Error "Failed to register task: $_"
    Write-Host ""
    Write-Host "Try running PowerShell as Administrator if this failed."
    exit 1
}
