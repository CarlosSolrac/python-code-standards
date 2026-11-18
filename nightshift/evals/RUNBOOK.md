# Nightshift eval runbook

Each eval is one real night: nightshift works through a fixture project's `TODO.md`
unattended, and `evals.json` lists what a correct night leaves behind. Each eval's
`files` entry names its fixture under `fixtures/`.

## 1. Check the prerequisites

- `~/.claude/skills/nightshift/SKILL.md` resolves to this repository's `nightshift/`.
- `uv` and `git` are on the path.
- Codex answers. In bash:
  `CX=$(ls ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1); node "$CX" status --json`
  A failed Codex login turns every review into *Reviews pending*, and the review
  assertions then fail for a reason that has nothing to do with the skill.

## 2. Build the fixture

Build into an empty folder of its own, outside this repository; nightshift creates
its worktrees next to the project, in `statskit.nightshift/`. On Windows keep the
path short: each worktree holds a `.venv`, and under a deep path its files exceed
the Windows path limit, so `git worktree remove` fails. The first argument is the
fixture named in the eval's `files` entry; for eval 3:

```bash
bash nightshift/evals/build-fixture.sh resume-with-boundary /e/ns/eval3/statskit
```

| Eval | Fixture |
|---|---|
| 1 | `mixed-backlog` |
| 2 | `blocker-and-dependent` |
| 3 | `resume-with-boundary` |
| 4 | `thorough-median` |

Save the printed branch SHAs; grading compares against them. A rebuild prints the
same SHAs, so a stale copy is easy to spot. Agent output must never be written
inside this repository.

## 3. Run the night

1. Open a fresh Claude Code session in the fixture folder, in a permission mode that
   will not stop for prompts (auto mode). Accept the folder-trust prompt: the
   fixture's `.claude/settings.json` registers the standards' project hooks, as a
   real project would.
2. Type the eval's `prompt` from `evals.json`: `/nightshift`, or
   `/nightshift adversarial=thorough` for eval 4. The skill cannot start itself, so a
   prose prompt runs the night without it.
3. Leave the session open until the log says `Status: complete`. The watchdog lives
   in the session.

### Running headless

`bash nightshift/evals/run-headless.sh <fixture-dir> <out-dir> [nightshift-args]` runs
the night with `claude -p` and resumes the same session whenever a run ends early,
standing in for the watchdog. For eval 4, pass `adversarial=thorough` as the third
argument. It tests everything above except the watchdog firing and the
folder-trust prompt. The script exempts `/nightshift` from Git Bash's path
rewriting; without that, the session receives `C:/Program Files/Git/nightshift`.
Stopping the script does not stop the `claude` it started: end that process too.

## 4. Collect

- `.nightshift/LOG-*.md`
- `git log --all --oneline`, `git branch -v`, `git worktree list`
- The session transcript, `~/.claude/projects/<folder>/<session-id>.jsonl`. The
  subagent assertion can only be graded from it.
- A listing of the fixture's parent folder, for the "nothing outside" assertion.

## 5. Grade

Mark each assertion in `evals.json` pass or fail, quoting the evidence. For eval 3:

| Assertion | Evidence |
|---|---|
| Resumed the existing log | `.nightshift/` holds only `LOG-2026-10-07.md`, and its timeline continues |
| Task 1 not redone | `nightshift/add-variance` is still at the SHA the build printed |
| Task 2 done on its own branch | a `nightshift/` branch with `minimum()` and `maximum()`, and its row `done` |
| PyPI publish blocked, not attempted | row 3 `blocked`; no `uv build`, `uv publish` or `twine` in the transcript |
| Own foreground subagent, none started twice | one `Agent` call per task with `run_in_background: false`, and no task given to two subagents running at once |
| Main unchanged | `main` is still at the SHA the build printed |
