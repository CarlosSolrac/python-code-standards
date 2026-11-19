# Tests nightshift-hook.ps1 against throwaway repositories: it acts only for a session that an
# active log in one of the repository's worktrees names, and stays silent for every other case.
# Run it under each shell the hook must support, e.g. -Shell pwsh and -Shell powershell.exe.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Shell', Justification = 'Read inside Invoke-Hook, which the rule does not follow.')]
param(
    [string]$Shell = (Get-Process -Id $PID).Path,
    [string]$WorkRoot = [IO.Path]::GetTempPath()
)

$hook = Join-Path $PSScriptRoot 'nightshift-hook.ps1'
$skill = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\SKILL.md'))
$root = Join-Path ([IO.Path]::GetFullPath($WorkRoot)) ("nightshift-test-" + [guid]::NewGuid().ToString('N'))
$repo = Join-Path $root 'repo'
$wt = Join-Path $root 'repo.wt'
$plain = Join-Path $root 'plain'
$failures = 0
$utf8 = New-Object Text.UTF8Encoding $false
$promptLine = '^- \d\d:\d\d Permission prompt shown although nightshift runs in autopilot: this session may be waiting for an approval\.$'

function Invoke-TestGit {
    $ErrorActionPreference = 'Continue'
    & git @args 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git $args failed" }
}

function Write-TestLog([string]$Dir, [string]$Name, [string]$Status, [string]$Session, [switch]$NoTrailingNewline) {
    $folder = Join-Path $Dir '.nightshift'
    New-Item -ItemType Directory -Force $folder | Out-Null
    $text = "# Nightshift log`n`nStatus: $Status`nSession: $Session`n`n## Timeline`n- 01:00 start"
    if (-not $NoTrailingNewline) { $text += "`n" }
    $path = Join-Path $folder $Name
    [IO.File]::WriteAllText($path, $text, $utf8)
    return $path
}

function Clear-Logs {
    foreach ($dir in $repo, $wt) { Remove-Item -Recurse -Force (Join-Path $dir '.nightshift') -ErrorAction SilentlyContinue }
}

function Invoke-Hook([string]$EventName, [string]$Payload, [string]$Dir = $repo) {
    # Returns the hook's stdout as one string and sets $script:exitCode.
    Push-Location $Dir
    try {
        $out = $Payload | & $Shell -NoProfile -ExecutionPolicy Bypass -File $hook -Event $EventName 2>$null
        $script:exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
    return (@($out) -join "`n").Trim()
}

function New-Payload([string]$Session, [string]$Dir = $repo, [string]$IdKey = 'sessionId', [hashtable]$Extra = @{}) {
    $data = @{ $IdKey = $Session; cwd = $Dir; timestamp = 1763481600000 }
    foreach ($key in $Extra.Keys) { $data[$key] = $Extra[$key] }
    return ($data | ConvertTo-Json -Compress)
}

function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    if ($Ok) { Write-Output "PASS $Name" }
    else { Write-Output "FAIL $Name $Detail"; $script:failures++ }
}

