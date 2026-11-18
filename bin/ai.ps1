<#
.SYNOPSIS
    Switch Claude Code between the local Qwen model and Anthropic.

.DESCRIPTION
    Anthropic mode is the plain `claude` command with no environment overrides, so it keeps
    whatever authentication the account already has. Qwen mode applies a settings profile
    with --settings, which outranks both the user and the project settings files.

    This only works while ~/.claude/settings.json sets no ANTHROPIC_* variables. Claude Code
    merges `env` one key at a time and a lower level cannot unset a key a higher one defined,
    so anything pinned there leaks into Anthropic mode and cannot be removed from here.

    The script takes no declared parameters on purpose. A param() block would let the
    PowerShell binder claim Claude's own switches -- `-p` binds to -ProgressAction -- instead
    of passing them through.

.EXAMPLE
    bin\ai.ps1 qwen
    bin\ai.ps1 claude --resume
#>

$ErrorActionPreference = 'Stop'

$mode = if ($args.Count -ge 1) { $args[0] } else { '' }
$claudeArgs = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

if ($mode -eq 'claude') {
    & claude @claudeArgs
    exit $LASTEXITCODE
}

if ($mode -ne 'qwen') {
    [Console]::Error.WriteLine("usage: $PSCommandPath {qwen|claude} [claude args...]")
    exit 2
}

# $profile is an automatic PowerShell variable, so the profile path needs its own name.
$profilePath = Join-Path (Split-Path -Parent $PSScriptRoot) '.claude/profiles/qwen.json'
if (-not (Test-Path -LiteralPath $profilePath)) {
    [Console]::Error.WriteLine("missing profile: $profilePath")
    exit 1
}

$baseUrl = (Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json).env.ANTHROPIC_BASE_URL
try {
    Invoke-WebRequest -Uri "$baseUrl/api/tags" -TimeoutSec 5 -UseBasicParsing | Out-Null
}
catch {
    [Console]::Error.WriteLine("Ollama is not answering at $baseUrl")
    exit 1
}

& claude --settings $profilePath @claudeArgs
exit $LASTEXITCODE
