# Plan: finish the cross-agent hook portability branch — pass CI, close the test gaps, move the Copilot rule

Source material: the branch `copilot/cross-agent-hook-portability` (commits 27a71d8 and f808670, no PR yet) and the daytime review of
2026-10-27. That review found that the branch behaves exactly as `main` does for Claude Code, but it fails two CI gates, leaves test
gaps, and adds a Copilot-only rule to `CLAUDE.md`, which is also the user's global `~/.claude/CLAUDE.md`. Where this plan and anything
else differ, this plan wins.

The review's evidence, so the night does not repeat it:

- The branch merges into `main` without conflicts, and the merged tree passes `uv run pytest` (1005 tests). `guard_protected.py` is at
  100% statement and branch coverage.
- Two CI gates fail on the merged tree:
  - `uv run complexipy skill/tools tests evals/grade.py evals/design_spec_grade.py` fails because `has_invalid_path` scores 21,
    over the cap of 15.
  - `uv run pyright` reports `tests/test_guard_protected.py:291:9 - error: Type of "fixture" is unknown (reportUnknownVariableType)`.
- Ruff, the format check, mypy, `check_declarations.py` and `check_passthrough.py` are clean on the changed files.
- Claude Code 2.1.310 sends `tool_use_id` and no `timestamp` in a PreToolUse event. On the real Claude payload shape, the branch's
  guard produced byte-identical output to `main`'s for 940 events.

## Decisions already made by the user

Do not reopen these; log a decision only for choices this plan leaves open.

- **Claude Code behaviour must not change.** Every change keeps the guard's output for Claude-shaped events (with `tool_use_id`,
  without `timestamp`) identical to `main`'s.
- **Branching**: task 1 branches from `origin/copilot/cross-agent-hook-portability`, merges `origin/main` into it, and opens its draft
  PR against `main`. That PR is the review and merge vehicle for the whole feature. Tasks 2 and 3 are stacked on task 1's branch and
  are independent of each other.
- **Fix `has_invalid_path`'s complexity by restructuring, not by suppressing it**:
  - Either fold the empty-or-non-string path check into the single walk `target_paths` already does, or split the walk so no
    function scores over 15.
  - No `# noqa`, no complexipy exclusion, and no threshold change.
- **Fix the pyright error with a narrowing cast** in the test, the way the surrounding tests use `cast`. No `# pyright: ignore`.
- **Pin current behaviour; do not change it.** Task 2 adds tests for behaviour the review found but did not ask to change, such as a
  patch nested in an object asking for approval. A test that exposes a real defect becomes a blocker naming the exact change, not a fix.
- **The Copilot review rule moves to `.github/copilot-instructions.md`**, word for word, and is removed from `CLAUDE.md`.
- **Not tonight**:
  - Changing how the guard treats `apply_patch` input nested in an object, or Copilot CLI's camelCase payload
    (`toolName`/`toolArgs`).
  - Changing the `powershell` key in `skill/assets/claude-settings.json`, which the SchemaStore schema flags as unknown.
  - Claude Code's own Windows gap: without Git Bash, `command` runs in PowerShell, where `"$CLAUDE_PROJECT_DIR"` is empty.
  - Deleting the `copilot/cross-agent-hook-portability` branch.
  - Do not attempt them.

## Tasks

