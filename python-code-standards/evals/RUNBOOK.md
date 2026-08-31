# Eval runbook

You are running an evaluation of the `python-code-standards` skill. Work through
these steps in order. Stop and report if a step fails, rather than working
around it.

The goal is to measure whether the skill changes an agent's behavior. Several
steps constrain what you may do; those constraints are what make the result mean
anything.

## 1. Check the skill symlink

Confirm the skill actually loads before changing anything:

```
dir "C:\Users\carlo\.claude\skills\python-code-standards\SKILL.md"
```

If that resolves, the link is correct — skip the rest of this step.

If it does not, the likely cause is that the whole skills directory was linked at
a single skill rather than a skill being linked inside it. In that case:

```
rmdir "C:\Users\carlo\.claude\skills"
mkdir "C:\Users\carlo\.claude\skills"
mklink /D "C:\Users\carlo\.claude\skills\python-code-standards" "E:\_src\python-code-standards\python-code-standards\skill"
```

`rmdir` on a directory symlink removes the link, not the target. Re-run the `dir`
check above afterwards.

## 2. Verify the toolchain on this machine

```
uv sync --all-groups
uv run pytest -q
uv run ruff check skill/tools tests evals/grade.py skill/assets/conformance.py
uv run python skill/tools/check_declarations.py skill/tools tests evals/grade.py
```

Expect 59 tests passing and clean output from the rest. This has only been
verified on Linux with CPython 3.13.13, so a Windows-specific failure is
plausible. Report one rather than patching around it.

## 3. Set up the scratch repository

Copy `evals/agents/eval-runner.md` into `.claude/agents/` in the scratch
repository. Every sample in both arms runs through that subagent, so the model
and effort are pinned in one file rather than inherited per session. The ad-hoc
Agent tool does not expose effort, which is why the n=3 run could not verify that
the two arms matched. Record the pinned values in `STATE.md` and confirm they are
unchanged before each pass.


Create `E:\_src\eval` as a separate git repository. Copy `evals/fixtures/` into
it. Create `runs/eval-N/with-skill` and `runs/eval-N/baseline` for each eval in
`evals/evals.json`.

Agent output must never be written inside this source repository.

## 4. Run the evals

The skill is installed personally, so every subagent can see it. A baseline
subagent merely *told* not to use skills may load it anyway, which would void the
comparison. Isolate the two arms by making the skill physically absent for the
baseline pass:

**Pass 1 — baseline.** Remove the link first:

```
rmdir "C:\Users\carlo\.claude\skills\python-code-standards"
```

Prefer `mv` to a stash path over `rmdir`: it is reversible and needs no symlink
privilege. Confirm the skill is gone, **then start a fresh session** — the skill
listing injected into subagents is cached per session, so a stale one will keep
advertising the skill's `description` to baseline agents even once the body is
unreachable. That description names strict typing and the tooling, so leaving it
visible partially contaminates the baseline.

Then run every eval's **B** arm, writing to `runs/eval-N/baseline`.

**Pass 2 — with skill.** Restore the link:

```
mklink /D "C:\Users\carlo\.claude\skills\python-code-standards" "E:\_src\python-code-standards\python-code-standards\skill"
```

Confirm `SKILL.md` resolves, then run every eval's **A** arm, writing to
`runs/eval-N/with-skill`.

Both arms receive the same prompt and the same fixture files. Do not run the two
passes interleaved: the whole point is that the skill is unreachable during pass
1 and reachable during pass 2.

These constraints decide whether the results mean anything:

- Pass each prompt **verbatim** from `evals.json`. Do not rephrase it, expand it,
  add context about standards, typing, uv, or variable declarations, or hint at
  what is being measured. Improving the prompt supplies the answer and measures
  nothing.
- Do not review, correct, or comment on subagent output before grading. Record it
  as produced, including anything that looks wrong.
- Run each pass in a single sitting so conditions do not drift between evals
  within a pass.
- One run per arm supports only a structural yes/no result (was a file created,
  did the skill trigger). Baseline behaviour varies between runs, so any numeric
  delta needs at least three samples per arm before it means anything.
- In each **A** transcript, confirm the skill actually loaded. A run where it did
  not is not a with-skill run; note it and rerun.
- Run eval 6 ("clean up this script") at least three times. It tests whether the
  skill triggers unprompted, which is probabilistic.
- Run eval 5 as the fourth or fifth task inside one long session, not fresh. It
  tests whether the rules survive context pressure.

## 5. Grade

From this repository:

```
uv run python evals/grade.py <runs>/eval-N/with-skill <runs>/eval-N/baseline --json scores-N.json
```

The measurement is the difference between the two rows, not either row alone.

Only the `decl` column is unconfounded. Ruff and Pyright counts depend on what
each run happens to ship and on whether its dependencies are installed in the
grader's environment, so treat them as context and read the per-rule breakdown in
the JSON rather than the totals.

## 6. Report

Give a table of with-skill against baseline for each eval: declaration
violations, Ruff violations, Pyright errors.

Then answer these four questions, which the grader cannot:

1. On the eval 6 runs, did the skill trigger without being named, and in how many
   of the runs?
2. On evals 2 and 3, run `git diff --stat` in the scratch repository. Did the
   with-skill agent change only what the prompt asked for, or did it reformat or
   otherwise improve unrelated code?
3. On evals 2 and 3, did the with-skill agent report the conflict between the
   repository's existing style and the standards, or silently rewrite?
4. In each with-skill transcript, did the agent claim any check passed without
   running it? Quote any instance.

**Do not fix anything you find.** Report it. The point is to measure the skill as
written, and a fix applied during measurement destroys the measurement.
