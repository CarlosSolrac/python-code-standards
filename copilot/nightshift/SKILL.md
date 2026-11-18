---
name: nightshift
description: Work unattended through the current project's TODO and plan files overnight in GitHub Copilot CLI, one task per branch and draft PR, keeping a work log of every decision (options, pros and cons, why one was chosen) and every blocker. Started only by the user typing /nightshift.
disable-model-invocation: true
argument-hint: "[adversarial=once|thorough]"
---

# Nightshift (Copilot CLI)

This is the GitHub Copilot CLI version of the `nightshift` skill. The Claude Code version
lives in `nightshift/SKILL.md` of the python-code-standards repository; both share the same
goals, authority, log format and morning deliverable, and differ only in how the host keeps
the night running, denies prompts and reviews work. If you are not running in Copilot CLI,
stop: this file depends on Copilot's autopilot mode, its `agentStop` hook and its `task`
tool.

The user is asleep. Nobody will answer a question until morning, so a question is never a
reason to stop: make the call, write down why, and keep going. Never call `ask_user`. The
morning deliverable is a set of draft PRs plus one work log the user can read in five
minutes and act on.

Two ideas drive everything below:

1. **Everything must be undoable by closing a PR and deleting a branch.** That is what makes
   it safe to decide alone. Work that would escape that boundary is skipped and logged.
2. **The log is the memory.** The session can be compacted, restarted, or killed at any
   moment. Write to the log *before* acting on a decision and *after* every task changes
   state, so the next wake-up (or the user) can pick up from the file alone.

## Authority

Running nightshift is the user's standing request to do the following without asking. Every
other rule from the user's instruction files and skills still applies; wherever one of them
says "ask the user", "stop and ask", or "wait for approval", record a decision in the log
instead and act.

- Create a branch per task, commit, push it, and open a **draft** PR.
- Delete or move files; write schema migrations — on the task branch only, each recorded
  as a decision.

Outside the boundary — skip, log as a blocker or question, move on:

- Pushing to or merging into the default branch, force-pushing, merging any PR, deleting
  remote branches, rewriting published history.
- Anything that acts on the world beyond the repository: running migrations against real
  databases, deploying, publishing packages, sending messages, spending money, changing
  repository or account settings, editing files outside the repo and its worktrees.
- Committing secrets or credentials.

Dependencies, CI, hooks, and build or tool configuration are never changed overnight:
projects often guard them behind an approval, and nobody is awake to give it. A task that
needs such a change chooses it as a decision, writes no code that relies on it, since that
code could pass neither the checks nor a review, and ends `blocked`, with the exact change
or command under *Needs you*. Never install a package outside the project's declared
dependencies to make a check pass; a check that passes only in your own environment has
not passed.

## Host facts

- **Session id.** This session's id is the last folder name of the session folder shown in
  your session context (`.../session-state/<session-id>`). Subagents share it, and every
  hook payload carries it as `sessionId`.
- **Skill folder.** `<skill-dir>` below is the folder holding this file, normally
  `~/.copilot/skills/nightshift` (or `$COPILOT_HOME/skills/nightshift`).
- **Models.** Read the `## Models (Copilot)` block between
  `<!-- python-code-standards:models -->` markers in `~/.copilot/copilot-instructions.md`
  (or `$COPILOT_HOME/copilot-instructions.md`). Turn each display name into a `task` model
  id by lower-casing it and replacing spaces with hyphens (`Claude Opus 5.5` →
  `claude-opus-5.5`, `GPT-6 Astra` → `gpt-6-astra`). The *Coding model* runs task
  subagents (default `claude-opus-5.5`); the *Adversarial code-review model* runs every
  review (default `gpt-6-astra`). Never substitute Codex — the Codex plugin or companion
  script of the Claude version — for it; `gpt-5.3-codex` runs only as one of the deep
  reviewers in `adversarial=thorough` (*Reviews*).
- **Unattended permissions.** The user starts the night in autopilot with all permissions
  allowed (*Running it*). Autopilot denies any request that would still prompt, such as a
  hook's `ask` or a command that needs to leave the sandbox; such a denial says the CLI was
  unable to ask the user. Treat it as an authority-boundary blocker (*Blockers*). MCP input
  and consent requests, including URL prompts, are the exception: autopilot waits for an
  answer to them, which would stall the night. Never call an MCP tool that may ask for input,
  consent or a sign-in overnight; get the same result another way or log a blocker.
- **Clock.** Read times with `Get-Date -Format HH:mm` and `Get-Date -Format 'yyyy-MM-dd HH:mm'`
  (or `date +%H:%M` / `date '+%Y-%m-%d %H:%M'` in bash); never estimate one.

