# design-spec eval runbook

Each eval is one real session: the `design-spec` skill works in a fixture project from one prompt, and `evals.json` lists what a
correct session leaves behind. Each eval's `files` entry names its fixture under `fixtures/` (empty when `build-fixture.sh` makes the
fixture from nothing or from GitHub), and `answer_key` names the grader's reference under `expected/`.

## 1. Check the prerequisites

- `~/.claude/skills/design-spec/SKILL.md` resolves to this repository's `design-spec/skill/` (morning step 3 of
  `docs/plans/design-spec.md` creates the link), and `~/.claude/skills/python-code-standards/SKILL.md` to
  `python-code-standards/skill/` (eval 2 is graded against it).
- `git`, `uv`, and Node 22.22.2+ or 24.15+ (the diagram checker) are on the path. The checker's first run needs network once.
- Network access: eval 1 looks up `template-0-summaries` on GitHub, eval 2's build runs `uv sync`, and eval 4's build clones the
  template.

## 2. Build the fixture

Build into an empty folder of its own, outside this repository. The first argument is the eval's `id` (eval 3b is id 5; `3b` also
works):

```bash
bash design-spec/evals/build-fixture.sh 3 /e/ds/eval3/parquettoxl
```

| Eval (id) | Fixture | Notes |
|---|---|---|
| 1 | an empty git repository | no commits |
| 2 | an empty project set up by `python-code-standards/skill/assets/setup-standards.sh` | needs uv and network; the setup's pre-commit hooks run on its commit |
| 3 | ParquetToXL at `8ffaa6f`, from `fixtures/parquettoxl-8ffaa6f.bundle` | `git log --oneline -1` must print `8ffaa6f Added backlog of bugs` |
| 3b (5) | `fixtures/planted-defects/`, the `tally` uv workspace | same SHA on every build |
| 6 | the same build as 3b, from `fixtures/planted-defects/` | same SHA as 3b; build it into its own folder |
| 4 | `template-sqlmesh-duckdb` with `ports.py` importing `adapters` | fails while the template has no `docs/design.md`: record eval 4 as not run |

The build prints the fixture's last commit; save it, since grading compares against it. No fixture keeps a remote. Never copy
`expected/` into the fixture or its parent folder: it holds the answers. Agent output must never be written inside this repository.

## 3. Run the session

1. Open a fresh Claude Code session in the fixture folder. Accept the folder-trust prompt; eval 2's fixture registers the standards'
   project hooks in `.claude/settings.json`, as a real project would.
2. Type the eval's `prompt` from `evals.json`, exactly. Evals 3 and 3b share the prompt "Document the design of this repository."; it
   names no artifact or finding, so what the spec contains is the skill's doing.
3. Answer nothing about the design itself. Your global rules may make the agent ask before it adds a dependency or edits more than
   two files (eval 2 needs a Parquet library); approve that once and note it in the grade. In evals 1 and 6 the skill stops by itself
   at "Approve or correct before I implement."; do not approve.

## 4. Collect

- The reply, and the session transcript (`~/.claude/projects/<folder>/<session-id>.jsonl`).
- In the fixture: `git status --untracked-files=all` and `git log --oneline -3`, plus `git diff <build commit>` for every eval but 1,
  whose repository has no commit (its status lists every file the session wrote).
- `docs/design.md` and `docs/adr/`, if written, and the checker's result on the spec, run from this repository's root:
  `node design-spec/skill/tools/validate_mermaid.mjs <fixture>/docs/design.md`.
- For eval 2, the project's gates in the fixture, after the status above is saved: `git add -A` first, since
  `pre-commit run --all-files` checks only files git tracks, then `uv run pre-commit run --all-files` and
  `uv run pytest --cov --cov-branch --cov-report=term-missing`.

## 5. Grade

Mark each assertion in `evals.json` pass or fail, quoting the evidence. The answer keys are references, not templates: a spec
that words things differently passes as long as the assertion holds.

| Eval | Answer key | What to compare |
|---|---|---|
| 3 | `expected/eval-3/design.md`, `expected/eval-3/backlog2.md` (PR #7's merge commit `f8f4a41`; `design.md` brought up to the skill's current diagram rules) | the `pqx-report` row of the matrix (§6 of `design.md`); findings 1 and 2 of `backlog2.md`; item 9.1 labelled known (§11 of `design.md`) |
| 3b (5) | `expected/eval-3b/answer-key.md` | the six findings with rule, file and label; its *Not findings* list counts false positives, which the assertions do not fail but the grade should report |
| 6 | none | the change-impact flowchart's node names against the fixture: `git -C <fixture> ls-files packages` lists the packages and modules that exist |

"No code changed" means `git diff <build commit>` (evals 3, 3b, 4, 6) and `git status --untracked-files=all` (all) show only
documentation files (`docs/design.md`, ADRs, a backlog file); for eval 2 the opposite holds: code, and no spec.
