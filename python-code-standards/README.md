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
evals/                  prompts + mechanical grader (development only)
pyproject.toml          tooling for this repo, and the baseline the skill teaches
```

Only `skill/` is installed. `tests/` and `evals/` stay here — they verify the
skill rather than being part of it.

## Install

Personal, all projects:

```bash
ln -s "$PWD/skill" ~/.claude/skills/python-code-standards
```

Per project, shared with anyone who clones that repository:

```bash
cp -r skill <target-repo>/.claude/skills/python-code-standards
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

The repository copy is authoritative wherever both exist: it is the one CI runs.

## Verifying the skill itself

```bash
uv sync --all-groups
uv run pytest --cov=tools.check_declarations --cov-branch
uv run ruff check skill/tools tests evals
uv run python skill/tools/check_declarations.py skill/tools tests evals/grade.py
# evals/fixtures/ is deliberately non-conforming — it is the baseline input
uv run python skill/tools/check_declarations.py skill/assets/conformance.py
```

The last line is the drift check: `conformance.py` is the executable form of
these standards, so when a Ruff upgrade changes which rules fire, it fails here.
