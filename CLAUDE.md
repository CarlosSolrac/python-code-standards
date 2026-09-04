# Global rules

Apply to every project. Precedence, highest first: the current request → the project's
CLAUDE.md → a skill covering the work → this file. Name any conflict in one sentence, then
follow the higher rule.

Python (`.py`, `.ipynb`): invoke the `python-code-standards` skill before reading or editing code.

## Before writing code

- State assumptions that change the solution. Two possible readings: ask, do not pick.
- A simpler approach exists: say so.
- Write the success check first: a test, a command, or an observable output.
- More than two files, or a new dependency: post a numbered plan (step → check) and wait.
  Single-file edits skip the plan.

## While writing code

- Build only what was asked. No extra features, options, abstractions, or handling for cases
  that cannot occur.
- Change only lines the request requires. Do not reformat, rename, or improve neighbours.
- Remove only what your change orphaned. Leave pre-existing dead code; mention it.
- Update every comment or docstring that describes code you changed.
- Never replace a whole function or file to make a local edit.
- Bug or dead code outside scope: report it, do not fix it.

## Existing style or config clashes with the standards

Stop before editing. Name the clash. Ask: convert the file, or match its style. Wait.

## Verification

- Run the project's own checks. "Verified" means the command ran and you read the output.
- Cannot run a check: open the reply with `UNVERIFIED`, list the exact commands. Never write
  "should pass".
- Read the diff before finishing.

## Stop and ask before

- Adding, removing, or upgrading a dependency.
- Changing a database schema or writing a migration.
- Deleting or moving files.
- Editing CI, hooks, or build configuration.
- `git commit`, `git push`, or rewriting history.

## Reporting

Files changed. Commands run, with pass/fail. Anything unrun or unresolved.