## Start of every wake-up

A wake-up is the user typing `/nightshift`, a prompt beginning `Nightshift watchdog:` from
the `agentStop` hook (*Keeping the night going*), or an autopilot continuation.

1. Find tonight's log: the newest `.nightshift/LOG-*.md` in the repository root whose
   `Status:` is `in progress` or `waiting for reviews`. If there is one, resume from it, with
   the settings recorded under `## Setup` (a watchdog prompt passes none). If the user typed
   `/nightshift`, set the log's `Session:` line to this session's id (*Host facts*), so the
   hook covers this session. If it is stale (see below), re-evaluate it first. Then retry
   any *Reviews pending* (see *When the reviewer is unavailable*) and go to *Work loop*. A
   task still marked `in progress` was interrupted; give it to a new task subagent, which
   continues in the existing worktree.

   A log is stale when its `Last update` is more than 24 hours old; one with no date there
   counts from the date in its file name. Such a night was abandoned rather than paused,
   and the repository may have moved on. Before resuming, re-evaluate every unfinished task
   against the repository as it is now: whether the default branch has moved, whether the
   work was merged or done another way, whether the task is still in its source file, and
   whether its branch and worktree still exist. Check every task before writing anything,
   then update the plan table and timeline in one write, so an interrupted re-evaluation
   leaves the log stale and the next wake-up repeats it. Resume only if open items remain:
   tasks still `todo` or `in progress`, or reviews pending. Otherwise write the *Morning
   summary*, set `Status: complete`, and stop with the *Close-the-session warning*.
2. Otherwise, if the user typed `/nightshift`, this is a new night: run the *Preflight*,
   then build the *Plan*. A watchdog prompt or an autopilot continuation with no open log
   means the night is over: reply that nightshift is complete and stop.

### Keeping the night going

A turn can end before the work does — the model decides it is finished, or the context is
compacted mid-thought — and nobody is awake to type `/nightshift` again. Two layers restart
it, and neither needs anything scheduled from inside the session:

- **Autopilot** sends continuation messages after a turn ends, up to the session's
  `--max-autopilot-continues` limit.
- **The `agentStop` hook** (`<skill-dir>/hooks/nightshift-hook.ps1`, installed as
  `~/.copilot/hooks/nightshift.json`) runs whenever this session's main agent ends a turn.
  While the log names this session and is `in progress` or `waiting for reviews`, it blocks
  the stop and starts a new turn with a prompt beginning `Nightshift watchdog:`. Copilot
  ends the turn anyway after eight consecutive blocks, so never end a turn on purpose while
  work remains.

Once the log says `complete`, the hook stays silent and the session stops normally.

### Preflight

Check once and record the results under `## Setup` in the log.

- Settings, from the arguments typed after `/nightshift`. There is one:
  `adversarial=once` (the default) or `adversarial=thorough`; see *Reviews*. Record the
  value in effect, and any argument you did not recognise, which is otherwise ignored.
- Session: write `Session: <session-id>` into the log header (see *Log format*).
- Hook: check that `~/.copilot/hooks/nightshift.json` (or `$COPILOT_HOME/hooks/`) exists and
  runs `nightshift-hook.ps1` for `agentStop` and for `notification` with matcher
  `permission_prompt`. If it does not, an early stop ends the night: log it under
  *Needs you* and continue.
- Models: read them (*Host facts*) and record the coding and review model ids in effect.
- Repository root (`git rev-parse --show-toplevel`) and default branch. Not a git
  repository: write the log, mark it `complete` with a blocker explaining that nightshift
  needs git to keep work reversible, and stop.
- `git fetch`; note whether `origin` exists and `gh auth status` succeeds. If pushing or PRs
  are unavailable, decide to keep branches local, log that decision, and continue.
- The project's own checks — find them in the instruction files, README, `pyproject.toml`,
  `package.json`, Makefile, CI workflows. Run them once on the default branch so you know
  which failures were already there before you touched anything.
- Reviewer: start a `general-purpose` agent and have it start a `code-review` agent with the
  review model that replies only `ok`, the same nesting the reviews use (*Reviews*). If
  it fails, follow *When the reviewer is unavailable*: the work goes on and every review
  waits until the reviewer answers.
- Add `.nightshift/` to `.git/info/exclude` so the log is never committed.

### Plan

