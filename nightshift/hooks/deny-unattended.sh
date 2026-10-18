#!/usr/bin/env bash
# Nightshift's unattended-permission hook. Install it in ~/.claude/settings.json for
# PermissionRequest (all tools) and for Notification with matcher permission_prompt.
#
# It acts only in a session running a night: one whose id is recorded as `Session:` in a
# .nightshift/LOG-*.md whose Status is `in progress` or `waiting for Codex`, in any worktree
# of the repository. Subagents carry their parent's session id, so they are covered.
# Every other session gets no output, so its prompts appear as usual.
#
# PermissionRequest: deny the call, so it ends as a blocker instead of a stalled night.
# Notification: a prompt was shown anyway; record it in the log's timeline.
input=$(cat)
session=$(printf '%s' "$input" | grep -o '"session_id" *: *"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
[ -n "$session" ] || exit 0

# The log lives at the root of the checkout that started the night, which can be any
# worktree of this repository, while the call may come from a task worktree. Search them all,
# this checkout's root, and the root of the folder the session started in
# (CLAUDE_PROJECT_DIR): with a separate git directory, the list names that directory instead.
top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
worktrees=$(git worktree list --porcelain)
logs=("$top"/.nightshift/LOG-*.md)
if started=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null); then
	logs+=("$started"/.nightshift/LOG-*.md)
fi
while IFS= read -r line; do
	[[ $line == "worktree "* ]] && logs+=("${line#worktree }"/.nightshift/LOG-*.md)
done <<<"$worktrees"
log=""
for f in "${logs[@]}"; do
	[ -f "$f" ] || continue
	grep -qE '^Status: (in progress|waiting for Codex)$' "$f" || continue
	grep -qxF "Session: $session" "$f" || continue
	[ -n "$log" ] && [[ ${f##*/} < ${log##*/} ]] || log=$f # keep the newest by file name
done
[ -n "$log" ] || exit 0

case $input in
*'"hook_event_name":"Notification"'* | *'"hook_event_name": "Notification"'*)
	printf -- '- %s Permission prompt shown although nightshift denies them: this session may be waiting for an approval.\n' \
		"$(date +%H:%M)" >>"$log"
	;;
*)
	printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"Unattended: nobody can approve this call. Do not retry it or work around it. Log it under Needs you in the nightshift log as a blocker, with the exact tool call, then continue with the next step."}}}'
	;;
esac
