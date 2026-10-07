# python-code-standards skill

Source of the `python-code-standards` skill for Claude Code. Install steps are in the
[top-level README](../README.md); this file covers what the skill is for and how to work on it.

## Why it exists

Three things an agent gets wrong unless told, and which no linter enforces:

- **Variable declaration.** Every variable is annotated before its first binding, so a wrong
  inference fails at the declaration instead of propagating. Ruff's `ANN` rules cover
  signatures only; `skill/tools/check_declarations.py` covers local bindings, instance
  attributes, and notebook cells.
- **Verification honesty.** A check counts as passed only when the command ran and its output
  was read. Otherwise the reply opens with `UNVERIFIED`.
- **Scope in repositories that do not follow the standards.** The agent runs what exists,
  reports the rest as unrun, and does not scaffold `pyproject.toml`, tests, or a lockfile to
  satisfy its own verification loop.

Everything else in `SKILL.md` is the toolchain those rules need: `uv`, Ruff, Pyright, MyPy,
pytest with coverage, and `pre-commit` to run them together. The `references/` files load
only when the work touches their topic, so they cost no tokens otherwise.

## Layout

```
skill/                  <- this is the installed skill; symlink or copy it
  SKILL.md
  references/           typing, testing, SQL/DuckDB, Pydantic, concurrency, packaging, repo setup
  assets/               templates copied into the repositories you work in
  tools/                bundled checker, invoked via ${CLAUDE_SKILL_DIR}
tests/                  tests for the checker, hooks, and grader  (development only)
docs/                   why each quality gate exists  (development only, never loaded)
evals/                  prompts, grader, runbook, pinned eval subagent (development only)
pyproject.toml          tooling for this repo, and the baseline the skill teaches
```

Only `skill/` is installed. `tests/` and `evals/` stay here — they verify the skill rather
than being part of it.

## Configuring a repository to follow the standards

CI and pre-commit run inside the target repository and cannot see the skill directory, so a
repository that adopts the tooling vendors its own copy of every config file and the checker.
`skill/assets/setup-standards.sh` does that in one step: it writes `pyproject.toml`,
`.pre-commit-config.yaml`, `.gitattributes`, `.gitignore`,
`.github/workflows/ci.yml`, `tools/check_declarations.py`, the change-scoped checks
(`tools/check_suppressions.py`, `tools/check_coverage_records.py`, and their approved-suppression
list `suppressions.toml`), report-only mutation testing (`tools/mutation.sh` and a nightly
`mutation.yml`), the review brief (`tools/review_brief.py`), and the Claude Code hooks
(`.claude/settings.json` and `tools/hooks/`, see [docs/quality-gates.md](docs/quality-gates.md)),
then pins Python 3.13, runs
`uv sync --all-groups`, installs the pre-commit hook, and runs the full check once. The check
is read-only: each tool runs directly in report mode, never through pre-commit, so existing
code is reported on, never rewritten, and no hook from an existing config runs.

