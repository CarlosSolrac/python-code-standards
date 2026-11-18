#!/usr/bin/env bash
# Tests deny-unattended.sh against throwaway repositories: it acts only for a session that a
# running log in one of the repository's worktrees names, and stays silent for every other case.
set -u
hook="$(cd "$(dirname "$0")" && pwd)/deny-unattended.sh"
repo=$(mktemp -d)
trap 'rm -rf "$repo"' EXIT
git -C "$repo" init -q
mkdir -p "$repo/.nightshift" "$repo/sub"
failures=0

write_log() {  # write_log <file> <status> <session>
	printf '# Nightshift log\n\nStatus: %s\nSession: %s\n\n## Timeline\n- 01:00 start\n' \
		"$2" "$3" >"$repo/.nightshift/$1"
}

run() {  # run <dir> <event> <session>: print the hook's stdout
	printf '{"session_id":"%s","hook_event_name":"%s","cwd":"%s"}' "$3" "$2" "$1" |
		(cd "$1" && bash "$hook")
}

expect() {  # expect <name> <actual> <expected substring, or empty for no output>
	if { [ -z "$3" ] && [ -z "$2" ]; } || { [ -n "$3" ] && [[ $2 == *"$3"* ]]; }; then
		echo "ok   $1"
	else
		echo "FAIL $1: got '$2'"
		failures=$((failures + 1))
	fi
}

deny='"behavior":"deny"'
write_log LOG-2026-10-16.md "in progress" old-session
write_log LOG-2026-10-17.md "in progress" night-session
expect "denies the night's session" "$(run "$repo" PermissionRequest night-session)" "$deny"
expect "denies from a subdirectory" "$(run "$repo/sub" PermissionRequest night-session)" "$deny"
expect "passes another session" "$(run "$repo" PermissionRequest day-session)" ""
expect "denies for an older active log naming the session" \
	"$(run "$repo" PermissionRequest old-session)" "$deny"
expect "passes an empty session id" "$(run "$repo" PermissionRequest '')" ""

git -C "$repo" commit -q --allow-empty -m base
git -C "$repo" worktree add -q "$repo.wt" 2>/dev/null
expect "denies from a task worktree" "$(run "$repo.wt" PermissionRequest night-session)" "$deny"
mkdir -p "$repo.wt/.nightshift"
mv "$repo/.nightshift/LOG-2026-10-17.md" "$repo.wt/.nightshift/"
expect "denies for a night started in a linked worktree" \
	"$(run "$repo.wt" PermissionRequest night-session)" "$deny"
git -C "$repo" worktree add -q "$repo.task" 2>/dev/null
expect "denies from a task worktree beside the linked one that started the night" \
	"$(run "$repo.task" PermissionRequest night-session)" "$deny"
git -C "$repo" worktree remove "$repo.task"
write_log LOG-2026-10-18.md "in progress" other-night
expect "denies while another worktree runs a newer night" \
	"$(run "$repo.wt" PermissionRequest night-session)" "$deny"
rm "$repo/.nightshift/LOG-2026-10-18.md"
mv "$repo.wt/.nightshift/LOG-2026-10-17.md" "$repo/.nightshift/"
git -C "$repo" worktree remove --force "$repo.wt"

sep=$(mktemp -d)
git init -q --separate-git-dir "$sep.git" "$sep"
mkdir -p "$sep/.nightshift"
cp "$repo/.nightshift/LOG-2026-10-17.md" "$sep/.nightshift/"
expect "denies in a repository with a separate git dir" \
	"$(run "$sep" PermissionRequest night-session)" "$deny"
git -C "$sep" commit -q --allow-empty -m base
git -C "$sep" worktree add -q "$sep.task" 2>/dev/null
expect "denies from a task worktree of a separate-git-dir checkout" \
	"$(CLAUDE_PROJECT_DIR=$sep run "$sep.task" PermissionRequest night-session)" "$deny"
rm -rf "$sep" "$sep.git" "$sep.task"

write_log LOG-2026-10-17.md "waiting for Codex" night-session
expect "denies while waiting for Codex" "$(run "$repo" PermissionRequest night-session)" "$deny"

write_log LOG-2026-10-17.md "complete" night-session
expect "passes once complete" "$(run "$repo" PermissionRequest night-session)" ""

write_log LOG-2026-10-16.md "in progress" night-session
expect "denies for a resumed older log beside a newer complete one" \
	"$(run "$repo" PermissionRequest night-session)" "$deny"
write_log LOG-2026-10-16.md "complete" old-session

write_log LOG-2026-10-17.md "in progress" night-session
run "$repo" Notification night-session >/dev/null
expect "notification adds a timeline line" "$(tail -1 "$repo/.nightshift/LOG-2026-10-17.md")" \
	"Permission prompt shown"
run "$repo" Notification day-session >/dev/null
expect "notification ignores another session" \
	"$(grep -c 'Permission prompt shown' "$repo/.nightshift/LOG-2026-10-17.md")" "1"

nolog=$(mktemp -d)
git -C "$nolog" init -q
expect "passes a repository without a log" "$(run "$nolog" PermissionRequest night-session)" ""
rm -rf "$nolog"
expect "passes outside a repository" "$(run /tmp PermissionRequest night-session)" ""

[ "$failures" -eq 0 ] && echo "all passed" || { echo "$failures failed"; exit 1; }
