# Quality gates

Why each deterministic gate exists. This file is for people maintaining the standards; it is
never loaded into an agent's context. The gates explain themselves when they fire, so neither
`CLAUDE.md` nor `SKILL.md` restates them.

## The premise

An agent writes code faster than a person can review it. Prose rules in a skill shape
behaviour but cannot be relied on, whereas hooks, pre-commit, and CI give the same answer
every run. So every rule that can be written as a check is a check. Each check's message
names the rule, the file and line, and the fix (or "ask the user"), and that message is
its documentation.

## Evidence: what linters can and cannot tell you about AI-written code

Haindl & Weinberger, "Does ChatGPT Help Novice Programmers Write Better Code? Results From
Static Code Analysis", *IEEE Access* 12 (2024), [doi:10.1109/ACCESS.2024.3445432](https://doi.org/10.1109/ACCESS.2024.3445432).

The authors compared 38 novice Java students, 22 of them using ChatGPT and 16 not, using
Checkstyle conventions, cyclomatic complexity, and SonarQube cognitive complexity.

- The ChatGPT group had significantly fewer convention violations, mostly line length,
  `final` parameters, design-for-extension, and magic numbers.
- Its cyclomatic complexity was lower: a median of 5.91 vs 8.67 on the OOP exercise.
- Its cognitive complexity was statistically lower, but the effect was "rather negligible"
  (1.36 vs 2). Nesting depth showed no difference.
- Correctness was not measured, and the authors flag construct validity: static rules may not
  capture maintainability.

What follows for the gates:

- **A clean lint run on AI code carries little information.** LLM output is already tidy by
  the measures linters use. The gates that add signal check meaning: tests, coverage of
  changed lines, strict types, silent-failure rules and, later, mutation score.
- **Complexity is a cap, not a goal.** Use cyclomatic and cognitive complexity together, with
  nesting watched separately.
- **Style-violation counts are not quality.** A formatter erases most of them.
- **Keep the study in proportion:** it was small, its subjects were novices, it used Java,
  and its effects were modest.

## Baseline gates

Each gate targets a failure mode that matters in AI-written code. There are deliberately
no new style rules.

| Gate | Runs in | Why |
|---|---|---|
| Ruff `BLE`, `TRY`, `RSE`, `EM` | pre-commit, CI | Swallowed or blind exceptions are the classic silent failure. |
| Ruff `C90` (max 10) and `complexipy` (max 15) | pre-commit, CI | The paper's two complexity metrics, used as caps that bound what one review has to hold. Ruff's `PLR` adds limits on branches, arguments and returns. |
| Ruff `FBT`, `PERF`, `PIE`, `FURB` | pre-commit, CI | Boolean traps, slow idioms and dead constructs that are cheap to catch mechanically. |
| `PLR2004` magic values | source only | In tests a literal expected value *is* the specification, so tests are exempt. |
| `check_suppressions.py` | pre-commit (added since `HEAD`), CI (`--base`) | Makes "suppressions need approval" mechanical. It covers line comments (`noqa`, `type: ignore`, `pyright: ignore`, `pragma: no cover`, `pragma: no branch`) and file- or function-level ones (`ruff: noqa`, `flake8: noqa`, `mypy:` and `pyright:` settings, `complexipy: ignore`). Every code needs approval, whether separated by commas or spaces, and a setting's approval covers only its exact value. Spelling variants the tools accept (`type:ignore`, `pragma no cover` without a colon) count as the same directive. In a module only real comments count (read with `tokenize`), so directive text inside a string or docstring is ignored. Notebooks, and modules that cannot be tokenized mid-edit, are scanned as text, which errs toward reporting. |
| `suppressions.toml` | read by the check above | Approved `(path, code, reason)` entries. The guard hook protects the file, so writing an entry triggers the user's permission prompt, and that prompt is the approval. A blanket suppression has no code and cannot be approved. Unit tests may suppress `reportPrivateUsage` without an entry. |
| `check_coverage_records.py` | CI | The CI twin of the Stop hook's check: a changed module that no test imports has no coverage record, and diff-cover would skip it. The vendored gate tooling (`VENDORED_TOOLS` in `stop_gate.py`) is exempt: it is tested here at 100%, kept byte-identical by the drift test, and protected by the guard. Without the exemption every adoption PR would fail. A project's own `tools/` scripts stay gated. |
| `deptry` | pre-commit, CI | Imports must match declared dependencies. It catches a hallucinated or typo-squatted package before install time. |
| `pip-audit` | CI | Dependencies with known vulnerabilities. It needs the network, so it runs in CI only. |
| gitleaks | pre-commit | Hardcoded secrets. It scans staged content, so it guards commits, not CI's `--all-files` run. |
| pytest `xfail_strict`, `filterwarnings = error`; Pyright `reportUnnecessaryTypeIgnoreComment` | every test and type-check run | An xfail that passes, an ignored warning, or a dead suppression is a check that quietly stopped checking. |

## Claude Code hooks

`setup-standards.sh` installs both into a target repository: `.claude/settings.json`
registers them, and the scripts live in `tools/hooks/`. Each is vendored, and
`tests/test_setup_script.py` keeps the copies byte-identical to `skill/`.

