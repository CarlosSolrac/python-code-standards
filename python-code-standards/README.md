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
  references/           typing, testing, SQL/DuckDB, Pydantic, concurrency, packaging
  assets/               templates copied into the repositories you work in
  tools/                bundled checker, invoked via ${CLAUDE_SKILL_DIR}
tests/                  tests for the checker and grader  (development only)
evals/                  prompts, grader, runbook, pinned eval subagent (development only)
pyproject.toml          tooling for this repo, and the baseline the skill teaches
```

Only `skill/` is installed. `tests/` and `evals/` stay here — they verify the skill rather
than being part of it.

## Adopting the standards in a repository

`skill/tools/check_declarations.py` is bundled so the rule is enforceable in any repository,
including one with no setup. But CI and pre-commit run inside the target repository and cannot
see the skill directory, so any repository that adopts the tooling vendors its own copy:

```bash
mkdir -p <target-repo>/tools
cp skill/tools/check_declarations.py <target-repo>/tools/
cp skill/assets/pyproject-baseline.toml <target-repo>/pyproject.toml
cp skill/assets/pre-commit-config.yaml <target-repo>/.pre-commit-config.yaml
mkdir -p <target-repo>/.github/workflows
cp skill/assets/ci.yml <target-repo>/.github/workflows/verify.yml
cd <target-repo>
uv lock                              # ci.yml installs with --locked
uv sync --all-groups                 # the baseline dev group includes pre-commit
uv run pre-commit install
```

```cmd
mkdir "<target-repo>\tools"
copy skill\tools\check_declarations.py "<target-repo>\tools\"
copy skill\assets\pyproject-baseline.toml "<target-repo>\pyproject.toml"
copy skill\assets\pre-commit-config.yaml "<target-repo>\.pre-commit-config.yaml"
mkdir "<target-repo>\.github\workflows"
copy skill\assets\ci.yml "<target-repo>\.github\workflows\verify.yml"
cd /d "<target-repo>"
uv lock
uv sync --all-groups
uv run pre-commit install
```

`cd /d` is required: plain `cd` will not change drives, so `cd E:\repo` from a `C:` prompt
silently does nothing and `uv lock` runs in the wrong directory.

The repository copy is authoritative wherever both exist: it is the one CI runs.

## Verifying the skill itself

```bash
uv sync --all-groups
uv run pytest --cov=skill.tools.check_declarations --cov=evals.grade --cov-branch
uv run ruff check skill/tools skill/assets/conformance.py tests evals/grade.py
# evals/fixtures/ is deliberately non-conforming — it is a baseline input, not source
uv run python skill/tools/check_declarations.py skill/tools skill/assets/conformance.py tests evals/grade.py
```

```cmd
uv sync --all-groups
uv run pytest --cov=skill.tools.check_declarations --cov=evals.grade --cov-branch
uv run ruff check skill/tools skill/assets/conformance.py tests evals/grade.py
REM evals/fixtures/ is deliberately non-conforming - it is a baseline input, not source
uv run python skill\tools\check_declarations.py skill\tools skill\assets\conformance.py tests evals\grade.py
```

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
