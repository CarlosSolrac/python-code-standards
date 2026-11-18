<#
.SYNOPSIS
    Pin Claude Code to the local Qwen model, or unpin it, at a chosen scope.

.DESCRIPTION
    Unlike a --settings profile, this edits the settings file itself, so pinning stays
    reversible: `claude` removes exactly the keys `qwen` added and leaves everything else --
    model, theme, enabledPlugins -- untouched.

    The embedded Python is duplicated in bin/set-model.sh so both platforms write byte
    identical JSON. Change one, change the other.

    The script takes no declared parameters on purpose, matching bin\ai.ps1.

.EXAMPLE
    bin\set-model.ps1 qwen global
    bin\set-model.ps1 claude repo
#>

$ErrorActionPreference = 'Stop'

$action = if ($args.Count -ge 1) { $args[0] } else { '' }
$scope = if ($args.Count -ge 2) { $args[1] } else { '' }

$repoRoot = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $repoRoot '.claude/profiles/qwen.json'

$target = switch ($scope) {
    'global' { Join-Path $HOME '.claude/settings.json' }
    'repo' { Join-Path $repoRoot '.claude/settings.json' }
    'local' { Join-Path $repoRoot '.claude/settings.local.json' }
    default { $null }
}

if (-not $target -or ($action -ne 'qwen' -and $action -ne 'claude')) {
    [Console]::Error.WriteLine("usage: $PSCommandPath {qwen|claude} {global|repo|local}")
    exit 2
}

if (-not (Test-Path -LiteralPath $profilePath)) {
    [Console]::Error.WriteLine("missing profile: $profilePath")
    exit 1
}

$program = @'
import json
import pathlib
import shutil
import sys

action, target_path, profile_path, scope = sys.argv[1:5]
target = pathlib.Path(target_path)
profile_env = json.loads(pathlib.Path(profile_path).read_text(encoding="utf-8"))["env"]

if action == "claude" and not target.exists():
    print(f"{scope}: {target}")
    print("  nothing pinned")
    sys.exit(0)

data = {}
if target.exists():
    data = json.loads(target.read_text(encoding="utf-8"))
    if scope == "global":
        shutil.copyfile(target, target.with_name(target.name + ".bak"))

env = data.get("env", {})
if action == "qwen":
    env.update(profile_env)
else:
    for key in profile_env:
        env.pop(key, None)

if env:
    data["env"] = env
else:
    data.pop("env", None)

if data:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
elif target.exists():
    # Unpinning emptied a file that held nothing else; leave no stub behind.
    target.unlink()

base_url = env.get("ANTHROPIC_BASE_URL")
model = env.get("ANTHROPIC_MODEL")
print(f"{scope}: {target}")
print(f"  {model} at {base_url}" if base_url else "  Anthropic, on this account's own credentials")
'@

$program | & python - $action $target $profilePath $scope
exit $LASTEXITCODE
