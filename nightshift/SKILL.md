---
name: nightshift
description: Work unattended through the current project's TODO and plan files overnight, one task per branch and draft PR, keeping a work log of every decision (options, pros and cons, why one was chosen) and every blocker. Started only by the user typing /nightshift.
disable-model-invocation: true
---

# Nightshift

The user is asleep. Nobody will answer a question until morning, so a question is never a
reason to stop: make the call, write down why, and keep going. The morning deliverable is a
set of draft PRs plus one work log the user can read in five minutes and act on.

Two ideas drive everything below:

1. **Everything must be undoable by closing a PR and deleting a branch.** That is what makes
   it safe to decide alone. Work that would escape that boundary is skipped and logged.
2. **The log is the memory.** The session can be summarised, restarted, or killed at any
   moment. Write to the log *before* acting on a decision and *after* every task changes
   state, so the next wake-up (or the user) can pick up from the file alone.

## Authority

Running nightshift is the user's standing request to do the following without asking. Every
other rule from CLAUDE.md files and skills still applies; wherever one of them says "ask the
user", "stop and ask", or "wait for approval", record a decision in the log instead and act.

- Create a branch per task, commit, push it, and open a **draft** PR.
- Add, remove or upgrade dependencies; delete or move files; edit CI, hooks, or build config;
  write schema migrations — on the task branch only, each recorded as a decision.

Outside the boundary — skip, log as a blocker or question, move on:

- Pushing to or merging into the default branch, force-pushing, merging any PR, deleting
  remote branches, rewriting published history.
- Anything that acts on the world beyond the repository: running migrations against real
  databases, deploying, publishing packages, sending messages, spending money, changing
  repository or account settings, editing files outside the repo and its worktrees.
- Committing secrets or credentials.

## Start of every wake-up

1. Find tonight's log: the newest `.nightshift/LOG-*.md` in the repository root whose
   `Status:` is `in progress` or `waiting for Codex`. If there is one, resume from it — retry
   any *Reviews pending* first (see *When Codex is unavailable*), then go to *Work loop*. A
   task still marked `in progress` was interrupted; continue it in its existing worktree.
2. Otherwise this is a new night. Run the *Preflight*, start the *Watchdog*, then build the
   *Plan*.

### Watchdog

A turn can end before the work does — Claude decides it is finished, or the context is
summarised mid-thought — and nobody is awake to type `/nightshift` again. So the skill
re-invokes itself: `CronCreate` with `cron: "7,27,47 * * * *"`, `prompt: "/nightshift"`,
`recurring: true`. It fires only while the session is idle, so it never interrupts work in
progress; it only restarts a session that stopped early. Record the job id under `## Setup`.
On resume, check `CronList` before creating another, so there is only ever one.

### Preflight

Check once and record the results under `## Setup` in the log.

- Repository root (`git rev-parse --show-toplevel`) and default branch. Not a git
  repository: write the log, mark it `complete` with a blocker explaining that nightshift
  needs git to keep work reversible, and stop.
- `git fetch`; note whether `origin` exists and `gh auth status` succeeds. If pushing or PRs
  are unavailable, decide to keep branches local, log that decision, and continue.
- The project's own checks — find them in CLAUDE.md, README, `pyproject.toml`,
  `package.json`, Makefile, CI workflows. Run them once on the default branch so you know
  which failures were already there before you touched anything.
- Codex: resolve the companion script
  (`ls ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | head -1`)
  and run `node "$CX" status --json`. If it is missing or fails, follow *When Codex is
  unavailable*: the work goes on and every review waits until Codex answers.
- Add `.nightshift/` to `.git/info/exclude` so the log is never committed.

### Plan

Collect tasks from what the project already has: `TODO.md`/`TODO`, plan or roadmap files
(`docs/plans/`, `PLAN.md`, `ROADMAP.md`), `TODO:` notes the files themselves point to, and
open GitHub issues assigned to the user or labelled for the work if `gh` works. Do not invent
work. Ideas you have along the way go under `## Suggestions` in the log, not into the plan.

For each task write a one-line done-check (a command, test, or observable result). Vague
items ("Evaluate X, Y, Z") become a concrete deliverable — usually a written report in
`docs/` with a recommendation — and that interpretation is itself a decision to log.

Order: tasks others depend on first, then by how likely they are to finish. Record the order
and its reasoning as decision D1. Write the plan table, then start working.

