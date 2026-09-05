#!/usr/bin/env bash
# Pin Claude Code to the local Qwen model, or unpin it, at a chosen scope.
#
#   bin/set-model.sh qwen   global   pins every repository on this machine
#   bin/set-model.sh claude repo     unpins this repository only
#   bin/set-model.sh qwen   local    pins this repository without committing the choice
#
# Unlike a --settings profile, this edits the settings file itself, so pinning stays
# reversible: `claude` removes exactly the keys `qwen` added and leaves everything else --
# model, theme, enabledPlugins -- untouched.
#
# The embedded Python is duplicated in bin/set-model.ps1 so both platforms write byte
# identical JSON. Change one, change the other.

set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
profile=$repo_root/.claude/profiles/qwen.json

action=${1-}
scope=${2-}

case $scope in
global) target=$HOME/.claude/settings.json ;;
repo) target=$repo_root/.claude/settings.json ;;
local) target=$repo_root/.claude/settings.local.json ;;
*) target= ;;
esac

if [ -z "$target" ] || { [ "$action" != qwen ] && [ "$action" != claude ]; }; then
    printf 'usage: %s {qwen|claude} {global|repo|local}\n' "$0" >&2
    exit 2
fi

if [ ! -f "$profile" ]; then
    printf 'missing profile: %s\n' "$profile" >&2
    exit 1
fi

python3 - "$action" "$target" "$profile" "$scope" <<'PY'
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
PY
