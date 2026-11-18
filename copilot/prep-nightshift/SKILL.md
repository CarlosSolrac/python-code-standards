---
name: prep-nightshift
description: Ready the current repository for a /nightshift run in GitHub Copilot CLI while the user is awake. Checks that the night can run unattended, confirms tonight's scope, puts every input the task worktrees need on the default branch as a plan file with the decisions already made, flags task steps outside nightshift's authority, and lists the morning steps. Commits and pushes only after the user approves, and never starts /nightshift. Started only by the user typing /prep-nightshift.
disable-model-invocation: true
---

# Prep nightshift (Copilot CLI)

This is the GitHub Copilot CLI version of the `prep-nightshift` skill; the Claude Code
version lives in `prep-nightshift/SKILL.md` of the python-code-standards repository. It
prepares a night run by the Copilot `nightshift` skill, which keeps itself going with
autopilot and an `agentStop` hook and reviews with the Copilot review model. If you are not
running in Copilot CLI, stop and say so.

Overnight, nightshift makes every call alone and logs it for the morning. This skill makes
those calls with the user first, so the night spends its hours on work instead of on
decisions the user might overrule, and no task ends blocked on something a minute of
daytime would have settled.

Nightshift's rules live in its own file; this one only points at them, so the two cannot
drift. Read the Copilot nightshift skill first: `../nightshift/SKILL.md` next to this file,
or the installed `~/.copilot/skills/nightshift/SKILL.md`. If neither exists, or the one you
find is not the Copilot version (its title ends `(Copilot CLI)`), stop: there is no
nightshift to prepare for. The sections used below are *Authority*, *Host facts*,
*Preflight*, *Plan*, *Task steps* and *Running it*.

Ground rules, for the whole session:

- **Ask and wait.** The user is awake. End each step with what you found and the questions
  it raises, and wait for the answer before acting on it; use `ask_user` for choices. Unlike
  nightshift, never decide a question alone.
- **Change nothing unapproved.** Read-only commands are fine. Every edit, commit, push,
  branch, or settings change waits for the user's yes to that change.
- **Never start the night.** Do not type, schedule, or simulate `/nightshift`, switch on
  autopilot, or write its log. Only the user starts it.
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
- **Models set.** The `## Models (Copilot)` block exists in
  `~/.copilot/copilot-instructions.md` (nightshift's *Host facts*); report the coding and
  review model ids it gives, or the defaults that apply without it.
- **Reviewer answers.** Start a `general-purpose` agent and have it start a `code-review`
  agent with the review model that replies only `ok`: overnight, reviews run one level down,
  inside each task's subagent, so this tests the nesting too. A failure is not fatal —
  nightshift logs reviews as pending — but say so.
- **Watchdog hook installed.** `~/.copilot/hooks/nightshift.json` (or `$COPILOT_HOME/hooks/`)
  exists, parses, and runs `nightshift-hook.ps1` for `agentStop` and for `notification`
  with matcher `permission_prompt`, at a path that exists. Without it, a turn that ends
  early ends the night.
- **Session will not prompt.** The night needs a session started with autopilot and every
  permission allowed, for example
  `copilot --autopilot --allow-all --max-autopilot-continues 200`. Check that no
  `settings.json` (`~/.copilot/settings.json`, the repository's `.github/copilot/`
  settings) disables allow-all mode, and note any `defaultPermissionMode` the user set:
  without `--allow-all`, autopilot denies every call that would prompt, so tasks end
  blocked. Check also that no user or repository hook returns `ask` or `deny` for
  commands the night needs (git, gh, the project's checks, edits in the task worktrees
  `<repo-parent>/<repo-name>.nightshift/`, `.nightshift/` and `.git/info/exclude`). List
  the MCP servers configured (`/mcp`): autopilot waits for an answer to MCP input and
  consent requests, so name any a task may need that could ask for a sign-in or consent,
  and offer to sign in now or disable it for the night. Name what is missing; change
  settings only if the user asks.
- **Machine and session.** Remind the user to stop the machine sleeping and to keep the
  nightshift session open: autopilot and the watchdog live in it and die with it.

For each failure, offer the fix (pull or push the default branch, `gh auth login` for the
user to type, installing the hook as `docs/manual-setup.md` describes) or say how nightshift
will work around it: local branches only, or reviews left pending.

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
(`~/.copilot` or `~/.claude` files, install links, other repositories, filing external
issues, deploying, sending anything); or that deletes files the user would rather decide
on. List each with why it is outside, and offer:

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
`/nightshift` (nightshift's *Preflight*); recommend one, do not record it. `thorough` runs a
six-model deep review per task and costs far more premium requests.

### 6. List the morning steps

In the plan file and in your reply, in order: open the log and read *Morning summary* and
*Needs you* first, then close the nightshift session and start a fresh one without
allow-all (*Running it*); mark each draft PR ready for review and merge them in dependency
order, retargeting any stacked PR after its base merges; then every step moved out in
step 4, each with its exact command or change.

### 7. Commit and push after approval

Show `git status` and the full diff of every prepared file: plan files, edited TODO items,
fenced files, committed inputs. Revise until the user approves. Commit to the default
branch and push only on the user's explicit yes; this is that approval, not a standing
one. Then re-check that `<default>` equals `origin/<default>` and that nothing a task
needs is still untracked. Without a remote, worktrees branch from the local `<default>`
(nightshift's *Task steps*), so the commit alone is enough.

### 8. Hand over

Summarise what is ready and what was left out. Give the commands for the user to type: start
a new session with `copilot --autopilot --allow-all --max-autopilot-continues 200` in the
repository, then `/nightshift` or `/nightshift adversarial=thorough`. Repeat the step 1
reminders: autopilot with allow-all, hook installed, no sleep, session open. Then stop.
