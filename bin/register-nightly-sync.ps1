<#
.SYNOPSIS
    Register the scheduled task that runs bin\nightly-sync.ps1 every night at 05:00.

.DESCRIPTION
    05:00 local is after Renovate's 02:00 UTC run has opened PRs and CI has merged the green
    ones. The task runs as the current user only while they are logged on, which a
    notification needs; a run missed while the machine was off or asleep starts as soon as it
    is available again. Re-running this script replaces the task.

.EXAMPLE
    bin\register-nightly-sync.ps1
    Start-ScheduledTask -TaskName 'python-code-standards nightly sync'
#>

$ErrorActionPreference = 'Stop'

$taskName = 'python-code-standards nightly sync'
$script = Join-Path $PSScriptRoot 'nightly-sync.ps1'

# Windows PowerShell 5.1, not pwsh: nightly-sync.ps1's notification needs its WinRT support.
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At '05:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

[void](Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Fast-forward $(Split-Path -Parent $PSScriptRoot) to origin/main and uv sync; see bin\nightly-sync.ps1." -Force)
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