## Work loop

Repeat until every task is `done` or `blocked`:

1. Pick the first `todo` task whose dependencies are `done`. Mark it `in progress` in the log
   with a timestamp.
2. Make a worktree so the user's own checkout is never disturbed:
   `git worktree add <repo-parent>/<repo-name>.nightshift/<task-slug> -b nightshift/<task-slug> origin/<default>`
   (plain `<default>` when there is no remote).
   If it depends on an unmerged nightshift branch, branch from that one instead and say in
   the PR body that it is stacked and must be retargeted to the default branch after its
   base merges. Set up the environment the project needs inside the worktree.
3. Do the task using the project's normal workflow — its CLAUDE.md, its skills, its tests,
   its review steps. Invoke every skill those instructions require (Python code follows
   `python-code-standards`) again at the start of each task: over a long night, context
   summarisation drops skill text that was loaded hours earlier. Unattended work deserves
   more verification, not less: the user cannot watch you, so the checks are the only
   evidence the work is right. Get a Codex review after every unit (see *Codex reviews*).
4. Each time you hit a choice the user would normally make, write a decision entry first,
   then act on it (see *Decisions*).
5. Hit a blocker → follow *Blockers*.
6. Finished: all done-checks and project checks pass (apart from failures you recorded as
   pre-existing), and the whole-branch and adversarial Codex reviews are done or logged as
   pending (see *When Codex is unavailable*). Push, and open a draft PR whose body lists
   what changed, how it was verified, and the decision and blocker entries for this task,
   copied from the log. Mark the task `done` with the PR link. Remove the worktree once the
   branch is pushed; keep it if the push failed so nothing is lost, or while its reviews are
   pending. Before removing any worktree, stop its Codex service:
   `echo '{"cwd":"<worktree>"}' | node "$(dirname "$CX")/session-lifecycle-hook.mjs" SessionEnd`.
   Codex starts one service per worktree and stops only the session's own at session end,
   so otherwise every task leaves one running all night, holding its folder open.
7. Continue straight to the next task in the same turn. Ending the turn early only costs up
   to twenty idle minutes until the watchdog fires.

When no task is left `todo`, write the *Morning summary*. If reviews are still pending, set
`Status: waiting for Codex`, keep the watchdog, and end the turn; each watchdog wake-up
retries them and updates the summary. Once none are pending, set `Status: complete`, delete
the watchdog with `CronDelete`, and stop. Do not look for more work.

## Codex reviews

In daytime work the user reviews each change; overnight nobody does, so Codex takes that
seat more often — small reviews catch a wrong turn before the next unit is built on it.
Drive the companion script exactly as the user's CLAUDE.md *Codex Review Automation
Protocol* describes (trigger in the background, poll `status --json`, fetch with plain
`result <job-id>`, reproduce every finding before acting on it), at these points:

1. **After every unit.** A unit is one red-green cycle: a failing test and the code that
   passes it, or one self-contained edit for non-code work. Once its narrow gates pass, run
   a working-tree review of the uncommitted delta, apply reproduced fixes, then commit the
   unit on the task branch. The commit marks the reviewed boundary, so the next working-tree
   review sees only new work.
2. **After applying fixes.** Re-review the fix before committing it. Stop after three
   rounds that each still produce reproduced findings — that is a blocker.
3. **Task complete.** Review the whole task with `--scope branch --base <task base>`,
   because unit reviews cannot see how the units fit together.
4. **Then challenge it.** Once that review is clean, run
   `node "$CX" adversarial-review --background --scope branch --base <task base> "<task and its done-check>"`.
   The ordinary reviews ask whether the code is correct; this one asks whether the approach
   was right at all — the question the user would have asked had they been awake. A finding
   that reproduces as a defect is fixed like any other, and the fix gets an ordinary review.
   A finding that challenges the approach becomes a decision entry: keep the approach or
   change it, with the pros and cons of both. Push after this step.

Findings that do not reproduce: note them in the task's timeline and change nothing. Design
tradeoffs, which the protocol sends to the user, become decision entries instead. Count the
reviews per task in the plan table (for example `5 + adversarial`) so the morning reader can
see the work was reviewed, and put the adversarial verdict in the PR body.

### When Codex is unavailable

A review can fail mid-night — a usage limit, an outage, an expired login. Work never waits
on Codex, but a failed review is postponed, not skipped: the user wants every one of them run.