function Test-Blocks([string]$Name, [string]$Out, [string]$Log) {
    $reason = $null
    try { $json = $Out | ConvertFrom-Json; if ($json.decision -eq 'block') { $reason = $json.reason } } catch { $reason = $null }
    $ok = $reason -and $reason.StartsWith('Nightshift watchdog: read ') -and
        $reason.IndexOf($skill, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $reason.EndsWith("Log: $Log", [StringComparison]::OrdinalIgnoreCase) -and $Out -notmatch "`n"
    Check $Name $ok "got '$Out'"
}

function Test-Silent([string]$Name, [string]$Out) {
    Check $Name (($Out -eq '') -and ($script:exitCode -eq 0)) "got '$Out', exit $script:exitCode"
}

try {
    $env:GIT_CEILING_DIRECTORIES = $root  # keep `plain` outside any enclosing repository
    New-Item -ItemType Directory -Force $repo, $plain | Out-Null
    Invoke-TestGit -C $repo init -q
    Invoke-TestGit -C $repo config user.email 'nightshift@example.invalid'
    Invoke-TestGit -C $repo config user.name 'Nightshift Test'
    Invoke-TestGit -C $repo commit -q --allow-empty -m base
    Invoke-TestGit -C $repo worktree add -q $wt

    $log = Write-TestLog $repo 'LOG-2026-11-17.md' 'in progress' 'night'
    Test-Blocks 'agentStop blocks for an in-progress log' (Invoke-Hook agentStop (New-Payload night)) $log
    Test-Blocks 'agentStop blocks from a task worktree' (Invoke-Hook agentStop (New-Payload night $wt) $wt) $log
    Test-Blocks 'snake_case session_id works' (Invoke-Hook agentStop (New-Payload night -IdKey session_id)) $log
    Test-Silent 'agentStop ignores another session' (Invoke-Hook agentStop (New-Payload day))

    $log = Write-TestLog $repo 'LOG-2026-11-17.md' 'waiting for reviews' 'night'
    Test-Blocks 'agentStop blocks while waiting for reviews' (Invoke-Hook agentStop (New-Payload night)) $log

    Write-TestLog $repo 'LOG-2026-11-17.md' 'complete' 'night' | Out-Null
    Test-Silent 'agentStop passes once complete' (Invoke-Hook agentStop (New-Payload night))

    Write-TestLog $repo 'LOG-2026-11-17.md' 'in progress (paused)' 'night' | Out-Null
    Test-Silent 'status must match exactly' (Invoke-Hook agentStop (New-Payload night))

    $quoted = Write-TestLog $repo 'LOG-2026-11-17.md' 'complete' 'night'
    [IO.File]::AppendAllText($quoted, "``````text`nStatus: in progress`n``````n", $utf8)
    Test-Silent 'status in the body is ignored' (Invoke-Hook agentStop (New-Payload night))
    $quoted = Write-TestLog $repo 'LOG-2026-11-17.md' 'in progress' 'night'
    [IO.File]::AppendAllText($quoted, "``````text`nSession: day`n``````n", $utf8)
    Test-Silent 'session in the body is ignored' (Invoke-Hook agentStop (New-Payload day))

    Clear-Logs
    Test-Silent 'agentStop passes without a log' (Invoke-Hook agentStop (New-Payload night))
    Test-Silent 'agentStop passes outside a repository' (Invoke-Hook agentStop (New-Payload night $plain) $plain)

    $env:COPILOT_PROJECT_DIR = $repo
    try {
        $log = Write-TestLog $repo 'LOG-2026-11-17.md' 'in progress' 'night'
        Test-Blocks 'COPILOT_PROJECT_DIR finds the log from outside the repository' (Invoke-Hook agentStop (New-Payload night $plain) $plain) $log
    }
    finally { Remove-Item Env:COPILOT_PROJECT_DIR -ErrorAction SilentlyContinue; Clear-Logs }

    $log = Write-TestLog $wt 'LOG-2026-11-17.md' 'in progress' 'night'
    Test-Blocks 'agentStop finds a log in the other worktree' (Invoke-Hook agentStop (New-Payload night)) $log

    Write-TestLog $repo 'LOG-2026-11-16.md' 'in progress' 'night' | Out-Null
    $log = Write-TestLog $repo 'LOG-2026-11-18.md' 'in progress' 'night'
    Test-Blocks 'newest of several active logs wins' (Invoke-Hook agentStop (New-Payload night)) $log

    Test-Silent 'malformed JSON passes' (Invoke-Hook agentStop '{"sessionId": "night", ')
    Test-Silent 'empty payload passes' (Invoke-Hook agentStop '')

    Clear-Logs
    $log = Write-TestLog $repo 'LOG-2026-11-18.md' 'in progress' 'night'
    $before = [IO.File]::ReadAllText($log)
    $prompt = @{ notification_type = 'permission_prompt'; message = 'Allow?' }
    $out = Invoke-Hook notification (New-Payload night -Extra $prompt)
    $after = [IO.File]::ReadAllText($log)
    $added = $after.Substring($before.Length)
    Check 'notification appends one prompt line' (($out -eq '') -and $after.StartsWith($before) -and
        $added.EndsWith("`n") -and ($added.Split("`n").Count -eq 2) -and
        ($added.TrimEnd("`n") -cmatch $promptLine)) "out '$out', added '$added'"

    $log = Write-TestLog $repo 'LOG-2026-11-18.md' 'in progress' 'night' -NoTrailingNewline
    $before = [IO.File]::ReadAllText($log)
    Invoke-Hook notification (New-Payload night -Extra $prompt) | Out-Null
    $lines = [IO.File]::ReadAllLines($log)
    Check 'notification adds a missing trailing newline first' (([IO.File]::ReadAllText($log)).StartsWith("$before`n") -and
        ($lines[-2] -ceq '- 01:00 start') -and ($lines[-1] -cmatch $promptLine)) "got '$($lines[-2..-1] -join '|')'"

    $before = [IO.File]::ReadAllText($log)
    $out = Invoke-Hook notification (New-Payload night -Extra @{ notification_type = 'agent_idle'; message = 'Idle' })
    Check 'notification ignores other types' (($out -eq '') -and ([IO.File]::ReadAllText($log) -ceq $before)) "out '$out'"

    $out = Invoke-Hook notification (New-Payload day -Extra $prompt)
    Check 'notification ignores another session' (($out -eq '') -and ([IO.File]::ReadAllText($log) -ceq $before)) "out '$out'"
}
catch {
    Write-Output "FAIL setup: $_"
    $failures++
}
finally {
    Remove-Item Env:GIT_CEILING_DIRECTORIES -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
}

if ($failures -eq 0) { Write-Output 'all passed'; exit 0 }
Write-Output "$failures failed"
exit 1
