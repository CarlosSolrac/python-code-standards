# Eval runbook

Paste the block below into Claude Code (the Code tab in Claude Desktop), opened
on `E:\_src\python-code-standards\python-code-standards`.

It is written as an instruction to the agent, not as documentation. The
constraints in step 4 are the ones that make the result meaningful; everything
else is setup.

---

```
Work through these steps in order. Stop and tell me if any step fails rather
than working around it.

1. FIX THE SKILL SYMLINK

   The symlink currently points the whole skills directory at one skill, so no
   skill loads. Verify this is the case, then fix it:

     rmdir "C:\Users\carlo\.claude\skills"
     mkdir "C:\Users\carlo\.claude\skills"
     mklink /D "C:\Users\carlo\.claude\skills\python-code-standards" ^
       "E:\_src\python-code-standards\python-code-standards\skill"

   rmdir on a directory symlink removes the link, not the target. Confirm
   afterwards that SKILL.md appears at the top level of
   C:\Users\carlo\.claude\skills\python-code-standards.

2. VERIFY THE TOOLCHAIN ON THIS MACHINE

     uv sync --all-groups
     uv run pytest -q
     uv run ruff check skill/tools tests evals/grade.py skill/assets/conformance.py
     uv run python skill/tools/check_declarations.py skill/tools tests evals/grade.py

   Expect 59 tests passing and clean output from the other three. This was
   verified on Linux/CPython 3.13.13 only, so a Windows-specific failure here is
   plausible and worth reporting rather than patching around.

3. SET UP THE SCRATCH REPOSITORY

   Create E:\_src\eval as a separate git repository. Copy evals/fixtures/ into
   it. Create runs/eval-N/with-skill and runs/eval-N/baseline for each eval in
   evals/evals.json. Agent output must never be written inside the source
   repository.

4. RUN THE EVALS

   For each eval in evals/evals.json, dispatch TWO subagents IN THE SAME TURN:

     - Subagent A works with the python-code-standards skill available.
     - Subagent B works with no skill and no coding standards of any kind.

   Both receive the SAME prompt and the SAME fixture files, and write their
   output into the matching run directory.

   These constraints decide whether the results mean anything:

     - Pass each prompt VERBATIM from evals.json. Do not rephrase it, expand it,
       add context about standards, typing, uv, or declarations, or hint at what
       is being measured. If you improve the prompt, you have supplied the answer
       and measured nothing.
     - Do not review, correct, or comment on subagent output before it is
       graded. Write it down as produced.
     - Launch both subagents in the same turn. Running all A cases first and the
       B cases later compares across different conditions.
     - Run eval 6 ("clean up this script") at least three times. It tests whether
       the skill triggers unprompted, which is probabilistic.
     - Run eval 5 as the fourth or fifth task inside one long session, not fresh.
       It tests whether the rules survive context pressure.

5. GRADE

   From the source repository:

     uv run python evals/grade.py <runs>/eval-N/with-skill <runs>/eval-N/baseline --json scores-N.json

   The measurement is the difference between the two rows, not either row alone.

6. REPORT

   Give me a table of with-skill vs baseline for each eval: declaration
   violations, Ruff violations, Pyright errors. Then answer these four questions,
   which the grader cannot:

     a. On the eval 6 runs, did the skill trigger without being named? How many
        of the runs?
     b. On evals 2 and 3, run `git diff --stat` in the scratch repo. Did the
        with-skill agent change only what the prompt asked for, or did it
        reformat or "improve" unrelated code?
     c. On evals 2 and 3, did the with-skill agent report the conflict between
        the repository's existing style and the standards, or silently rewrite?
     d. In each with-skill transcript, did the agent claim any check passed
        without actually running it? Quote any instance.

   Do not fix anything you find. Report it. The point is to measure the skill as
   written, and a fix applied during measurement destroys the measurement.
```

---

## Interpreting the result

A near-zero delta in declaration violations means the rule is not landing, and
the fix is to make it louder in `SKILL.md` — not to conclude the eval failed.

A low trigger rate on eval 6 means the `description` frontmatter needs work.
That field is the only thing loaded before the skill fires, so a perfect body
behind a weak description is worth nothing.

Failures in question (d) are the most serious: the verification-honesty rule is
the one place the standards ask the agent to say something against its own
apparent interest, and it is the hardest to enforce mechanically.
