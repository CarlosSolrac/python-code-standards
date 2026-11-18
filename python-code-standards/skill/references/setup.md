# Setting up a repository

Read when asked to set up, configure, or upgrade a repository to follow these standards, or to start a new project.

## The setup script

Use `setup-standards.sh` rather than copying templates by hand. It writes CI and hook configuration, installs a git hook, runs `git add -A`, records the [models](#choose-the-models) for each coding host in its home (`~/.claude/CLAUDE.md` and `~/.claude/settings.json`, `~/.copilot/copilot-instructions.md`, and `~/.codex/AGENTS.md` for a Codex reviewer; with `-y`, the defaults, and only where none are recorded), [installs the skills](#installed-skills) in those homes, and with `--update` adds missing dev tools with `uv add --dev`, so first tell the user exactly that and wait for approval; `-y` only skips the script's own prompt, which cannot be answered from a non-interactive shell. Then run it from the repository root, with the options for the task below.

When this skill is a link into a clone, the script sits next to `skill/` in the clone:

```bash
bash "${CLAUDE_SKILL_DIR}/../setup/setup-standards.sh" -y
```

Otherwise setup installed this skill and kept a copy of itself in `~/.local/share/python-code-standards/`:

```bash
bash ~/.local/share/python-code-standards/setup-standards.sh -y
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

## Choose the models

Before installing, the script asks which coding hosts to configure, then three questions per host. Model names are free text; the suggested names are not checked.

| Host | Instruction file | Detected when |
| --- | --- | --- |
| `claude-code` | `~/.claude/CLAUDE.md`, plus `model` in `~/.claude/settings.json` | `~/.claude` exists |
| `copilot` | `$COPILOT_HOME/copilot-instructions.md` when `COPILOT_HOME` is set, else `~/.copilot/copilot-instructions.md`; no settings file | `COPILOT_HOME` names an existing directory, or `~/.copilot` exists |

The host question offers the hosts already configured (their file holds a models block), else the detected ones, else `claude-code`; `-y` takes that answer.

| Question | Used for | `-y` default, `claude-code` | `-y` default, `copilot` |
| --- | --- | --- | --- |
| Coordinator model | The main session's default; it runs the tests. | `sonnet` | `Claude Sonnet 5.5` |
| Coding model | Agents that write code. | `opus` (the alias for the latest Opus) | `Claude Opus 5.5` |
| Adversarial code-review provider, then its model | The adversarial code review. | `codex` (or `claude`), `gpt-5.4` | `copilot` (or `none`), `GPT-6 Astra` |

- The answers are stored in the host's instruction file, between `<!-- python-code-standards:models -->` and `<!-- /python-code-standards:models -->`, under `## Models` (`## Models (Copilot)` for Copilot). Everything else in the file is kept byte for byte; without a block, one is appended. A missing line in a block takes that host's default.
- On `claude-code` the coordinator is also written to `model` in `~/.claude/settings.json`, keeping its other keys. Copilot gets no model setting, because its key is unverified: pick the model in the picker or with `--model`; `picker` is an accepted answer.
- Every write of every host is shown, then confirmed once; `-y` assumes the confirmation. Each file is written to a temporary file beside it, then replaced. A host whose write fails is reported, the others are still written, and setup carries on, then fails at the end.
- A re-run without `-y` asks again, offering the stored answers as defaults. Choosing a new coordinator then replaces the `model` in `settings.json`; nothing else replaces an existing one.
- `-y` writes the defaults only for a host without a block, and keeps an existing block untouched. Before running with `-y`, tell the user these defaults; to choose others, they run the script in a terminal.
- A host that is not chosen keeps its block; the summary lists it as still configured. Delete the block to remove it.
- A host is refused when its markers do not form exactly one closed block (a start marker without a later end marker, an end marker before its start, or a repeated marker), its instruction file cannot be read, or its `settings.json` is not a JSON object: the file and the problem are reported, none of that host's files is written, the other hosts go ahead, and setup carries on, then fails at the end. Repair the file, then re-run.
- A file to write that is a symbolic link resolving outside the home directory (for example a `CLAUDE.md` kept in a repository) is shown with its target and needs its own confirmation; `-y` skips it, reports it, and setup carries on, then fails at the end. A `COPILOT_HOME` outside the home directory counts as inside.
- The summary reports Copilot as configured, not verified, with a checklist to run once per surface (VS Code agent mode, Copilot CLI): open a session, ask which models it was told to use, confirm each hook fires. The stop gate is configured for Claude Code only. When `COPILOT_HOME` moves the file, the summary warns that VS Code may read `~/.copilot` instead.
- `~` is the home directory Python's `Path.home()` returns, on Windows and in WSL alike; under WSL that is the Linux home, not the Windows one.
- Each block ends with a guard line telling that host not to open the other agents' instruction files unless a change touches them: `AGENTS.md` and `.github/copilot-instructions.md` for `claude-code`; `CLAUDE.md`, `.claude/` and `AGENTS.md` for `copilot`. A block written before the guard existed still reads back; `-y` keeps it as it is, so the guard arrives with the next run without `-y`.

## Installed skills

The script embeds two skills and installs them in the homes of the chosen hosts, as part of the same confirmed write:

| Skill | Goes to |
| --- | --- |
| `python-code-standards` (this skill) | `~/.claude/skills/` for `claude-code`; `$COPILOT_HOME/skills/`, else `~/.copilot/skills/`, for `copilot` |
| `review-standards` (what a reviewer checks; no coding how-to) | by the host's review provider: `codex` to `~/.agents/skills/`, `claude` to `~/.claude/skills/`, `copilot` to Copilot's skills directory, `none` nowhere |

- Each installed skill directory holds a `.managed-by` file. Setup writes only a missing directory or one holding that file, and only the files that differ. A directory without it, or one that is a link (such as a clone linked in by hand), is reported as not managed by setup and left as it is. A marked directory no host wants any more, after a provider change, is listed, never removed.
- A file inside a marked directory that is a link resolving outside the home directory follows the same rule as the instruction files: its own confirmation, and `-y` skips it and fails at the end.
- For a `codex` reviewer, Codex's `$CODEX_HOME/AGENTS.md` (else `~/.codex/AGENTS.md`) gets a `## Review scope` block between `<!-- python-code-standards:review -->` and `<!-- /python-code-standards:review -->`: "You are a reviewer. Do not load the `python-code-standards` or `design-spec` skills and do not open `CLAUDE.md`, `.github/copilot-instructions.md` or `.claude/`. Use the `review-standards` skill." Its markers differ from the models block's, the rest of the file is kept byte for byte, and bad markers refuse the file as for a host. When `AGENTS.override.md` exists beside it, the summary says the block will be ignored, because Codex reads that file instead.
- The script copies itself to `~/.local/share/python-code-standards/setup-standards.sh`, where this skill finds it when it is not a link into a clone.
- The summary ends with how well each reviewer is kept from this skill: structural for a `codex` reviewer, since this skill is in no directory Codex scans (it says so when something else put a copy in `~/.agents/skills` or in the repository's `.agents/skills`; setup only looks there, it never writes in the repository); advisory for `claude` and `copilot`, whose review skill shares a directory with this one. It then lists the overlaps that remain for the chosen hosts: Copilot also scans `~/.agents/skills`, and VS Code's Copilot also reads `~/.claude/skills`. Instructions narrow what a model loads; they do not forbid it.

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
