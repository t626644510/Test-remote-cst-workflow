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

# ── Build the trigger (at startup with delay) ─────────────────────────
$Trigger = New-ScheduledTaskTrigger `
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

# ── Register the task ─────────────────────────────────────────────────
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

try {
    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Auto-restart CST Workflow 2 after system reboot with crash recovery"

    Write-Host "SUCCESS: Task '$TaskName' registered."
    Write-Host ""
    Write-Host "To view:   taskschd.msc"
    Write-Host "To remove: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
    Write-Host "To run now: Start-ScheduledTask -TaskName '$TaskName'"
} catch {
    Write-Error "Failed to register task: $_"
    Write-Host ""
    Write-Host "Try running PowerShell as Administrator if this failed."
    exit 1
}
