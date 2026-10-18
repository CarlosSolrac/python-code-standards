Not for nightshift: item 1 edits other repositories; items 2–7 moved to docs/plans/design-spec-review.md.

# TODO

1. **Fill the template.** Skill §8 sends every Standard pipeline to `template-0-summaries`, whose index holds only a README; `template-sqlmesh-duckdb` is empty. Until it is filled, eval 1 (template found) fails and eval 4 can't build its fixture. Planned for a separate session.

## Nightshift: turn permission prompts into blockers instead of stalls (option A)

Not for nightshift: it adds a hook to a skill's frontmatter.

**Why.** One unanswered permission prompt stalls a whole night. The task subagent waits, the
coordinator waits on it, and the watchdog fires only while the session is idle. A PreToolUse
hook's `"ask"` forces a prompt even in auto mode (hooks reference: "A hook's "ask" also forces a
permission prompt in auto mode"). template-sqlmesh-duckdb's `tools/hooks/guard_protected.py` is
one such hook.

**Change.** In `nightshift/SKILL.md` frontmatter, add `hooks:`. Hooks declared there register
when the user types `/nightshift` and last for the rest of that session.
- `PermissionRequest` (all tools): return
  `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"Unattended: nobody can approve this call. Do not retry it or work around it. Log it under Needs you in the nightshift log as a blocker, with the exact tool call, then continue with the next step."}}}`.
  Do not set `interrupt`.
- `Notification` with matcher `permission_prompt`: append a timeline line to the newest
  `.nightshift/LOG-*.md`. This is a backstop in case a prompt still appears.

**Test first**, in a throwaway folder (a scratchpad, not a real project):
1. Project settings with a PreToolUse hook that returns `"ask"` for Bash commands containing
   `probe-ask`, and an `ask` permission rule for `Bash(echo probe-rule*)`. A test skill carrying
   the frontmatter hooks above, which also writes a marker file.
2. Invoke the skill, then run `echo probe-ask` in the main session. Expected: denied, no prompt,
   message visible to Claude, marker written.
3. Repeat from a foreground general-purpose subagent. This checks subagent coverage, which the
   docs do not state.
4. Repeat with `echo probe-rule`, a rule-based ask, not a hook-based one.
5. Start a new session and confirm the hook is gone, so daytime prompts come back.
Record each result in the PR. If step 2 or 3 fails, switch to option B and say so. Option B is a
user-level hook in `~/.claude/settings.json` that denies only when the newest
`.nightshift/LOG-*.md` says `Status: in progress` or `waiting for Codex` and was updated within
the last 2 hours.

**Also update.**
- nightshift *Blockers*: a denied permission prompt is an authority-boundary blocker, so no
  attempts and no workaround commands.
- nightshift *Running it*: in the morning, close the nightshift session and start a fresh one,
  because it denies every prompt.
- prep-nightshift step 1: keep the permission-mode check, and say prompts now end as blockers
  rather than stalls. prep-nightshift step 6: add "close the nightshift session".

**Done-check.** All five test results are recorded. The repository's own checks pass. `git grep
-n PermissionRequest nightshift/SKILL.md` finds the hook.