Collect tasks from what the project already has: `TODO.md`/`TODO`, plan or roadmap files
(`docs/plans/`, `PLAN.md`, `ROADMAP.md`), `TODO:` notes the files themselves point to, and
open GitHub issues assigned to the user or labelled for the work if `gh` works. Skip a file
whose first line says it is not for nightshift. Do not invent work. Ideas you have along the
way go under `## Suggestions` in the log, not into the plan.

For each task write a one-line done-check (a command, test, or observable result). Vague
items ("Evaluate X, Y, Z") become a concrete deliverable — usually a written report in
`docs/` with a recommendation — and that interpretation is itself a decision to log.

Order: tasks others depend on first, then by how likely they are to finish. Record the order
and its reasoning as decision D1. Write the plan table, then start working.

## Work loop

Each task runs in its own subagent, so it starts with a fresh context and loads its skills
fresh instead of carrying hours of earlier work. This session is the coordinator: it keeps
the plan, the review retries and the morning summary, and does no task work itself.

Repeat until every task is `done` or `blocked`:

1. Pick the first `todo` task whose dependencies are `done`. Mark it `in progress` in the log
   with a timestamp.
2. Start one `task` subagent for it with `agent_type: "general-purpose"`, the coding model,
   and `mode: "sync"`, and wait for it. Sync matters: a background subagent would let the
   turn end and a watchdog wake-up start the same task a second time. Run one task at a
   time. The brief gives the task, its done-check, its branch base, its worktree if one
   exists, the log path, the review model id, the `adversarial` setting, and the full path
   of this file. It tells the subagent to read this file and follow *Authority*,
   *Host facts*, *Task steps*, *Reviews*, *Decisions*, *Blockers* and *Log format*; never
   to call `ask_user`; to start no other task; and to end by reporting the task's status and
   PR link. It also states that the coordinator explicitly requests nested delegation: the
   subagent must run every review in *Reviews* as its own `task` subagent, never review its
   own work in place.
3. When it returns, read the task's row in the log; the log is the record, not the report.
   A row still `in progress` means the subagent stopped early: start a new one for the same
   task. If that one also stops early, mark the task `blocked` and say so under *Needs you*.
4. Continue straight to the next task in the same turn.

When no task is left `todo`, write the *Morning summary*. If reviews are still pending, set
`Status: waiting for reviews`, wait 20 minutes (two sync `Start-Sleep -Seconds 600` shell
calls), retry them, update the summary, and repeat; if the turn ends meanwhile, the watchdog
resumes it. Once none are pending, set `Status: complete` and stop with the
*Close-the-session warning*. Do not look for more work.

### Close-the-session warning

Whenever the night ends with `Status: complete`, open the *Morning summary* and the final
reply with this banner, word for word. Terminal replies show no colours, so the coloured
emoji carry them:

```markdown
> 🛑🟥🟥🟥 **CLOSE THIS NIGHTSHIFT SESSION** 🟥🟥🟥🛑
>
> ⚠️ Start a fresh session for daytime work. This one ran unattended:
> - 🔓 it ran in autopilot with every permission allowed, so nothing would stop for you;
> - 🧠 its context is full of the night's work, so your instructions and skills are no
>   longer fresh in it.
```

### Task steps

The task subagent works through these:

1. Make a worktree so the user's own checkout is never disturbed, unless the brief names one:
   `git worktree add <repo-parent>/<repo-name>.nightshift/<task-slug> -b nightshift/<task-slug> origin/<default>`
   (plain `<default>` when there is no remote).
   If it depends on an unmerged nightshift branch, branch from that one instead and say in
   the PR body that it is stacked and must be retargeted to the default branch after its
   base merges. Set up the environment the project needs inside the worktree.
2. Do the task using the project's normal workflow — its instruction files, its skills, its
   tests, its review steps. Invoke every skill those instructions require (Python code
   follows `python-code-standards`) before starting work. Unattended work deserves more
   verification, not less: the user cannot watch you, so the checks are the only evidence
   the work is right. Get a review after every unit (see *Reviews*).
3. Each time you hit a choice the user would normally make, write a decision entry first,
   then act on it (see *Decisions*).
4. Hit a blocker → follow *Blockers*.
5. Finished: all done-checks and project checks pass (apart from failures you recorded as
   pre-existing), and the whole-branch and adversarial reviews are done or logged as
   pending (see *When the reviewer is unavailable*). Push, and open a draft PR whose body
   lists what changed, how it was verified, and the decision and blocker entries for this
   task, copied from the log. Mark the task `done` with the PR link. Remove the worktree
   once the branch is pushed; keep it if the push failed so nothing is lost, or while its
   reviews are pending.

## Reviews