### `guard_protected.py` (PreToolUse)

This hook asks the user before a tool call changes anything that decides what "passing" means:

- tool configuration (`pyproject.toml`, `ruff.toml`, `setup.cfg`, `mypy.ini`,
  `pyrightconfig.json`, `pytest.ini`, `tox.ini`, `.coveragerc`)
- `.pre-commit-config.yaml` and `.github/workflows/`
- the gate scripts
- `.claude/settings*.json`

It also asks on `uv add`, `uv remove`, and `uv lock --upgrade`.

- **Why "ask", not "deny":** a legitimate change is one approval away, and an illegitimate
  one is never silent.
- **Case:** paths match regardless of case, since on Windows and macOS `PyProject.toml` is
  the protected file. On Linux the cost is an occasional extra prompt.
- **Limits:** shell commands are matched by pattern, so the check is best effort. A
  determined `python -c` write gets through. CI, which runs the unmodified gates, is the
  backstop.

### `stop_gate.py` (Stop)

When the working tree has changed Python files (staged, unstaged, untracked, or deleted),
this hook runs what CI runs, plus one check CI lacks, in order:

1. `pre-commit` on the changed files that still exist, skipped when the only change is a
   deletion. A deleted module still triggers the tests, since it can break its importers.
2. `pytest` with branch coverage
3. **Coverage record check:** every changed `.py` file must appear in `coverage.xml`.
   A module no test imports is never recorded, and diff-cover silently skips files with no
   record, so without this check an entirely untested module would pass. Notebooks are exempt.
4. `diff-cover --fail-under=100` against `main`

The first failure blocks the stop, and the tail of its output goes back to the agent.

- **Cost:** a turn that touched no Python pays nothing.
- **Git errors fail closed.** A broken configuration, a repository owned by another user, or
  no repository at all blocks the stop with git's message. These are never read as
  "nothing changed".
- **Coverage `omit`:** a changed file the coverage configuration omits has no record either,
  so it blocks. That is by design: omitting a file needs the user's approval anyway.
- **Loop guard:** a stop that is already a retry (`stop_hook_active`) is let through with a
  `GATE FAILED` message to the user, so an unfixable failure cannot loop forever and still
  cannot pass unseen.
- **Assumption:** the base branch is `main`. Elsewhere, diff-cover's error says so and the
  stop is blocked once.

## Mutation testing

100% coverage proves every line ran, not that any test checked the result. mutmut
changes the code one small step at a time (`>=` to `>`, `//` to `/`, a constant
nudged) and reruns the tests. A **surviving mutant** is a change no test noticed.

- **Run:** `bash tools/mutation.sh`, optionally with a mutant name pattern. Always
  through `bash`: the script is not marked executable, and Windows commits cannot
  mark it. mutmut needs `os.fork`, so on Windows it runs in WSL:
  `wsl -e bash tools/mutation.sh`. The
  script keeps the Linux environment outside the checkout, under
  `~/.venvs/<project>`, so it never replaces the Windows `.venv` in a shared
  folder. CI runs it nightly and on demand (`mutation.yml`).
- **Configure:** list the code in `[tool.mutmut] source_paths`. The script refuses
  to run without it, because mutmut's own guess uses the checkout folder's name and
  breaks in clones and CI.
- **Report-only.** Survivors go to `mutants/survivors.txt` and the CI artifact and
  never fail a build. Some survivors are *equivalent* (no observable change), which
  makes any fixed threshold arbitrary.
- **Tests mutmut cannot use** carry `@pytest.mark.no_mutation`: a test that runs
  project code in a child process (mutants are only switched on in-process) or that
  compares source bytes (mutmut rewrites them).
- **Reading a survivor:** `mutmut show <name>` prints the diff. In a live check a
  test asserting `discount(25_000) == 2500` survived `total // 10` becoming
  `total / 10`, because `2500.0 == 2500`. Strict Pyright rejects that mutant through
  the `-> int` annotation, so typing and mutation testing complement each other.
- **This repository (2026-10-06):** the first run killed 1,118 of 1,446 mutants (77%)
  at 100% line and branch coverage. Writing tests for the survivors raised it to 1,360
  of 1,425 killed (95%), plus 7 caught by timeout. Every remaining survivor is listed
  as equivalent, with its reason, in [mutation-equivalents.md](mutation-equivalents.md).
  The same work found one real bug: comprehension variables were wrongly treated as
  declared in the enclosing scope.

## Metrics deliberately not used

- **Coverage percentage as a goal on its own.** It proves lines ran, not that tests assert
  anything. Pair it with mutation testing.
- **Maintainability Index and Halstead metrics.** These are composites with weak validation
  and give no actionable signal.
- **Lines of code, comment density, and commit counts.** These reward volume.
- **Aggregate grades and "tech-debt hours".** They are opaque, and they hide which rule
  failed.
- **LLM-scored quality as a gate.** It is not deterministic. Use it as advice only.
- **Very low complexity thresholds.** They fragment code into many tiny functions, which are
  harder to review than one clear one.