Existing files are compared with their templates (`skill/tools/setup_files.py`); see
[what the script reports](skill/references/setup.md#what-the-script-reports).
Missing `[dependency-groups] dev` tools are listed, then added with `uv add --dev` after a
prompt, or unasked with `-y --update`. A tool the project already names keeps its version. Until
they are installed, the check lists them as not run, and the pre-commit git hook is not
installed.

The script is self-contained — every template and the checker are embedded — so it also runs
copied on its own to a host with no clone of this repo. `tests/test_setup_script.py` keeps the
embedded copies byte-identical to `skill/tools/` and `skill/assets/`. It recognizes earlier
versions by digests of every template the script has ever written; after changing a template,
regenerate them with `uv run python -m skill.tools.template_history`, or that test fails.

Run it from inside the target repository; it configures the repo your current directory is in,
not wherever the script lives. Pick the options for your task:

- **New repository:** no options, or `-y` to skip the prompts. See
  [Set up a new repository](skill/references/setup.md#set-up-a-new-repository).
- **Upgrade a repository set up earlier:** `-y --update`. See
  [Upgrade a repository set up earlier](skill/references/setup.md#upgrade-a-repository-set-up-earlier).
- **Replace files you edited:** `-y --force`. See
  [Replace files the user edited](skill/references/setup.md#replace-files-the-user-edited).

```bash
cd <target-repo>
~/.claude/skills/python-code-standards/assets/setup-standards.sh
```

```powershell
Set-Location <target-repo>
bash "$env:USERPROFILE\.claude\skills\python-code-standards\assets\setup-standards.sh"
```

```cmd
cd /d "<target-repo>"
bash "%USERPROFILE%\.claude\skills\python-code-standards\assets\setup-standards.sh"
```

The script is `bash`; on Windows it needs Git Bash or WSL `bash` on `PATH`, and only the
`bash` block has been executed. `cd /d` is required in `cmd` because plain `cd` will not
change drives. Working on a clone of this repo, the path is `skill/assets/setup-standards.sh`.
Adopting the tooling in an existing repository with mixed line endings needs one more step
after the script, `git add --renormalize .`, so the new `.gitattributes` takes effect.

The repository copy is authoritative wherever both exist: it is the one CI runs.

## Verifying the skill itself

```bash
uv sync --all-groups
uv run pytest --cov=skill.tools --cov=evals.grade --cov-branch
uv run ruff check skill/tools skill/assets/conformance.py tests evals/grade.py
# evals/fixtures/ is deliberately non-conforming — it is a baseline input, not source
uv run python skill/tools/check_declarations.py skill/tools skill/assets/conformance.py tests evals/grade.py
uv run complexipy skill/tools tests evals/grade.py
uv run deptry .
```

```cmd
uv sync --all-groups
uv run pytest --cov=skill.tools --cov=evals.grade --cov-branch
uv run ruff check skill/tools skill/assets/conformance.py tests evals/grade.py
REM evals/fixtures/ is deliberately non-conforming - it is a baseline input, not source
uv run python skill\tools\check_declarations.py skill\tools skill\assets\conformance.py tests evals\grade.py
uv run complexipy skill\tools tests evals\grade.py
uv run deptry .
```

Mutation testing needs `os.fork`, so on Windows it runs in WSL: `wsl -e bash skill/tools/mutation.sh`
(see [docs/quality-gates.md](docs/quality-gates.md#mutation-testing)).

`conformance.py` is the drift check: it is the executable form of these standards, so when a
Ruff upgrade changes which rules fire, it fails here.

The `cmd` blocks have not been executed on Windows; they are transcriptions of the `bash`
blocks, which are the verified ones. `uv`, `ruff` and `python` all accept forward slashes on
Windows, so the only genuinely shell-specific commands are the symlink and file-copy steps.

## Running the evals

Set up a scratch repository the agents will work in, separate from this one:

```
..\eval\
├── fixtures\        copies of evals/fixtures/, the inputs agents edit
└── runs\
    └── eval-1\
        ├── with-skill\
        └── baseline\
```

In Claude Code, open this repository and say:

```
Follow the instructions in @evals/RUNBOOK.md
```

That runbook fixes the skill symlink, verifies the toolchain, sets up the scratch repository,
runs the evals, and grades them.

### Reading the result

A near-zero delta in declaration violations means the rule is not landing, and the fix is to
make it louder in `SKILL.md` — not to conclude the eval failed.

A low trigger rate on eval 6 means the `description` frontmatter needs work. That field is the
only thing loaded before a skill fires, so a strong body behind a weak description is worth
nothing.

A failure on report question 4 is the most serious. Verification honesty is the one rule that
asks an agent to say something against its own apparent interest, and it is the hardest to
enforce mechanically.

The runbook runs the two arms as **separate passes**, with the skill physically moved out of
the skills directory for the baseline pass. A subagent merely told not to use skills can still
load one, and the cached skill listing keeps advertising the description even after the body
becomes unreachable — so isolation has to be a filesystem fact, not an instruction. Each pass
runs in its own fresh session.

Then grade from this repository:

```bash
uv sync --all-groups
uv run python evals/grade.py <runs>/with-skill <runs>/baseline --json scores.json
```

```cmd
uv sync --all-groups
uv run python evals\grade.py <runs>\with-skill <runs>\baseline --json scores.json
```

The delta between the two columns is the measurement; a single run's absolute numbers mean
little.
