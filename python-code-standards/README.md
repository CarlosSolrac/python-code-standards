# python-code-standards

Source repository for the `python-code-standards` skill.

## Layout

```
skill/                  <- this is the installed skill; symlink or copy it
  SKILL.md
  references/
  assets/               templates copied into the repositories you work in
  tools/                bundled checker, invoked via ${CLAUDE_SKILL_DIR}
tests/                  tests for the checker  (development only)
evals/                  prompts, grader, runbook, pinned eval subagent (development only)
pyproject.toml          tooling for this repo, and the baseline the skill teaches
```

Only `skill/` is installed. `tests/` and `evals/` stay here — they verify the
skill rather than being part of it.

## Install

Personal, all projects:

```bash
ln -s "$PWD/skill" ~/.claude/skills/python-code-standards
```

```cmd
mklink /D "%USERPROFILE%\.claude\skills\python-code-standards" "%CD%\skill"
```

Note that `mklink` takes the link first and the target second — the reverse of
`ln -s`. It needs Developer Mode enabled or an elevated prompt. Link the skill
*inside* `skills\`; linking `skills\` itself hides every other skill and stops
this one loading, because Claude Code scans subdirectories for `SKILL.md`.

Per project, shared with anyone who clones that repository:

```bash
cp -r skill <target-repo>/.claude/skills/python-code-standards
```

```cmd
xcopy /E /I skill "<target-repo>\.claude\skills\python-code-standards"
```

A symlink keeps one source of truth and picks up edits immediately; a copy is
pinned and survives this repository moving. Do not install both at once under
the same name — resolution order between personal and project scope is not
something to rely on.

## Adopting the standards in a repository

`skill/tools/check_declarations.py` is bundled so the rule is enforceable in any
repository, including one with no setup. But CI and pre-commit run inside the
target repository and cannot see the skill directory, so any repository that
adopts the tooling vendors its own copy:

```bash
mkdir -p <target-repo>/tools
cp skill/tools/check_declarations.py <target-repo>/tools/
cp skill/assets/pyproject-baseline.toml <target-repo>/pyproject.toml
cp skill/assets/pre-commit-config.yaml <target-repo>/.pre-commit-config.yaml
mkdir -p <target-repo>/.github/workflows
cp skill/assets/ci.yml <target-repo>/.github/workflows/verify.yml
cd <target-repo> && uv lock          # ci.yml installs with --locked
```

```cmd
mkdir "<target-repo>\tools"
copy skill\tools\check_declarations.py "<target-repo>\tools\"
copy skill\assets\pyproject-baseline.toml "<target-repo>\pyproject.toml"
copy skill\assets\pre-commit-config.yaml "<target-repo>\.pre-commit-config.yaml"
mkdir "<target-repo>\.github\workflows"
copy skill\assets\ci.yml "<target-repo>\.github\workflows\verify.yml"
REM ci.yml installs with --locked, so the lockfile must exist and be committed.
cd /d "<target-repo>"
uv lock
```

`cd /d` is required: plain `cd` will not change drives, so `cd E:\repo` from a
`C:` prompt silently does nothing and `uv lock` runs in the wrong directory.

The repository copy is authoritative wherever both exist: it is the one CI runs.

## Running the evals

Set up a scratch repository the agents will work in, separate from this one:

```
E:\_src\eval\
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

That runbook fixes the skill symlink, verifies the toolchain, sets up the scratch
repository, runs the evals, and grades them.

### Reading the result

A near-zero delta in declaration violations means the rule is not landing, and
the fix is to make it louder in `SKILL.md` — not to conclude the eval failed.

A low trigger rate on eval 6 means the `description` frontmatter needs work. That
field is the only thing loaded before a skill fires, so a strong body behind a
weak description is worth nothing.

A failure on report question 4 is the most serious. Verification honesty is the
one rule that asks an agent to say something against its own apparent interest,
and it is the hardest to enforce mechanically.

The runbook runs the two arms as **separate passes**, with the skill physically
moved out of the skills directory for the baseline pass. A subagent merely told
not to use skills can still load one, and the cached skill listing keeps
advertising the description even after the body becomes unreachable — so
isolation has to be a filesystem fact, not an instruction. Each pass runs in its
own fresh session.

Then grade from this repository:

```bash
uv sync --all-groups
uv run python evals/grade.py <runs>/with-skill <runs>/baseline --json scores.json
```

```cmd
uv sync --all-groups
uv run python evals\grade.py <runs>\with-skill <runs>\baseline --json scores.json
```

The delta between the two columns is the measurement; a single run's absolute
numbers mean little.

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

`conformance.py` is the drift check: it is the executable form of these
standards, so when a Ruff upgrade changes which rules fire, it fails here.

The `cmd` blocks have not been executed on Windows; they are transcriptions of
the `bash` blocks, which are the verified ones. `uv`, `ruff` and `python` all
accept forward slashes on Windows, so the only genuinely shell-specific commands
are the symlink and file-copy steps above.
