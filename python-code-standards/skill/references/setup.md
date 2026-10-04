# Setting up a repository

Read when asked to set up or configure a repository to follow these standards, or to start a new project.

## The setup script

Use `assets/setup-standards.sh` rather than copying templates by hand. It writes CI and hook configuration, installs a git hook, and runs `git add -A`, so first tell the user exactly that and wait for approval; `-y` only skips the script's own prompt, which cannot be answered from a non-interactive shell. Then run it from the repository root:

```bash
bash "${CLAUDE_SKILL_DIR}/assets/setup-standards.sh" -y
```

It never overwrites an existing file, so merge any it reports as skipped. Its check is read-only: Ruff in report mode, the declaration checker, Pyright, and MyPy run directly, never through pre-commit, so no hook from an existing config runs and problems in existing code are listed, not fixed. A tool the project's own `pyproject.toml` does not install is reported as not run; add the baseline's dev dependencies and re-run. Fixing them is a separate change for the user to approve; `uv run pre-commit run --all-files` applies Ruff's fixes and formatting. The hook it installs does apply them, but only to files in each later commit. Tests and coverage are separate checks.

## Templates

`assets/` holds the templates the script embeds, for copying into a repository by hand: `pyproject-baseline.toml` (the baseline for a new project), `pre-commit-config.yaml`, `gitattributes`, and `ci.yml`.

An application commits `uv.lock`: run `uv lock` once and commit it before CI, since `assets/ci.yml` installs with `--locked`.
