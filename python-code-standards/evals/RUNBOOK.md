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

Create `E:\_src\eval` as a separate git repository. Copy `evals/fixtures/` into
it. Create `runs/eval-N/with-skill` and `runs/eval-N/baseline` for each eval in
`evals/evals.json`.

Agent output must never be written inside this source repository.

## 4. Run the evals

For each eval in `evals/evals.json`, dispatch **two subagents in the same turn**:

- **A** works with the `python-code-standards` skill available.
- **B** works with no skill and no coding standards of any kind.

Both receive the same prompt and the same fixture files, and write output into
the matching run directory.

These constraints decide whether the results mean anything:

- Pass each prompt **verbatim** from `evals.json`. Do not rephrase it, expand it,
  add context about standards, typing, uv, or variable declarations, or hint at
  what is being measured. Improving the prompt supplies the answer and measures
  nothing.
- Do not review, correct, or comment on subagent output before grading. Record it
  as produced, including anything that looks wrong.
- Launch both subagents in the same turn. Running all A cases first and the B
  cases later compares across different conditions.
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