In daytime work the user reviews each change; overnight nobody does, so a reviewer takes
that seat more often — small reviews catch a wrong turn before the next unit is built on it.
Every review is a fresh `task` subagent run with `mode: "sync"`, the review model and
`reasoning_effort: "high"`. Its brief names the worktree, the exact diff to review (the
command that prints it), the task and its done-check, and asks for a numbered list of
findings, each with severity, location, problem and a reproduction. Reviewers change
nothing. Handle findings as the user's review protocol says: reproduce every finding before
acting on it; fix only reproduced correctness issues, each with a regression test; a finding
that does not reproduce is noted in the task's timeline and changes nothing. Review points:

1. **After every unit.** A unit is one red-green cycle: a failing test and the code that
   passes it, or one self-contained edit for non-code work. Once its narrow gates pass, run
   a `code-review` agent on the uncommitted delta (`git diff` and untracked files), apply
   reproduced fixes, then commit the unit on the task branch. The commit marks the reviewed
   boundary, so the next review sees only new work.
2. **After applying fixes.** Re-review the fix before committing it. Stop after three
   rounds that each still produce reproduced findings. Of the findings left then, one that
   breaks what the task asked for or its done-check is a blocker; the rest go under
   *Suggestions* with their reproduction.
3. **Task complete.** Run a `code-review` agent on the whole task,
   `git diff <task base>...HEAD`, because unit reviews cannot see how the units fit together.
4. **Then challenge it.** Once that review is clean, run an adversarial review: a
   `general-purpose` agent with the review model, told to assume the work is wrong, to
   question whether the approach was right at all — the question the user would have asked
   had they been awake — and to change nothing. A finding that challenges the approach
   becomes a decision entry: keep the approach or change it, with the pros and cons of both.
   Other reproduced findings depend on the `adversarial` setting:
   - `once` (default): run it once per task. Fix a finding only where it breaks what the
     task asked for or its done-check, and give that fix an ordinary review, not another
     adversarial one. Edge cases beyond the task go under *Suggestions* with their
     reproduction, for the user to decide.
   - `thorough`: run it as a deep review — the review-model reviewer plus five more
     `general-purpose` reviewers on `gpt-6.1-sol`, `gpt-5.3-codex`, `gemini-4-argon`,
     `grok-4.7` and `mai-code-1.1-flash`, all six started in one response with
     `mode: "background"`, each with the same brief. Wait for all six with `read_agent` and
     `wait: true` before doing anything else, then consolidate:
     merge duplicates, note which models raised each finding (agreement raises confidence),
     and reproduce each before acting. Fix every reproduced defect, give each fix an
     ordinary review, and run the deep review again until it approves, for at most three
     rounds. Of the findings left after the third, one that breaks what the task asked for
     or its done-check makes the task `blocked`; the rest go under *Suggestions*. Never
     replace a reviewer whose model fails; log it under *Reviews pending*.

   Push after this step.

Design tradeoffs, which the protocol sends to the user, become decision entries instead.
Count the reviews per task in the plan table (for example `5 + adversarial`, or
`5 + deep ×2`) so the morning reader can see the work was reviewed, and put the adversarial
verdict, with the models that agreed, in the PR body.

### When the reviewer is unavailable

A review can fail mid-night — a usage limit, an outage, a model no longer offered. Work
never waits on the reviewer, but a failed review is postponed, not skipped: the user wants
every one of them run.

1. **Log the failure** under `## Reviews pending`: the task, which review point it was, the
   model, the error text, and the retry time if one was given. Note it in the timeline.
2. **Review with a stand-in meanwhile.** When a unit or fix review fails, run the same
   review through a `code-review` agent with the coding model, never one left to its
   configured default, which could be Codex. If the coding model is the one failing, use
   any other non-Codex model the session offers and name it in the log. Handle its findings
   as *Reviews* does. Never use Codex. The whole-branch and adversarial points have no stand-in. This review replaces
   none of the missed ones: they stay under *Reviews pending* and still run. Count these
   apart in the plan table (for example `2 + 3 stand-in`).
3. **Keep working.** Commit the unit anyway and record the last commit the review model did
   review. Finish the task as usual — push it and open its draft PR — with
   `Review pending` at the top of the PR body, followed by the stand-in reviews run
   meanwhile, and mark it `done — reviews pending`. Keep its worktree, because any review
   fixes will land there.
4. **Retry** before starting each task and on every wake-up, but not before a reported
   retry time.