| # | Task | Depends on | Done-check |
|---|---|---|---|
| 1 | Bring the branch up to date and pass CI | — | From `python-code-standards/`, every command in `.github/workflows/ci.yml` passes on the branch: `uv run pytest --cov=skill.tools --cov=evals.grade --cov=evals.design_spec_grade --cov-branch`; `ruff check` and `ruff format --check` on the CI sources; `check_declarations.py`, `check_passthrough.py`, `complexipy skill/tools tests evals/grade.py evals/design_spec_grade.py`, `pyright`, `mypy`, `deptry .`. `guard_protected.py` stays at 100% statement and branch coverage. `tests/test_setup_script.py` passes, so the vendored copies in `setup-standards.sh` match `skill/` byte for byte. |
| 2 | Close the guard's test gaps | 1 (stacked) | The tests listed in section 2 exist and pass. The task 1 done-check still passes. `uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=100` passes. |
| 3 | Move the Copilot review rule out of `CLAUDE.md` | 1 (stacked) | `git grep -n "GPT-Astra" -- CLAUDE.md` prints nothing. `.github/copilot-instructions.md` holds the rule word for word. `git diff origin/main -- CLAUDE.md` on the branch is empty. |

### 1. Up to date and green

- Merge `origin/main` into the task branch with a merge commit. Do not rebase: the branch's commits are someone else's.
- Fix the two CI failures as decided above.
- Re-run every CI command.
- If `setup-standards.sh` no longer matches `skill/` after the merge, regenerate it with the project's own tool
  (`skill.tools.vendor_templates`, as `renovate.json`'s `postUpgradeTasks` does). Do not edit it by hand.

### 2. Test gaps

In `python-code-standards/tests/test_guard_protected.py`. The fixture file is `tests/fixtures/hook_events.json`.

1. A real Claude Code PreToolUse event:
   - Fields: `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name: "PreToolUse"`, `tool_use_id`, no
     `timestamp`.
   - For an Edit of `pyproject.toml` and for a Bash `uv add requests`, it gets the nested `hookSpecificOutput` decision.
2. Give each fixture an `expected` field (`"silent"` or `"ask"`), and assert it in the fixture test instead of always asserting silence.
   Add one synthetic Claude Edit of `pyproject.toml` with `expected: "ask"`, and label it synthetic in its `case` text, as
   `docs/agent-hooks.md` requires.
3. Copilot-shaped Bash and PowerShell events (string `timestamp`, no `tool_use_id`) that modify a protected file get the root-level
   `{"permissionDecision": "ask", ...}` decision.
4. A JSON-string `tool_input` naming an ordinary file (`{"file_path": "src/app.py"}`) stays silent.
5. The rule that recognises a Copilot event, at its edges: a non-string `timestamp` and a `tool_use_id` present but `null` both get the
   nested decision.
6. `apply_patch`:
   - `*** Delete File: pyproject.toml` and `*** Move to: pyproject.toml` headers ask.
   - A patch nested in an object (`{"input": "*** Begin Patch\n*** Update File: src/app.py\n*** End Patch"}`) asks with the
     "could not be inspected" reason. Name that test so it says the behaviour is pinned, not endorsed.

### 3. The Copilot rule

- Move the `## Copilot Review Rule` section from `CLAUDE.md` to a new `.github/copilot-instructions.md`, unchanged.
- Leave the rest of `CLAUDE.md` exactly as it is on `origin/main`.
- Put one sentence in the PR body: the rule now reaches Copilot in this repository only, not every project, as it did when the global
  `CLAUDE.md` held it.

## Morning steps (for the user, not nightshift)

1. Open `.nightshift/LOG-<date>.md`; read *Morning summary* and *Needs you* first. Then close the nightshift session and start a fresh
   one: until the log is `complete` it denies every prompt.
2. Turn the Codex stop gate back on: `node "$CX" setup --enable-review-gate` from the repository root.
3. Mark the draft PRs ready. Merge task 1 into `main`, retarget tasks 2 and 3 to `main`, then merge them.
4. Pull `main` in `/home/carlos/_src/python-code-standards`: `~/.claude/CLAUDE.md` and the skill links point at that checkout.
5. Delete `copilot/cross-agent-hook-portability`, local and remote, once task 1 has merged.
6. Decide the *Not tonight* items. If the Copilot rule should apply in every project, add it to Copilot's user-level instructions
   file, outside this repository.
7. Run a live smoke test of the guard in a Copilot host. The tests check its contract, not a real host.
