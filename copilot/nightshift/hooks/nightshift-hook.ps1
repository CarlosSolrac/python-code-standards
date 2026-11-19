# Nightshift's GitHub Copilot CLI hook. Install it for the notification and agentStop events.
#
# It acts only in a session running a night: one whose id is recorded as `Session:` in a
# .nightshift\LOG-*.md whose Status is `in progress` or `waiting for reviews`, in any worktree
# of the repository. Every other session gets no output, so the hook is inert there.
#
# notification: a permission prompt was shown although nightshift runs in autopilot; record it
#   in the log's timeline.
# agentStop: the watchdog. Block the stop and tell the agent to continue the night.
#
# Any failure exits 0 without output: these events must never break the session.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidAssignmentToAutomaticVariable', 'Event', Justification = '-Event is the installed hook command line; $Event is automatic only inside event actions.')]
param([Parameter(Mandatory)][ValidateSet('notification', 'agentStop')][string]$Event)

function Invoke-Git {
    # Returns git's stdout lines, or nothing when git fails; stderr never reaches the caller.
    $ErrorActionPreference = 'Continue'
    $lines = & git @args 2>$null
    if ($LASTEXITCODE -ne 0) { return }
    return @($lines)
}

function Find-ActiveLog([string[]]$Directories, [string]$SessionId) {
    # The log lives at the root of the checkout that started the night, which can be any
    # worktree of this repository; porcelain paths use forward slashes even on Windows.
    # The project directory is searched too: with a separate git dir, worktree list names
    # the git directory rather than the checkout.
    $roots = @()
    foreach ($directory in $Directories) {
        $roots += $directory
        # @() keeps a one-line result an array; otherwise $top[0] would be its first character.
        $top = @(Invoke-Git -C $directory rev-parse --show-toplevel)
        if ($top.Count -eq 0) { continue }
        $roots += $top[0]
        foreach ($line in @(Invoke-Git -C $top[0] worktree list --porcelain)) {
            if ($line -clike 'worktree *') { $roots += $line.Substring(9) }
        }
    }

    $seen = @{}
    $best = $null
    foreach ($root in $roots) {
        $folder = [IO.Path]::GetFullPath((Join-Path $root '.nightshift'))
        if ($seen.ContainsKey($folder) -or -not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
        $seen[$folder] = $true
        foreach ($file in Get-ChildItem -LiteralPath $folder -Filter 'LOG-*.md' -File) {
            # Only the header, before the first section, counts: the body may quote such lines.
            $lines = @()
            foreach ($line in [IO.File]::ReadAllLines($file.FullName)) {
                if ($line.StartsWith('## ')) { break }
                $lines += $line
            }
            if (-not ($lines -cmatch '^Status: (in progress|waiting for reviews)$')) { continue }
            if (-not ($lines -ceq "Session: $SessionId")) { continue }
            if (-not $best -or [string]::CompareOrdinal($file.Name, $best.Name) -gt 0) { $best = $file }
        }
    }
    return $best
}

try {
    $ErrorActionPreference = 'Stop'
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json

    $sessionId = $payload.sessionId
    if (-not $sessionId) { $sessionId = $payload.session_id }
    if (-not $sessionId) { exit 0 }
    if ($Event -eq 'notification' -and $payload.notification_type -cne 'permission_prompt') { exit 0 }

    $directory = (Get-Location).Path
    if ($payload.cwd -and (Test-Path -LiteralPath $payload.cwd -PathType Container)) { $directory = $payload.cwd }
    $directories = @($directory)
    if ($env:COPILOT_PROJECT_DIR -and (Test-Path -LiteralPath $env:COPILOT_PROJECT_DIR -PathType Container)) { $directories += $env:COPILOT_PROJECT_DIR }
    $log = Find-ActiveLog $directories ([string]$sessionId)
    if (-not $log) { exit 0 }

    if ($Event -eq 'notification') {
        $content = [IO.File]::ReadAllText($log.FullName)
        $newline = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
        $time = (Get-Date).ToString('HH:mm', [Globalization.CultureInfo]::InvariantCulture)
        $text = "- $time Permission prompt shown although nightshift runs in autopilot: this session may be waiting for an approval.$newline"
        if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) { $text = $newline + $text }
        [IO.File]::AppendAllText($log.FullName, $text, (New-Object Text.UTF8Encoding $false))
        exit 0
    }

    $skill = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\SKILL.md'))
    $reason = "Nightshift watchdog: read $skill and continue tonight's night from its Start of every wake-up. Log: $($log.FullName)"
    [Console]::Out.WriteLine(([ordered]@{ decision = 'block'; reason = $reason } | ConvertTo-Json -Compress))
    exit 0
}
catch {
    exit 0
}