5. **When the reviewer answers again**, run what was missed, oldest task first, before new
   work. Commits that missed their unit review get one review of
   `git diff <last reviewed commit>...HEAD`; then the task's whole-branch review and
   adversarial review. Handle the findings as above, push the fixes to the same PR, replace
   `Review pending` with the verdicts, mark the task `done`, remove its worktree, and remove
   the entry from *Reviews pending*. Each task's catch-up runs in a task subagent started as
   in *Work loop*, with the pending entry in its brief.

A model that is not offered at all will not recover on its own, so also put it under
**Needs you**.

## Decisions

The user asked for this specifically: for every question you would have asked them, show
what the options were, the pros and cons of **each** option, which one you chose, and why.
Options you rejected need their pros listed too — the user may weigh them differently, and
they cannot do that from a bare verdict. Add how to reverse the choice, so overruling you in
the morning is cheap.

Log a decision for: anything normally gated on approval (dependencies, deleting files, CI,
schema), interpreting an ambiguous task, choosing between designs or libraries, design
tradeoffs raised in review, and deviations from the project's stated rules. Do not log
routine implementation choices that any reviewer would expect.

## Blockers

A blocker is anything that stops the task's done-check from passing.

1. Find the cause before changing anything: read the full error, reproduce it, check what
   changed. Use a debugging skill if one is available.
2. Try up to three *different* approaches — a different fix, not the same command again.
   Keep them inside the repository, its worktrees and the project's own configuration: the
   user handed over a project, not the machine, so never search their home folder, drives,
   credential stores or network settings, and never copy details about the machine into
   the log. Log each attempt and its result in the blocker entry as you go.
3. Still blocked: mark the task `blocked`, state exactly what you need from the user, and
   mark tasks that depend on it `blocked` too (pointing at this blocker). If the partial work
   is worth keeping, push it and open a draft PR titled `[blocked] <task>`. Move on to the
   next task.

Something that would cross the authority boundary is a blocker immediately — no attempts.
A tool call denied because the CLI could not ask the user, or denied by a hook, is one:
log the exact tool call as the blocker, and run no other command to get the same result.

## Log format

Path: `.nightshift/LOG-<YYYY-MM-DD>.md` at the repository root, dated by the night's start.
Keep the sections in this order so the morning reader sees what needs them first:

```markdown
# Nightshift log — <project> — <YYYY-MM-DD>

Status: in progress | waiting for reviews | complete
Started: <YYYY-MM-DD HH:MM> · Last update: <YYYY-MM-DD HH:MM> · Finished: <YYYY-MM-DD HH:MM>
Session: <id of the Copilot session running the night>
Host: Copilot CLI

## Morning summary
<Written last. Once complete, the Close-the-session warning first. Done: N (PR links).
Blocked: N. Decisions worth reviewing, highest stakes first, one line each with a link to
the entry. Anything left running or left behind, such as worktrees kept after a failed push.>

## Needs you
- B2 — <one line: what is needed to unblock>
- D4 — <one line: a decision you may want to overrule>

## Plan
| # | Task | Source | Done-check | Status | Reviews | Branch / PR |
|---|------|--------|------------|--------|---------|-------------|

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
- Task <#> — <review point> — <model> failed <time>: <error>. Retry after: <time or "any time">.
  Last reviewed commit: <sha>.

## Setup
<preflight results: settings, models, hook, default branch, remote and gh status, checks found, pre-existing failures>

## Suggestions
<ideas outside the task list, not acted on>

## Timeline
- <time> <event>
```

Each `##` heading appears once: update a section in place, never append a second copy of
it. The hook appends permission-prompt lines at the end of the file, which is the
*Timeline*. Update `Last update` on every write.

## Running it

Start a Copilot CLI session in the repository with autopilot and every permission allowed,
for example `copilot --autopilot --allow-all --max-autopilot-continues 200`, and type
`/nightshift`, or `/nightshift adversarial=thorough` for a night that hardens each task
against every defect a six-model deep review finds. Start it with those flags rather than
`/allow-all` and `/autopilot` in an open session: the continuation limit is set only at
startup and defaults to five. Autopilot denies anything that would still prompt, so a tool
prompt cannot stall the night; the denied call ends as a blocker (*Blockers*). MCP input
and consent requests still wait for an answer (*Host facts*). The session must stay
open and the machine awake: the night lives in it. In the morning, open
`.nightshift/LOG-<date>.md` and read **Morning summary** and **Needs you** first, then close
the nightshift session and start a fresh one: it still allows every permission, and until
the log is `complete` its `agentStop` hook keeps restarting it. To end a night early, set
the log's `Status:` to `complete` or close the session; a typed "stop" is not enough,
because the hook turns the stop into another watchdog turn.
