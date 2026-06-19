<#
.SYNOPSIS
    Register a Windows Task Scheduler job to auto-restart Workflow 2 after reboot.

.DESCRIPTION
    Creates a scheduled task that runs at system startup (with a 2-minute delay)
    and re-launches ``run_workflow_2.py --auto-resume --heartbeat``.

    The task runs as the current user and is configured to:
    - Trigger at system startup
    - Not run if on battery (laptop)
    - Auto-terminate after 72 hours
    - Restart every 72 hours if still eligible

.EXAMPLE
    .\scripts\schedule_workflow2.ps1

    .\scripts\schedule_workflow2.ps1 -TaskName "CST_WF2_Auto" -DelayMinutes 5
#>

param(
    [string]$TaskName = "CST_Workflow2_AutoResume",
    [int]$DelayMinutes = 2,
    [string]$PythonExe = "",
    [string]$WorkDir = ""
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

Write-Host "Task Name:    $TaskName"
Write-Host "Python:       $PythonExe"
Write-Host "Script:       $ScriptPath"
Write-Host "Work Dir:     $WorkDir"
Write-Host "Delay:        ${DelayMinutes} min after startup"
Write-Host ""

# ── Build the action ──────────────────────────────────────────────────
$ActionArgs = "`"$ScriptPath`" --auto-resume --heartbeat"
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ActionArgs `
    -WorkingDirectory $WorkDir

# ── Build triggers ────────────────────────────────────────────────────
# Trigger 1: at system startup (with delay for CST license)
$TriggerStartup = New-ScheduledTaskTrigger `
    -AtStartup `
    -RandomDelay (New-TimeSpan -Minutes $DelayMinutes)

# Trigger 2: daily at 09:00, repeat every 4 hours (periodic health restart)
$TriggerDaily = New-ScheduledTaskTrigger `
    -Daily `
    -At "09:00" `
    -RepetitionInterval (New-TimeSpan -Hours 4)

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
        -Trigger $TriggerStartup, $TriggerDaily `
        -Settings $Settings `
        -Principal $Principal `
        -Description "CST Workflow 2 — auto-restart on boot + daily 09:00 with 4h repeat"

    Write-Host "SUCCESS: Workflow task '$TaskName' registered."
    Write-Host "  Triggers: AtStartup + Daily 09:00 (every 4h)"
    Write-Host ""

    # ── Register the watchdog task (every 5 min heartbeat check) ──────
    $WatchdogName = "${TaskName}_Watchdog"
    $WatchdogScript = Join-Path $WorkDir "scripts\watchdog.ps1"
    if (-not (Test-Path $WatchdogScript)) {
        Write-Warning "Watchdog script not found at $WatchdogScript — skipping watchdog registration"
    } else {
        Unregister-ScheduledTask -TaskName $WatchdogName -Confirm:$false -ErrorAction SilentlyContinue

        $WatchdogAction = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WatchdogScript`"" `
            -WorkingDirectory $WorkDir

        # Trigger: every 5 minutes, indefinitely
        $WatchdogTrigger = New-ScheduledTaskTrigger `
            -Once `
            -At (Get-Date -Hour 0 -Minute 0 -Second 0) `
            -RepetitionInterval (New-TimeSpan -Minutes 5)

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
