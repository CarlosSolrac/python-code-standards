# CLAUDE.md

<!-- FILL IN: one or two sentences on what this repo is and who uses it.
     Example: "Knowledge Bridge — single-user orchestration service that pulls
     captures from Karakeep, summarizes them via Ollama, writes notes to Obsidian.
     SQLite for state. Single developer, no backwards-compatibility burden." -->

## Commands

<!-- FILL IN with the real commands for this repo. Verify each one runs before
     committing this file — a wrong command here is worse than no command. -->

```cmd
uv sync                      # install/refresh the environment
uv run pytest                # full test suite
uv run pytest path/to/test_x.py::test_name   # single test
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy .                # type check
```

Never run `pip` directly. Never activate a venv manually — use `uv run`.

## Layout

<!-- FILL IN: 3-6 lines. Where source lives, where tests live, where config lives,
     and anything non-obvious a newcomer would guess wrong about. -->

---

## 1. Think before coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

Asking costs one round trip. Guessing wrong costs a rewrite.

## 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for scenarios that can't occur.
- If you write 200 lines and it could be 50, rewrite it.

This governs structure, not rigor. Type annotations, docstrings, and the Python
standards below are never "extra" — they are the baseline, and they are not
what gets cut when simplifying.

Test: would a senior engineer call this overcomplicated?

## 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- If you notice unrelated dead code or a real bug outside scope, mention it — don't fix it.
- Delete imports, variables, and functions that *your* change orphaned. Leave pre-existing dead code alone.
- If a comment describes code you changed, update the comment. A stale comment is a bug you introduced.

Test: every changed line traces directly to the request. If you can't explain
why a line moved, revert it.

## 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Turn tasks into checkable goals:

- "Add validation" → write tests for invalid inputs, then make them pass.
- "Fix the bug" → write a failing test that reproduces it, then make it pass.
- "Refactor X" → tests green before and after, behavior unchanged.

Verify by running the commands above, not by inspection. "It should work" isn't
verification. If you can't run something, say so explicitly rather than
implying it passed.

For work spanning more than a couple of files or introducing a dependency,
state the plan first and wait for confirmation:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Skip the plan for single-file edits. Ceremony on trivial tasks is its own kind
of overcomplication.

## 5. Ask first

Stop and confirm before:

- Adding, removing, or upgrading a dependency.
- Changing the database schema, or writing a migration.
- Deleting files, or moving them between directories.
- `git commit`, `git push`, or anything that rewrites history.
- Changing anything under CI, hooks, or `pyproject.toml` build config.

## 6. Precedence

When rules conflict, higher wins:

1. Explicit instruction in the current request.
2. Python Code Standards (imported below).
3. Conventions already established in the file being edited.
4. Rules 1–5 above.

Where 2 and 3 collide in existing code: apply the standards to lines you add or
rewrite, leave surrounding lines as they are, and say in your reply that the
file is now mixed. Don't silently reformat the file to resolve the tension, and
don't silently downgrade new code to match old.

If a request conflicts with a rule here, follow the request and name the
conflict in one sentence.

---

# Python code standards

Mandatory for all Python in this repo.

@~/.claude/skills/python-coding-standards/SKILL.md
