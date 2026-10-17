# Plan: upgrade all packages

A plan, not the upgrade: nothing here has been changed yet. It lists every place this repository declares a version, the newest
release of each that is at least two weeks old, what breaks between the current and target versions, and the order to do it in,
each step with a check.

- **Snapshot:** 2026-10-16. **Cutoff:** 2026-10-02 — a release counts only if it was published on or before that day. Executing
  later? Move the cutoff to "today minus 14 days" and re-read the dates (commands under [Re-reading the dates](#re-reading-the-dates)).
- **Sources:** release dates from the PyPI JSON API (earliest non-yanked file of each release, pre-releases skipped), `npm view
  <pkg> time`, GitHub releases (`gh release list`), tags via `git ls-remote`, and python.org's release API. Breaking-change notes are
  from each project's release notes, or its changelog where that says more, for every major or minor release between the current
  and target versions.
- **Pinning rules already in the repository, kept here:** Ruff is held below its next minor (`<0.17`, "minor releases change which
  rules fire"); pytest's floor `>=9.0.3` stays ("9.0.3 fixes PYSEC-2026-1845"); the Mermaid checker pins exact versions so no project
  gains npm files; the template's `uv sync --locked` in CI means every lock change must still pass `uv lock --check`.

## Where versions are declared

| File | Declares | Kept in step with |
|---|---|---|
| `python-code-standards/pyproject.toml` | `[dependency-groups] dev` (12 tools) | the template below, by hand (no test ties them) |
| `python-code-standards/uv.lock` | locked versions, 67 packages | `pyproject.toml` (`uv lock --check`) |
| `python-code-standards/skill/assets/pyproject-baseline.toml` | the same dev group minus `duckdb` | the `TOML` heredoc in `setup-standards.sh` (byte-identical, tested) |
| `python-code-standards/skill/assets/pre-commit-config.yaml` | hook revs: `ruff-pre-commit`, `gitleaks` | the `YAML` heredoc (tested); the Ruff rev must equal the locked Ruff |
| `python-code-standards/skill/assets/ci.yml` | `actions/checkout@v4`, `astral-sh/setup-uv@v5` | the `CI` heredoc (tested) |
| `python-code-standards/skill/assets/mutation.yml` | `actions/checkout@v4`, `astral-sh/setup-uv@v5`, `actions/upload-artifact@v4` | the `MUTCI` heredoc (tested) |
| `python-code-standards/skill/assets/setup-standards.sh` | the embedded copies above; `uv python pin 3.13`; `--python 3.13` | `template_history.py` digests in its `HASHEOF` heredoc (tested) |
| `python-code-standards/.python-version` | `3.13` | `requires-python`, Ruff `target-version`, Pyright `pythonVersion`, MyPy `python_version` |
| `nightshift/evals/fixtures/base/` | `pyproject.toml` (same dev group, no comments), `uv.lock` (66 packages), `.python-version`, `.pre-commit-config.yaml`, `.github/workflows/{ci,mutation}.yml` | the skill assets, by hand: the workflows and pre-commit file are byte-identical to the assets today; no test enforces it |
| `design-spec/skill/tools/validate_mermaid.mjs` | `PINS`: `mermaid` 11.17.2, `jsdom` 30.1.1 | `docs/plans/design-spec.md` (names both versions) |

Not declared anywhere: **uv** (no `required-version`; `setup-uv` installs the latest; local 0.11.29) and **Node** (the Mermaid checker
needs 22.22.2+ or 24.15+; local v24.19.0).

## Decisions for you before starting

1. **Mermaid 11 → 12.** Planned: **12.1.0** (step 3). The checker only parses. Its tests parse a flowchart, a state and a C4 diagram
   (asserting the printed type for the first two) and reject a broken flowchart, so a parse-level change to those shows up there;
   other diagram types are not covered, and step 3 adds a run over real diagrams for that reason. The exception you may prefer: stay on 11.17.2 (the newest 11.x) and skip step 3, because a
   checker on 12 passes diagram types and syntax new in 12 that a renderer still on 11 cannot draw.
2. **How to pin GitHub Actions.** `setup-uv` stopped publishing major tags at v8, so `@v10` does not exist and an exact pin is needed
   anyway. Recommend **full commit SHAs with the version as a comment** (`uses: actions/checkout@3d3c42e5… # v7.0.1`), as `setup-uv`'s
   own v8 notes advise; exact tags (`@v7.0.1`) are the readable alternative. A floating major tag also breaks the two-week rule:
   `actions/upload-artifact@v7` already points at v7.0.2, published 2026-10-07.
3. **The eval fixture's lock.** It was locked on 2026-10-12 (`d052384`) and holds seven transitive versions newer than the cutoff.
   Recommend **leave it as is**: its constraints do not change, `uv lock --check` passes on it, and applying the cutoff would only
   downgrade those seven (see the [appendix](#appendix-transitive-packages-the-refresh-moves)).
4. **Python.** Recommend **no change**: 3.13 is the standards' floor ("Python 3.13+"), so raising it is a standards decision, not an
   upgrade. The `3.13` pin already picks up the newest 3.13 patch that the uv in use knows about.

## Inventory

### Python development tools

Constraints are identical in `pyproject.toml`, the baseline template and the fixture, except `duckdb`, which only this repository
declares (it lets Pyright type-check `conformance.py`).

| Package | Constraint | Locked (repo / fixture) | Newest release | Newest ≥ 2 weeks old | Target |
|---|---|---|---|---|---|
| complexipy | `>=8,<9` | 8.0.1 / 8.0.1 | 8.0.1 (2026-09-07) | 8.0.1 | no change |
| deptry | `>=0.25,<0.26` | 0.25.1 / 0.25.1 | 0.25.1 (2026-03-18) | 0.25.1 | no change |
| diff-cover | `>=10,<11` | 10.6.0 / 10.6.0 | 10.6.0 (2026-09-22) | 10.6.0 | no change |
| duckdb | `>=1.5,<2` | 1.5.6 / — | 1.5.6 (2026-09-28) | 1.5.6 | no change |
| mutmut | `>=3.8,<4; sys_platform != 'win32'` | 3.8.0 / 3.8.0 | 3.8.0 (2026-09-12) | 3.8.0 | no change |
| mypy | `>=2.4,<3` | 2.4.0 / 2.4.0 | 2.4.0 (2026-10-01) | 2.4.0 | no change |
| pip-audit | `>=2.10,<3` | 2.10.1 / 2.10.1 | 2.10.1 (2026-06-10) | 2.10.1 | no change |
| pre-commit | `>=4,<5` | 4.6.2 / 4.6.2 | 4.7.0 (2026-10-12) | 4.6.2 (2026-08-10) | no change; 4.7.0 eligible from 2026-10-26 |
| pyright | `>=1.1.400,<2` | **1.1.411** / 1.1.414 | 1.1.414 (2026-09-10) | 1.1.414 | **1.1.414** in the repo lock |
| pytest | `>=9.0.3,<10` | 9.1.1 / 9.1.1 | 9.1.1 (2026-06-19) | 9.1.1 | no change |
| pytest-cov | `>=6,<8` | 7.1.0 / 7.1.0 | 7.1.0 (2026-03-21) | 7.1.0 | no change |
| ruff | `>=0.16.10,<0.17` | 0.16.10 / 0.16.10 | 0.17.1 (2026-10-15) | 0.16.10 (2026-10-01) | no change; 0.17.0 eligible from 2026-10-23 |

Every target fits inside the current constraints, so no `pyproject.toml` or template line has to change for the Python tools; only the
repository's lock moves. `uv run pip-audit` on the current lock: "No known vulnerabilities found" (run 2026-10-16).

Breaking-change notes:

- **pyright 1.1.411 → 1.1.414.** The 1.1.412–1.1.414 release notes list no breaking changes, but several checks became stricter or
  more precise and can add diagnostics under `strict`: PEP 800 disjoint-base semantics, completed `TypeForm` support, narrowing of
  closed `TypedDict`s on `in`, `IntEnum`/`StrEnum` equality narrowing, TypeGuard/TypeIs narrowing for union returns, "do not inherit
  dataclass defaults when a subclass uses `field()` without one", and a specific diagnostic for a walrus in a comprehension iterable.
  The PyPI wrapper's dates differ from GitHub's (GitHub published 1.1.412 on 2026-08-12, PyPI on 2026-09-09); the table uses PyPI's,
  since that is what uv installs.
- **ruff 0.17.0** (not eligible yet; for the follow-up). Its breaking changes that reach this configuration: `TID254` and `TID255`
  (lazy imports) and `RUF071` (`os.path.commonprefix`) are stabilized, and `TID` and `RUF` are selected, so they start firing; the
  formatter, `I001` and `E501` now ignore trailing pragma comments when measuring line length, which "may cause existing imports to be
  reformatted". The default rule set and default Python version also changed, but the explicit `select` list and `target-version =
  "py313"` make those moot here.
- **pre-commit 4.7.0** (not eligible yet): within `<5`, so a lock refresh alone picks it up once eligible.

### Pre-commit hook revs

| Hook | Current rev | Newest | Newest ≥ 2 weeks old | Target |
|---|---|---|---|---|
| `astral-sh/ruff-pre-commit` | `v0.16.10` | v0.17.1 (2026-10-15) | v0.16.10 (2026-10-01) | no change; moves with Ruff (follow-up) |
| `gitleaks/gitleaks` | `v8.30.1` | v8.30.1 (2026-03-21) | v8.30.1 | no change |

### GitHub Actions in the workflow templates

The templates use floating major tags; each row gives what the tag resolves to today.

| Action | Current | Newest | Newest ≥ 2 weeks old | Target |
|---|---|---|---|---|
| `actions/checkout` | `@v4` → v4.4.0 (2026-07-20) | v7.0.1 (2026-07-20) | v7.0.1 | **v7.0.1** (`3d3c42e5aac5ba805825da76410c181273ba90b1`) |
| `astral-sh/setup-uv` | `@v5` → v5.4.2 (2025-04-16) | v10.3.0 (2026-10-09) | v10.2.0 (2026-09-21) | **v10.2.0** (`c18668ad3cf93ea998bef934396af7bb5c839dc7`) |
| `actions/upload-artifact` | `@v4` → v4.6.2 (2025-03-19) | v7.0.2 (2026-10-07) | v7.0.1 (2026-04-10) | **v7.0.1** (`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`) |

Breaking-change notes, and whether they touch the templates:

- **checkout v5:** runs on Node 24 and needs Actions runner 2.327.1 or newer (GitHub-hosted runners qualify). **v6:** persists the
  credentials to a separate file. **v7:** ESM build; refuses to check out a fork's PR under `pull_request_target` and `workflow_run`
  unless allowed. The templates trigger on `push`, `pull_request`, `schedule` and `workflow_dispatch` only, and `ci.yml`'s
  `fetch-depth: 0` (needed by `diff-cover`) is unchanged, so none of this needs a template edit. v4.4.0 already carries the same
  `pull_request_target` change as a backport.
- **setup-uv v6:** environment activation becomes an explicit input (`activate-environment`, default false); new `working-directory`
  input; `pyproject-file` and `uv-file` inputs removed; the default `cache-dependency-glob` now also covers `pyproject.toml`. **v7:**
  Node 24; `server-url` removed. **v8:** no more major or minor tags — pin an exact tag or SHA; old `manifest-file` format removed.
  **v9:** `prune-cache` defaults to false (larger caches). **v10:** the default `enable-cache: auto` turns caching off for
  `pull_request_target`, `workflow_run` and `release`. The templates pass only `enable-cache: true` and run every tool through
  `uv run`, so the one required edit is the exact pin.
- **upload-artifact v5/v6:** Node 24, runner 2.327.1 or newer. **v7:** ESM; new `archive` input (default true, so the zipped
  `mutation-report` artifact of two files is unchanged).

### npm packages pinned by the Mermaid checker

| Package | Pin | Newest | Newest ≥ 2 weeks old | Target |
|---|---|---|---|---|
| mermaid | 11.17.2 (2026-08-25) | 12.2.0 (2026-10-13) | 12.1.0 (2026-10-02) | **12.1.0** (decision 1; exception: stay on 11.17.2, the newest 11.x) |
| jsdom | 30.1.1 (2026-09-22) | 30.1.3 (2026-10-15) | 30.1.1 | no change; 30.1.2 eligible from 2026-10-18 |

Breaking-change notes. **mermaid 12.1.0** (minor changes only): a new `elk.orientFeedbackEdges` option, on by default, re-routes
edges that feed back into a subgraph in ELK layouts — rendering only; set it to `false` to keep the old routing — and a `bitOrder`
option for packet diagrams whose default keeps today's behaviour. **mermaid 12.0.0**: requires ES2024 and Node 22.12+ (the checker already
needs 22.22.2+); ELK is bundled and becomes the default layout for flowchart, state, class, ER and requirement diagrams, and a new
default look recolours them — both affect rendering, not parsing; the `defaultRenderer` option is removed (ignored, not rejected); the
legacy `flowchart`, `class` and `state` diagram ids are gone, but with the default configuration the checker uses they were already
unreachable, so the ids it prints (`flowchart-v2`, `stateDiagram`, `classDiagram`) should not change — the checker's tests assert
`flowchart-v2` and `stateDiagram` and would catch a change to those two (`classDiagram` is not tested); internal layout exports are removed (the checker does not use them). jsdom 30.1.1's `engines`
(`^22.22.2 || ^24.15.0 || >=26.0.0`) matches the checker's Node message. Changing a pin makes the checker run `npm install` into each
user's cache (`~/.cache/design-spec-mermaid`) on its next run, so the first run needs the network.

### Runtimes

| Runtime | Declared | Newest | Newest ≥ 2 weeks old | Target |
|---|---|---|---|---|
| Python | `3.13` (`.python-version` ×2), `>=3.13`, `py313`, `3.13` in Pyright and MyPy, `uv python pin 3.13` in the setup script | 3.15.0 (2026-10-09) | 3.14.8 (2026-09-30); 3.13 line: 3.13.16 (2026-09-30) | no file change (decision 4); locally, `uv python upgrade 3.13` reaches 3.13.16 only with a uv that knows it — uv 0.11.29 offers 3.13.14 at most |
| uv | not declared | 0.13.1 (2026-10-14) | 0.12.22 (2026-10-02) | out of scope: `setup-uv` installs the newest uv on every CI run, so CI already runs one younger than two weeks; pinning it (`version:` input or `required-version`) would add a declaration, not upgrade one |
| Node | not declared (checker needs 22.22.2+ or 24.15+) | — | — | out of scope |

## Appendix: transitive packages the refresh moves

Not declared, so no constraint changes; listed so the lock diff holds no surprises. Measured with a dry run on a scratch copy of each
project (outside the repository) on 2026-10-16.

**`python-code-standards/uv.lock`** with step 1's command: coverage 7.16.0 → 7.16.2 (bug fixes for branch coverage on Python 3.14+),
filelock 3.32.5 → 4.0.9 (a major version, needs Python 3.11+; pulled in by virtualenv, python-discovery and cachecontrol). Per its
changelog, 4.0.0 changes the on-disk protocol of `SoftReadWriteLock` — an old and a new participant on one lock path do not exclude
each other, so every participant must be stopped, upgraded and restarted together — and makes re-creating a singleton
`SoftReadWriteLock` with different `on_compromise` or `poll_interval` settings raise `ValueError`; 4.0.1 and 4.0.7 make `FileLock`
reject an invalid `poll_interval`, or a `mode` that denies the owner read or write, at construction instead of on a later acquire;
4.0.9 fixes GHSA-j8f7-rjxc-mr56 (`ReadWriteLock` followed a symlink at its database path). The read-write-lock changes do not reach
this lock: virtualenv 21.14.5, python-discovery 1.6.0 and 1.6.1, and cachecontrol 0.14.4 import only `FileLock` and `BaseFileLock`
(their sources searched on 2026-10-16); the gates' `uv run pip-audit` exercises `FileLock` through its cachecontrol file cache. Then
identify 2.6.19 → 2.6.20, nodeenv 1.10.0 → 1.11.0 (new options only), platformdirs
4.11.7 → 4.12.2, python-discovery 1.6.0 → 1.6.1, and pyright as above. A blanket `uv lock --upgrade --exclude-newer` would also
*downgrade* ast-serialize 0.12.1 → 0.12.0, because 0.12.1 was published on 2026-10-03, after the cutoff; step 1's targeted command
leaves it alone.

**`nightshift/evals/fixtures/base/uv.lock`** under the same cutoff would only move backwards: ast-serialize 0.12.1 → 0.12.0, filelock
4.1.1 → 4.0.9, iniconfig 2.3.1 → 2.3.0, platformdirs 4.13.0 → 4.12.2, python-discovery 1.6.2 → 1.6.1, tomli 2.5.0 → 2.4.1,
virtualenv 21.14.7 → 21.14.5. Hence decision 3.

## Upgrade steps

One commit per step on a branch off `main`, so any step can be reverted alone. Commands run from `python-code-standards/` unless a step
says otherwise. **The gates** are the README's checks plus formatting, both type checkers and the audit; all passed on `main` on
2026-10-16:

```bash
uv sync --locked --all-groups
uv run pytest --cov=skill.tools --cov=evals.grade --cov-branch
uv run ruff check skill/tools skill/assets/conformance.py tests evals/grade.py
uv run ruff format --check skill/tools skill/assets/conformance.py tests evals/grade.py
uv run python skill/tools/check_declarations.py skill/tools skill/assets/conformance.py tests evals/grade.py
uv run pyright skill/tools skill/assets/conformance.py tests evals/grade.py
uv run mypy skill/tools skill/assets/conformance.py tests evals/grade.py
uv run complexipy skill/tools tests evals/grade.py
uv run deptry .
uv run pip-audit
```

The order goes from smallest blast radius to largest: a lock-only change first, then template files that need the drift procedure,
then the separate Node tool, and Ruff last, because it changes which rules fire and three declarations must move with it.

### Step 0 — baseline

Run the gates, and from the repository root the Mermaid checker's tests:

```bash
node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"
```

**Check:** everything passes. Record any failure as pre-existing before changing anything.

### Step 1 — refresh the repository's lock

No constraint changes; only `uv.lock` moves.

```bash
uv lock -P pyright==1.1.414 -P coverage==7.16.2 -P filelock==4.0.9 -P identify==2.6.20 \
        -P nodeenv==1.11.0 -P platformdirs==4.12.2 -P python-discovery==1.6.1
```

Why named targets rather than `uv lock --upgrade --exclude-newer <cutoff>`: that flag is written into `uv.lock` under `[options]`,
and afterwards `uv lock --check` — and so CI's `uv sync --locked` — fails until `uv lock` is run again without it; it would also
downgrade ast-serialize. Both were confirmed in the dry run. Use the flag with `--dry-run` to discover targets instead (see
[Re-reading the dates](#re-reading-the-dates)).

**Check:** `uv lock --check` exits 0; `git diff --stat` lists only `uv.lock`; `git diff uv.lock | grep -E '^[-+]version'` shows seven
version changes (14 lines), one per package above; the gates pass. Run Pyright first, as the only direct tool that moves: a new diagnostic is fixed in the code,
in its own commit, never suppressed.

### Step 2 — GitHub Actions in the workflow templates

1. In `skill/assets/ci.yml` and `skill/assets/mutation.yml`, replace `actions/checkout@v4`, `astral-sh/setup-uv@v5` and
   `actions/upload-artifact@v4` with the targets, in the form decision 2 picks.
2. Copy each file, byte for byte, into its heredoc in `skill/assets/setup-standards.sh`: `CI` for `ci.yml`, `MUTCI` for `mutation.yml`.
3. `uv run python -m skill.tools.template_history` — adds the new files' digests to the script's `HASHEOF` heredoc, so the script
   recognises the files it now writes, and a project still holding an unedited old version sees it as *outdated* and gets it replaced
   by `setup-standards.sh -y --update`.
4. Copy both workflows to `nightshift/evals/fixtures/base/.github/workflows/`.

**Check:**

```bash
uv run pytest tests/test_setup_script.py -q    # heredocs byte-identical to the assets; digest history covers them
diff skill/assets/ci.yml ../nightshift/evals/fixtures/base/.github/workflows/ci.yml
diff skill/assets/mutation.yml ../nightshift/evals/fixtures/base/.github/workflows/mutation.yml
git grep -nE 'uses: [^ ]+@v[0-9]+$' -- skill/assets ../nightshift/evals/fixtures/base    # no floating major tag left: prints nothing
```

then the gates. The workflows run only in a project the script sets up — this repository has no CI of its own — so for an end-to-end
check, run `setup-standards.sh -y` in a scratch repository, push it to a throwaway GitHub repository, and watch `verify` pass on a pull
request and `mutation` pass from `workflow_dispatch`.

### Step 3 — Mermaid 12.1.0 (skip if you take decision 1's exception)

1. In `design-spec/skill/tools/validate_mermaid.mjs`, set `PINS` to `{ mermaid: "12.1.0", jsdom: "30.1.1" }`.
2. In `docs/plans/design-spec.md`, change the sentence naming the pinned versions.

**Check**, from the repository root, against a scratch cache so the shared one is not replaced until the change is kept:

```bash
export DESIGN_SPEC_MERMAID_CACHE="$(mktemp -d)"
node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"
node design-spec/skill/tools/validate_mermaid.mjs design-spec/skill/SKILL.md
```

The tests pass at 100% line and branch coverage (they parse flowchart, state and C4 diagrams), and the last command prints
`OK flowchart-v2` for block 1, as it does on 11.17.2 today. The first run downloads the new pins.

### Step 4 — Ruff 0.17 (from 2026-10-23)

The pin comment's reason applies in full, so this is its own step, done last. Let N be the newest 0.17 patch at least two weeks old.

1. `ruff>=0.17.N,<0.18` in `pyproject.toml`, `skill/assets/pyproject-baseline.toml`, the `TOML` heredoc, and
   `nightshift/evals/fixtures/base/pyproject.toml`.
2. `rev: v0.17.N` in `skill/assets/pre-commit-config.yaml`, the `YAML` heredoc, and `nightshift/evals/fixtures/base/.pre-commit-config.yaml`.
3. `uv lock -P ruff==0.17.N` here, and the same from `nightshift/evals/fixtures/base/`.
4. `uv run python -m skill.tools.template_history`. The pre-commit file needs a new digest; the `pyproject.toml` change does not, since
   the history digests only its `[tool.*]` tables and this change is in `[dependency-groups]`.

**Check:** `uv run ruff check` and `uv run ruff format --check` on the gate paths — `conformance.py` is the drift check, so a new
finding there means the standards' example changes or the rule is deselected, which is a standards decision, not a fix to slip in;
`uv run pytest tests/test_setup_script.py -q`; `uv lock --check` in both projects; `git grep -n 'v0.16' -- skill/assets
../nightshift/evals/fixtures/base` prints nothing; then the gates. None of those runs the hook itself, and this repository has no
pre-commit config of its own, so also run the template's CI hook step in a project built from the fixture, which carries the new rev
— once before the edits and once after, so a failure after is the upgrade's (from the repository root; pre-commit installs the hook
environments on first run):

```bash
dest="$(mktemp -d)/statskit"
nightshift/evals/build-fixture.sh thorough-median "$dest"
(cd "$dest" && uv sync --locked --all-groups && uv run pre-commit run --all-files --show-diff-on-failure)
```

Projects set up earlier: `setup-standards.sh -y --update` replaces an unedited `.pre-commit-config.yaml`, but never changes a dev tool
the project already names ("A tool the project already names keeps its version"), so their `uv run ruff` stays on 0.16 while the hook
runs 0.17 until they run `uv add --dev "ruff>=0.17.N,<0.18"`. Say so wherever the skill's change is announced.

Projects set up afterwards: the setup script syncs without a lock, so a new project gets the newest 0.17 patch, which can be newer than
the hook's `rev: v0.17.N` and younger than two weeks. That is the template's existing design — the pin comment holds back minor
releases, not patches, and 0.16 behaves the same way today — so the range stays; pinning `ruff==0.17.N` instead would be a standards
change.

### Step 5 — what becomes eligible next

Each date is the release date plus 14 days. Re-run the discovery commands below before acting on any of them.

| Release | Published | Eligible from | Lands in |
|---|---|---|---|
| ast-serialize 0.12.1 (already locked) | 2026-10-03 | 2026-10-17 | — |
| jsdom 30.1.2 | 2026-10-04 | 2026-10-18 | `PINS` |
| actions/upload-artifact v7.0.2 | 2026-10-07 | 2026-10-21 | step 2's files |
| ruff 0.17.0, ruff-pre-commit v0.17.0 | 2026-10-09 | 2026-10-23 | step 4 |
| astral-sh/setup-uv v10.3.0 | 2026-10-09 | 2026-10-23 | step 2's files |
| Python 3.15.0 | 2026-10-09 | 2026-10-23 | decision 4 |
| pre-commit 4.7.0 | 2026-10-12 | 2026-10-26 | a lock refresh (`-P pre-commit==4.7.0`) |
| mermaid 12.2.0 | 2026-10-13 | 2026-10-27 | `PINS` (decision 1) |
| ruff 0.17.1 | 2026-10-15 | 2026-10-29 | step 4 |
| pluggy 1.7.0 (pytest) | 2026-10-15 | 2026-10-29 | a lock refresh |

## Re-reading the dates

To list what is eligible on the day you execute, without writing anything. The cutoff is the end of the day 14 days ago, in UTC
(`date -d` is GNU; on macOS use `date -v-13d`).

```bash
# 1. Locked packages, within the current constraints (run in each project):
uv lock --upgrade --dry-run --exclude-newer "$(date -u -d '13 days ago' +%Y-%m-%d)T00:00:00Z"

# 2. The newest eligible release of each direct tool, ignoring its constraint (finds a new Ruff minor, which step 1 cannot):
uv run --no-project --with packaging python - <<'PY'
import datetime as dt, json, urllib.request
from packaging.version import InvalidVersion, Version
cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=14)).date().isoformat()
def final(version):  # a release, post-release included; None for a pre-release, dev release or unparsable version
    try:
        parsed = Version(version)
    except InvalidVersion:
        return None
    return None if parsed.is_prerelease else parsed
for name in ["complexipy", "deptry", "diff-cover", "duckdb", "mutmut", "mypy", "pip-audit", "pre-commit", "pyright", "pytest", "pytest-cov", "ruff"]:
    releases = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json"))["releases"]
    ok = [(final(v), v) for v, files in releases.items()
          if final(v) and any(not f["yanked"] for f in files)
          and min(f["upload_time"] for f in files if not f["yanked"])[:10] <= cutoff]
    print(name, max(ok)[1])
PY

# 3. npm pins: every version with its publish time.
npm view mermaid time --json
npm view jsdom time --json

# 4. Actions and hooks: the highest version published on or before the cutoff. Sorted by version, not date, because
#    checkout publishes backports to old majors on the same day as new releases.
cutoff="$(date -u -d '14 days ago' +%Y-%m-%d)"
for repo in actions/checkout astral-sh/setup-uv actions/upload-artifact astral-sh/ruff-pre-commit gitleaks/gitleaks; do
    printf '%s ' "$repo"; gh release list -R "$repo" --limit 200 --exclude-pre-releases --json tagName,publishedAt \
        --jq ".[] | select(.publishedAt[:10] <= \"$cutoff\") | .tagName" | sort -V | tail -1
done
# The commit a chosen tag points at, for a SHA pin (resolves annotated tags too, which `git ls-remote` would not):
gh api repos/actions/checkout/commits/v7.0.1 --jq .sha
```

Command 1 prints `Update <package> vX -> vY` for each move; a move to a *lower* version means the locked version is younger than the
cutoff, and the targeted `-P` form of step 1 keeps it. On 2026-10-16, command 2 printed exactly the "Newest ≥ 2 weeks old"
column of the Python tools table, and command 4 the targets of the Actions and hook tables.
