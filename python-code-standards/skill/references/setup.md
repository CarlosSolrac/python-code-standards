# Setting up a repository

Read when asked to set up, configure, or upgrade a repository to follow these standards, or to start a new project.

## The setup script

Use `assets/setup-standards.sh` rather than copying templates by hand. It writes CI and hook configuration, installs a git hook, runs `git add -A`, and with `--update` adds missing dev tools with `uv add --dev`, so first tell the user exactly that and wait for approval; `-y` only skips the script's own prompt, which cannot be answered from a non-interactive shell. Then run it from the repository root, with the options for the task below:

```bash
bash "${CLAUDE_SKILL_DIR}/assets/setup-standards.sh" -y
```

## Set up a new repository

- Run `setup-standards.sh -y`.
- Every missing file is created. Existing files are never replaced, only [reported](#what-the-script-reports).

## Upgrade a repository set up earlier

- Run `setup-standards.sh -y --update`.
- Use it to pick up newer templates and tools, for example a fixed `tools/check_declarations.py`.
- Replaces only **outdated** files and `[tool.*]` tables. **Edited** ones are kept and listed.
- Adds the baseline's dev tools that `[dependency-groups] dev` lacks, with `uv add --dev`. A tool the project already names keeps its version. Without `--update`, `-y` only lists them.
- `pyproject.toml` is saved as `pyproject.toml.orig` before any table changes, because a comment added inside a table does not count as an edit.

## Replace files the user edited

- Run `setup-standards.sh -y --force`.
- Only when the user asks to discard their changes to these files.
- Replaces **outdated** and **edited** items. Each edited file is saved as `<file>.orig` first.

## Run it in a terminal

- No options: lists the outdated items and asks once before replacing them. Edited ones are kept. Then asks before adding missing dev tools.
- `--force`: also asks, separately, before replacing edited ones.
- Claude's shell cannot answer a prompt, so Claude always passes `-y`.

## What the script reports

A missing file is created. An existing one is listed with one of three statuses; `pyproject.toml` is compared one `[tool.*]` table at a time, and its `[project]`, dependencies, and tables the baseline does not define are never touched, except that missing dev tools are added as described above.

| Status | Meaning |
| --- | --- |
| current | Identical to the template; nothing to do. |
| outdated | An earlier version of the script wrote it and nobody edited it since, so replacing it loses nothing. |
| edited | Differs from every version the script has written: the user changed it, or the script never wrote it. |

- Backups are never staged. Compare each `.orig` file with its file, then delete it.
- Merge kept edits, such as the `"hooks"` block of `.claude/settings.json`, by hand.

## The first check

After installing, the script checks the whole repository once. The check is read-only: Ruff in report mode, the declaration checker, Pyright, and MyPy run directly, never through pre-commit, so no hook from an existing config runs and problems in existing code are listed, not fixed. A tool the project's own `pyproject.toml` does not install is reported as not run, as is the pre-commit git hook without `pre-commit`; re-run with `-y --update` to add them. Fixing them is a separate change for the user to approve; `uv run pre-commit run --all-files` applies Ruff's fixes and formatting. The hook it installs does apply them, but only to files in each later commit. Tests and coverage are separate checks.

## Templates

`assets/` holds the templates the script embeds, for copying into a repository by hand: `pyproject-baseline.toml` (the baseline for a new project), `pre-commit-config.yaml`, `gitattributes`, and `ci.yml`.

An application commits `uv.lock`: run `uv lock` once and commit it before CI, since `assets/ci.yml` installs with `--locked`.
