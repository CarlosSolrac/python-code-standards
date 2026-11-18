<#
.SYNOPSIS
    Fast-forward this clone's main to origin/main and sync the environment, or explain why not.

.DESCRIPTION
    Run nightly by the scheduled task bin\register-nightly-sync.ps1 creates, after Renovate's
    merges. It only ever fast-forwards: on another branch, with uncommitted changes, or with
    unpushed commits on main it fetches, logs why it stopped, and leaves the clone as it was.
    It never stashes, resets, or merges.

    Every run appends one line to %LOCALAPPDATA%\python-code-standards\nightly-sync.log,
    outside the repository so the log never dirties the tree. A skip or failure also shows a
    Windows notification.

    Written for Windows PowerShell 5.1, which the task runs: the notification uses a WinRT
    API that PowerShell 7 cannot load.

.EXAMPLE
    powershell -NoProfile -File bin\nightly-sync.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA 'python-code-standards'
$logPath = Join-Path $logDir 'nightly-sync.log'

function Write-Log([string] $outcome, [string] $detail) {
    if (-not (Test-Path -LiteralPath $logDir)) {
        [void](New-Item -ItemType Directory -Path $logDir)
    }
    Add-Content -LiteralPath $logPath -Value ('{0}  {1,-8} {2}' -f (Get-Date -Format s), $outcome, ($detail -replace '\s*\r?\n\s*', ' | ')) -Encoding UTF8
}

function Show-Toast([string] $text) {
    try {
        [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $lines = $xml.GetElementsByTagName('text')
        [void]$lines.Item(0).AppendChild($xml.CreateTextNode('python-code-standards nightly sync'))
        [void]$lines.Item(1).AppendChild($xml.CreateTextNode($text))
        # Windows PowerShell's own app ID: a notification needs a registered app to come from.
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch {
        Write-Log 'notice' "notification not shown: $($_.Exception.Message)"
    }
}

function Stop-Sync([string] $outcome, [string] $detail) {
    Write-Log $outcome $detail
    if ($outcome -eq 'skipped' -or $outcome -eq 'failed') {
        Show-Toast "${outcome}: $detail"
    }
    exit $(if ($outcome -eq 'failed') { 1 } else { 0 })
}

# Native commands do not throw on a nonzero exit, so each one is checked here. Windows
# PowerShell turns redirected stderr (git's progress lines) into errors, which 'Stop' would throw.
function Invoke-Native([string] $program, [string[]] $arguments) {
    $ErrorActionPreference = 'Continue'
    $output = & $program @arguments 2>&1 | ForEach-Object { "$_" } | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "$program $($arguments -join ' ') exited $LASTEXITCODE`: $($output.Trim())"
    }
    return $output.Trim()
}

try {
    [void](Invoke-Native 'git' @('-C', $repoRoot, 'fetch', '--prune', 'origin'))

    $branch = Invoke-Native 'git' @('-C', $repoRoot, 'rev-parse', '--abbrev-ref', 'HEAD')
    if ($branch -ne 'main') {
        Stop-Sync 'skipped' "on branch $branch, not main"
    }
    # Untracked files are ignored: a fast-forward that would overwrite one refuses on its own.
    if (Invoke-Native 'git' @('-C', $repoRoot, 'status', '--porcelain', '--untracked-files=no')) {
        Stop-Sync 'skipped' 'uncommitted changes on main'
    }
    $ahead = [int](Invoke-Native 'git' @('-C', $repoRoot, 'rev-list', '--count', 'origin/main..HEAD'))
    if ($ahead -gt 0) {
        Stop-Sync 'skipped' "main has $ahead unpushed commit(s)"
    }
    $before = Invoke-Native 'git' @('-C', $repoRoot, 'rev-parse', '--short', 'HEAD')
    if ([int](Invoke-Native 'git' @('-C', $repoRoot, 'rev-list', '--count', 'HEAD..origin/main')) -eq 0) {
        Stop-Sync 'current' "main already at origin/main ($before)"
    }

    [void](Invoke-Native 'git' @('-C', $repoRoot, 'merge', '--ff-only', 'origin/main'))
    $after = Invoke-Native 'git' @('-C', $repoRoot, 'rev-parse', '--short', 'HEAD')
    [void](Invoke-Native 'uv' @('sync', '--locked', '--directory', (Join-Path $repoRoot 'python-code-standards')))
    Stop-Sync 'synced' "$before..$after"
} catch {
    Stop-Sync 'failed' $_.Exception.Message
}
