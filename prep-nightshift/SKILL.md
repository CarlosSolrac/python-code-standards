---
name: prep-nightshift
description: Ready the current repository for a /nightshift run while the user is awake. Checks that the night can run unattended, confirms tonight's scope, puts every input the task worktrees need on the default branch as a plan file with the decisions already made, flags task steps outside nightshift's authority, and lists the morning steps. Commits and pushes only after the user approves, and never starts /nightshift. Started only by the user typing /prep-nightshift.
disable-model-invocation: true
---

# Prep nightshift

Overnight, nightshift makes every call alone and logs it for the morning. This skill makes
those calls with the user first, so the night spends its hours on work instead of on
decisions the user might overrule, and no task ends blocked on something a minute of
daytime would have settled.

Nightshift's rules live in its own file; this one only points at them, so the two cannot
drift. Read `${CLAUDE_SKILL_DIR}/../nightshift/SKILL.md` first (or the installed `nightshift`
skill's `SKILL.md`). If neither exists, stop: there is no nightshift to prepare for. The
sections used below are *Authority*, *Preflight*, *Plan*, *Task steps* and *Running it*.

Ground rules, for the whole session:

- **Ask and wait.** The user is awake. End each step with what you found and the questions
  it raises, and wait for the answer before acting on it. Unlike nightshift, never decide
  a question alone.
- **Change nothing unapproved.** Read-only commands are fine. Every edit, commit, push,
  branch, or settings change waits for the user's yes to that change.
- **Never start the night.** Do not type, schedule, or simulate `/nightshift`, create its
  watchdog, or write its log. Only the user starts it.
- **Do not do tonight's tasks.** The one exception is a step the user asks to do in daytime
  first (step 4), which follows the project's normal workflow.

## Steps

### 1. Preflight

Check what nightshift's *Preflight* and *Running it* need, read-only, and report one line
per check, pass or fail:

- **Default branch matches origin.** `git fetch`; find the default branch
  (`git symbolic-ref --short refs/remotes/origin/HEAD` prints `origin/main`; drop the
  `origin/` prefix to get `main`); compare
  `git rev-list --left-right --count <default>...origin/<default>` (want `0 0`).
- **gh logged in.** `gh auth status`.
- **Codex answers.** Resolve `$CX` as nightshift's *Preflight* does and run
  `node "$CX" status --json`.
- **Permission mode will not prompt.** One prompt stalls the night (*Running it*). Read
  `permissions` in `.claude/settings.json`, `.claude/settings.local.json` and
  `~/.claude/settings.json`, and ask which mode the session that will run `/nightshift`
  uses. Auto mode passes; an allowlist must cover git, gh, `node "$CX"`, the project's
  checks, and edits in the task worktrees (`<repo-parent>/<repo-name>.nightshift/`), in
  `.nightshift/` at the repository root (the log) and in `.git/info/exclude`.
  Name what is missing; change settings only if the user asks.
- **Machine and session.** Remind the user to stop the machine sleeping and to keep this
  session open: nightshift's watchdog lives in the session and dies with it.

For each failure, offer the fix (pull or push the default branch, `gh auth login` for the
user to type, re-login to Codex) or say how nightshift will work around it: local branches
only, or reviews left pending.

### 2. Confirm scope

Collect the tasks exactly where nightshift's *Plan* will look: TODO files, plan and roadmap
files, `TODO:` notes those point to, and open issues if `gh` works. Show them as a table:
task, source, the done-check nightshift would likely write, and whether it can finish
overnight or will hit step 4. Ask the user to confirm, reword, remove or add.

Nightshift reads only files, so the answers must land in them. Propose each edit, then make
it once approved:

- **Reword** vague items into a deliverable ("Plan ...", "Suggest ...", "Evaluate ... and
  recommend one"), so the night does not have to interpret them.
- **Fence off** files that must not be worked with a first line such as
  `PAUSED until the user says otherwise: not for nightshift` or
  `Not for nightshift: <reason>`. Nightshift's *Plan* skips any file whose first line says
  so.
- **Pre-approve** inside the task's own text what the night may do that it would
  otherwise skip or log, for example `(approved: run each through uvx; do not add any as
  a dependency)`.

### 3. Find inputs the worktrees would miss

Each task runs in a worktree branched from `origin/<default>` (nightshift's *Task steps*),
so it sees nothing that exists only here. Look for what a confirmed task needs among:

- untracked and ignored files: `git status --porcelain --untracked-files=all --ignored`;
- uncommitted changes, and commits not on `origin/<default>`:
  `git log origin/<default>..<default>`, `git log origin/<default>..HEAD --stat` (the
  branch you are on), `git branch -vv`; inputs a task needs that sit on another branch
  move to the default branch once approved;
- plans, decisions and constraints that live only in this conversation or in the user's
  head.

For each, propose committing it (a source folder such as `handoff/`) or capturing it in a
plan file. Keep secrets and personal notes out, and say which files you left out and why.

Write the plan file as `docs/plans/<name>.md`, one per body of work, with:

- **Source material**, linked, and a line that this plan wins where they differ.
- **Decisions already made by the user**, opening with "Do not reopen these; log a
  decision only for choices this plan leaves open." End it with a **Not tonight** item
  listing every step moved out in step 4, with "Do not attempt them."
- **Tasks**: a table of #, task, depends on, done-check (a command or observable result),
  then one section per task saying exactly what to change.
- **Morning steps** (step 6).

Nightshift collects tasks from TODO files, plan files and issues alike, so each task must
live in one place. When a plan task takes over a TODO item, propose deleting that item;
when it takes over an issue, propose removing every assignment and label that makes
nightshift collect it, or leave the task in the issue and out of the plan.

Steps 4 to 6 fill in the rest of the draft.

### 4. Flag steps outside the authority

Walk every confirmed task and plan step against nightshift's *Authority*. Flag each step
that changes dependencies, CI, hooks (including a `hooks:` entry in a skill's
frontmatter), or build or tool configuration; that reaches outside the repository
(`~/.claude` files, install links, other repositories, filing external issues, deploying,
sending anything); or that deletes files the user would rather decide on. List each with
why it is outside, and offer:

- **Do it now, in daytime.** Build, test, review and commit it under the project's own
  workflow, so the night builds on it. It reaches the worktrees only once it is on
  `origin/<default>` (step 7).
- **Move it out.** Put it under *Not tonight* and *Morning steps*, and reword the task so
  nothing tonight depends on it.
- **Let it end blocked.** The task runs, stops at that step, and names the exact change
  under *Needs you*. Partial work only; say so.

### 5. Settle open decisions

Ask now what nightshift would otherwise decide alone and log: interpretations, design
choices, which task stacks on which. Write each answer into the plan file's decisions or
the task's text. The `adversarial=once|thorough` setting is typed by the user after
`/nightshift` (nightshift's *Preflight*); recommend one, do not record it.

### 6. List the morning steps

In the plan file and in your reply, in order: open the log and read *Morning summary* and
*Needs you* first (*Running it*); mark each draft PR ready for review and merge them in
dependency order, retargeting any stacked PR after its base merges; then every step moved out in step 4, each with its exact
command or change.

### 7. Commit and push after approval

Show `git status` and the full diff of every prepared file: plan files, edited TODO items,
fenced files, committed inputs. Revise until the user approves. Commit to the default
branch and push only on the user's explicit yes; this is that approval, not a standing
one. Then re-check that `<default>` equals `origin/<default>` and that nothing a task
needs is still untracked. Without a remote, worktrees branch from the local `<default>`
(nightshift's *Task steps*), so the commit alone is enough.

### 8. Hand over

Summarise what is ready and what was left out. Give the command for the user to type,
`/nightshift` or `/nightshift adversarial=thorough`, and repeat the step 1 reminders:
permission mode, no sleep, session open. Then stop.
