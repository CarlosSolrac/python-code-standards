# Plan: add the `design-spec` skill

Source material: [handoff/design-spec/HANDOFF.md](https://github.com/CarlosSolrac/python-code-standards/blob/eb189bb/handoff/design-spec/HANDOFF.md)
(context, conflicts, original tasks) and
[handoff/design-spec/SKILL.draft.md](https://github.com/CarlosSolrac/python-code-standards/blob/eb189bb/handoff/design-spec/SKILL.draft.md)
(the skill as drafted), removed from the tree once the skill landed and linked here at the last commit that has them. Where this plan and the handoff
differ, this plan wins: it records the user's decisions of 2026-10-15 and 2026-10-16.

## Decisions already made by the user

Do not reopen these; log a decision only for choices this plan leaves open.

- **Conflicts 1–3** (handoff §5): resolved as the handoff recommends.
- **Conflict 4**: `CsvSource` checks `table_name` against an allowlist read from `external_models.yaml`. That code lives in the template
  repository (below), not here; the skill's rule 8 only states the requirement.
- **Conflict 5 and the reference skeleton**: the skeleton does not live in this repository. It goes in the public template repository
  [CarlosSolrac/template-sqlmesh-duckdb](https://github.com/CarlosSolrac/template-sqlmesh-duckdb) (created, still empty), filled by a
  separate session. Templates are indexed in [CarlosSolrac/template-0-summaries](https://github.com/CarlosSolrac/template-0-summaries).
  The skill links to the index, not to one template, and to `main`, not a tag. The template's own `docs/design.md` is the worked example
  and its `docs/adr/` holds ADR-0001 and ADR-0002, so the skill keeps no copy of either.
- **Mermaid checker**: done before this plan. [design-spec/skill/tools/validate_mermaid.mjs](../../design-spec/skill/tools/validate_mermaid.mjs)
  checks ```` ```mermaid ```` blocks in Markdown and whole `.mmd`/`.mermaid` files. Its pinned packages (`mermaid` 11.17.2, `jsdom` 30.1.1)
  are already installed in its cache, so running it installs nothing. It needs Node 22.22.2+ or 24.15+ (jsdom's minimum). Run it as
  `node design-spec/skill/tools/validate_mermaid.mjs <file>...` (exit 0 = every diagram parses). Its tests:
  `node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"`.
- **Evals**: all five, listed under task 3.
- **Not tonight** (each needs the user, a hook, or a change outside the repository): the `hooks:` entry in the skill's frontmatter, the
  install link in `~/.claude/skills`, the live hook test, deleting `handoff/`, filing the frontmatter bug report, and filling the template
  repository. They are listed under *Morning steps* for the user. Do not attempt them.

## Tasks

| # | Task | Depends on | Done-check |
|---|---|---|---|
| 1 | Global rules: conflicts 1 and 2 | — | `git diff main` shows the three edits below and nothing else |
| 2 | Create `design-spec/skill/SKILL.md` | — | `SKILL.md` has at most ~250 lines; the checker exits 0 on it; a copy with one diagram deliberately broken makes it exit 1 |
| 3 | Evals and fixtures | 2 | `design-spec/evals/evals.json` parses and every eval has `prompt`, `expected_output`, `assertions`; `build-fixture.sh` builds fixtures for evals 1, 2, 3 and 3b into empty folders; eval 3's fixture is at commit `8ffaa6f` |
| 4 | README update | 2 | Every relative link in `README.md` resolves to an existing file; the install, verify and uninstall blocks cover both new skills in bash, PowerShell and cmd |

### 1. Global rules

- [CLAUDE.md](../../CLAUDE.md), *Before writing code*: reword "Design top-down: the entry point first, then each helper it calls, one
  level at a time." so top-down is the order for implementing a unit, and architecture is designed from the domain outward per the
  `design-spec` skill.
- [python-code-standards/skill/SKILL.md](../../python-code-standards/skill/SKILL.md), *Design and testing*: the same change to the
  **Top-down design** bullet.
- `CLAUDE.md`: add one sentence next to the "More than two files... post a numbered plan" rule: a Standard or Large design produces a
  `design-spec` spec first, and the edit plan follows its approval.

`~/.claude/CLAUDE.md` links to this file, so the change reaches every session only once the PR merges.

### 2. `design-spec/skill/SKILL.md`

Mirror `python-code-standards/skill/`. Start from the draft's sections 1–7 and change:

- Frontmatter: keep `name` and `description`. Add no `hooks:` entry (a morning step). Claude Code ends frontmatter at the first `---`
  anywhere, even mid-line, so the frontmatter must not contain three dashes in a row.
- §7: replace the inlined script with a pointer to `tools/validate_mermaid.mjs` and its command line; keep the mermaid-cli option for
  rendering.
- §8 (worked example) and §10 (reference skeleton): remove. In their place, one short section: the default pattern for a Standard data
  pipeline comes from the templates indexed in `template-0-summaries`; each template's `docs/design.md` is its worked example; when the
  project already has a pattern, follow it and record the difference in an ADR.
- §9: replace with "Python code follows the `python-code-standards` skill." plus the two SQLMesh-specific lines (`uv run sqlmesh test` among
  the checks; the `PlanError` CLI tip).
- Rule 8: identifier-only DDL in adapters must check identifiers against an allowlist of declared tables (for SQLMesh projects, read from
  `external_models.yaml`), never interpolate unchecked names.

### 3. Evals and fixtures

Follow `nightshift/evals/`: `design-spec/evals/evals.json`, `RUNBOOK.md`, `build-fixture.sh`, fixtures under `design-spec/evals/fixtures/`.
Agent output never goes inside this repository.

1. **Design, Standard.** Fixture: an empty git repository. Prompt: "Pull orders from a CSV and a REST API into DuckDB, dedupe, and produce a
   daily revenue table." Assert: first line states design mode and Standard; numbers derived or unknowns listed as open questions, none
   invented; state diagram before the component flowchart; every component labelled with the decision it owns; contract table with every
   boundary; a C4 context view (CSV and API are two external systems); the default pattern found through `template-0-summaries`, or an ADR
   saying why not; every diagram passes the checker; ends with "Approve or correct before I implement." and writes no code.
2. **Small.** Fixture: an empty project set up with `python-code-standards`. Prompt: "Script to convert one CSV to Parquet." Assert: first
   line states Small; no `docs/design.md`, no spec, no SQLMesh; code written directly under the Python standards.
3. **Document, real repository.** Fixture: ParquetToXL at commit `8ffaa6f` (the base of its PR #7), stored as a git bundle
   `fixtures/parquettoxl-8ffaa6f.bundle` made from `https://github.com/CarlosSolrac/ParquetToXL` (`git bundle create` of a branch at
   `8ffaa6f`, about 3 MB). `build-fixture.sh` clones it. Answer key: `expected/eval-3/design.md` and `expected/eval-3/backlog2.md`, copied
   from the PR's merge commit `f8f4a41`. Assert: finds the `pqx-report` dependency defect with an `!`/`d` matrix; finds the `CLAUDE.md`
   layering drift; labels backlog item 9.1 as known; changes no code.
3b. **Document, planted defects.** A small uv-workspace fixture in this repository with exactly these defects, each listed in its answer
   key: a package importing another it does not declare (`!`); a package declaring a dependency it never imports (`d`); a layer that only
   forwards data (rule 2); a dict crossing a boundary (rule 4); a layering diagram in its `CLAUDE.md` that disagrees with the code
   (rule 14); one of these already in its backlog file, to be labelled known. The fixture's code is defective on purpose and is not held
   to this repository's checks. Assert: all six findings, labelled new or known correctly; inferred items marked; no code changed.
4. **Resync.** Fixture: a clone of `template-sqlmesh-duckdb` with one import reversed (`ports.py` importing from `adapters`). Prompt:
   "Resync the design." Assert: reports the import-direction change before overwriting `docs/design.md` (the template has fewer than five
   modules, so the spec has an import-direction line, not a matrix); adds a rule 6 finding; changes no code. The template is still empty,
   so this eval cannot run yet: `build-fixture.sh` must fail with a clear message while the template has no `docs/design.md`.

### 4. README

- A section on `design-spec`: what it does (the two modes, the size gate), that its diagram checker needs Node 22.22.2+ or 24.15+, and that templates
  are listed in `template-0-summaries`.
- A section on `nightshift` (linked into `~/.claude/skills` but not yet documented): it works through the project's TODO and plan files
  overnight, one draft PR per task, and only the user starts it with `/nightshift`.
- Rewrite "Each rule lives in exactly one of the two files" to cover every file the repository installs.
- Manual Install, Copy instead of link, Verify and Uninstall: add both skills in bash, PowerShell and cmd, in the same forms as the
  existing commands.

## Morning steps (for the user, not nightshift)

1. Merge the PRs: task 1 alone; task 2, then tasks 3 and 4, which stack on it.
2. Add the `hooks:` entry to the skill's frontmatter: `PostToolUse`, matcher `Write|Edit`, command
   `node "$HOME/.claude/skills/design-spec/tools/validate_mermaid.mjs" --hook`, `timeout: 180`. (`${CLAUDE_SKILL_DIR}` is not substituted in
   hook commands, verified on Claude Code 2.1.294.)
3. Link `~/.claude/skills/design-spec` to `design-spec/skill`, then run a headless session that invokes the skill and writes a Markdown
   file with a broken diagram; the hook must report it.
4. Delete `handoff/`; the repository is now the copy of record.
5. File the frontmatter bug report.
6. Start the session that fills `template-sqlmesh-duckdb`.
