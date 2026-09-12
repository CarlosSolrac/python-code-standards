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

## Codex Review Automation Protocol

When I ask you to implement a feature, refactor code, or fix a bug, run this cycle before
declaring the task complete.

Every `/codex:*` slash command is declared `disable-model-invocation: true`, so only I can
type them — you cannot. Drive the companion script directly instead, resolving its path at
run time because the version directory changes whenever the plugin upgrades:

    CX=$(ls ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | head -1)

1. **Implement.** Write the code and leave the *implementation* uncommitted. Intermediate
   commits the project's own workflow requires are exempt: where TDD mandates committing a
   failing test first, still make that commit.
2. **Gate before review.** Run the project's own narrow checks — lint, both type checkers,
   the relevant test file. Never send Codex code that does not already pass them. Its
   sandbox is read-only and often cannot run tests at all, so if you skip this step nothing
   runs them and the review is weaker than it looks.
3. **Trigger.** `node "$CX" review --background`. A dirty tree is reviewed at working-tree
   scope, so Codex sees only the uncommitted delta; to cover everything since the base use
   `--scope branch --base main`.
4. **Collect.** Poll `node "$CX" status --json` until `.running` is empty and
   `.latestFinished.status` is `completed`, then fetch the findings with
   `node "$CX" result <job-id>` — plain, not `--json`, which returns job metadata rather
   than the review text.
5. **Reproduce, then fix.** The findings are a validation gate, not a set of instructions.
   - Reproduce each finding before acting on it. If it does not reproduce, report that and
     change nothing. If it reproduces differently than described, fix what actually
     reproduces and say how it differed.
   - Apply fixes only for reproduced correctness issues.
   - Design tradeoffs come to me with a recommendation; do not settle them alone.
   - Add a regression test for each fix, and update any contract, docstring or spec the fix
     invalidates in the same change.
6. **Re-verify and present.** Re-run the gates, then show the unified diff for staging.
   Never commit or push without asking.

## Stop and ask before

- Adding, removing, or upgrading a dependency.
- Changing a database schema or writing a migration.
- Deleting or moving files.
- Editing CI, hooks, or build configuration.
- `git commit`, `git push`, or rewriting history.

## Reporting

Files changed. Commands run, with pass/fail. Anything unrun or unresolved.
