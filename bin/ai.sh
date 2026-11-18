#!/usr/bin/env bash
# Switch Claude Code between the local Qwen model and Anthropic.
#
#   bin/ai.sh qwen   [claude args...]   local Qwen, served by Ollama
#   bin/ai.sh claude [claude args...]   Anthropic, on the account's own credentials
#
# Anthropic mode is the plain `claude` command with no environment overrides, so it keeps
# whatever authentication the account already has. Qwen mode applies a settings profile
# with --settings, which outranks both the user and the project settings files.
#
# This only works while ~/.claude/settings.json sets no ANTHROPIC_* variables. Claude Code
# merges `env` one key at a time and a lower level cannot unset a key a higher one defined,
# so anything pinned there leaks into Anthropic mode and cannot be removed from here.

set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
profile=$repo_root/.claude/profiles/qwen.json

mode=${1-}
[ $# -gt 0 ] && shift

case $mode in
qwen)
    if [ ! -f "$profile" ]; then
        printf 'missing profile: %s\n' "$profile" >&2
        exit 1
    fi
    base_url=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["env"]["ANTHROPIC_BASE_URL"])' "$profile")
    if ! curl -fsS -m 5 -o /dev/null "$base_url/api/tags"; then
        printf 'Ollama is not answering at %s\n' "$base_url" >&2
        exit 1
    fi
    exec claude --settings "$profile" "$@"
    ;;
claude)
    exec claude "$@"
    ;;
*)
    printf 'usage: %s {qwen|claude} [claude args...]\n' "$0" >&2
    exit 2
    ;;
esac