1. **Log the failure** under `## Reviews pending`: the task, which review point it was, the
   job id, the error text, and the retry time if Codex gave one. Note it in the timeline.
2. **Keep working.** Commit the unit anyway and record the last commit Codex did review.
   Finish the task as usual — push it and open its draft PR — with `Codex review pending` at
   the top of the PR body, and mark it `done — reviews pending`. Keep its worktree, because
   any review fixes will land there.
3. **Retry** before starting each task and on every wake-up, but not before a retry time
   Codex reported.
4. **When Codex answers again**, run what was missed, oldest task first, before new work.
   Commits that missed their unit review get one review with
   `--scope branch --base <last reviewed commit>`; then the task's whole-branch review and
   adversarial review. Handle the findings as above, push the fixes to the same PR, replace
   `Codex review pending` with the verdicts, mark the task `done`, remove its worktree, and
   remove the entry from *Reviews pending*.

A missing install or a failed login will not recover on its own, so also put it under
**Needs you**.

## Decisions

The user asked for this specifically: for every question you would have asked them, show
what the options were, the pros and cons of **each** option, which one you chose, and why.
Options you rejected need their pros listed too — the user may weigh them differently, and
they cannot do that from a bare verdict. Add how to reverse the choice, so overruling you in
the morning is cheap.

Log a decision for: anything normally gated on approval (dependencies, deleting files, CI,
schema), interpreting an ambiguous task, choosing between designs or libraries, design
tradeoffs raised in code review, and deviations from the project's stated rules. Do not log
routine implementation choices that any reviewer would expect.

## Blockers

A blocker is anything that stops the task's done-check from passing.

1. Find the cause before changing anything: read the full error, reproduce it, check what
   changed. Use a debugging skill if one is available.
2. Try up to three *different* approaches — a different fix, not the same command again.
   Log each attempt and its result in the blocker entry as you go.
3. Still blocked: mark the task `blocked`, state exactly what you need from the user, and
   mark tasks that depend on it `blocked` too (pointing at this blocker). If the partial work
   is worth keeping, push it and open a draft PR titled `[blocked] <task>`. Move on to the
   next task.

Something that would cross the authority boundary is a blocker immediately — no attempts.

## Log format

Path: `.nightshift/LOG-<YYYY-MM-DD>.md` at the repository root, dated by the night's start.
Keep the sections in this order so the morning reader sees what needs them first:

```markdown
# Nightshift log — <project> — <YYYY-MM-DD>

Status: in progress | waiting for Codex | complete
Started: <time> · Last update: <time> · Finished: <time>

## Morning summary
<Written last. Done: N (PR links). Blocked: N. Decisions worth reviewing, highest stakes
first, one line each with a link to the entry. Anything left running or left behind, such
as worktrees kept after a failed push.>

## Needs you
- B2 — <one line: what is needed to unblock>
- D4 — <one line: a decision you may want to overrule>

## Plan
| # | Task | Source | Done-check | Status | Codex reviews | Branch / PR |
|---|------|--------|------------|--------|---------------|-------------|

## Decisions
### D1 — <the question, phrased as you would have asked it> (task #)
Context: <one or two sentences>
| Option | Pros | Cons |
|--------|------|------|
| A ... | ... | ... |
| B ... | ... | ... |
**Chose:** B. **Why:** <reasoning>. **To reverse:** <how>.

## Blockers
### B1 — <task> (task #)
Symptom: <error, with the key lines of output>
Cause: <what you found, or "unknown">
Attempts: 1. <approach> → <result>  2. ...  3. ...
Needs from you: <the specific thing>

## Reviews pending
- Task <#> — <review point> — job <id> failed <time>: <error>. Retry after: <time or "any time">.
  Last reviewed commit: <sha>.

## Setup
<preflight results: default branch, remote and gh status, checks found, pre-existing failures>

## Suggestions
<ideas outside the task list, not acted on>

## Timeline
- <time> <event>
```

Timestamps use local time. Update `Last update` on every write.

## Running it

The user types `/nightshift` in a session whose permission mode will not stop for prompts
(for example auto mode, or an allowlist covering git, gh, the project's tools, and file
edits) — a single permission prompt otherwise stalls the whole night. The session must stay
open: the watchdog lives in it and dies with it. In the morning, open
`.nightshift/LOG-<date>.md` and read **Morning summary** and **Needs you** first.
