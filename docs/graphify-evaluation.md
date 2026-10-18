# Graphify and doc/spec knowledge tools: evaluation

Date: 2026-10-18. Task: `docs/plans/design-spec-review.md`, task 4. Every tool ran ephemerally through
`uvx` or `npx`, on copies of the fixtures in a scratch folder outside the repository. No tool was added
as a dependency, no skill was installed into `~/.claude`, and no API key was set. Each tool ran with
`HOME` and `USERPROFILE` pointed at its own scratch folder, so nothing was written to the real home
folder.

Machine: Windows 11, Git Bash, uv 0.11.29 (graphify ran under uv's Python 3.13.14), Node 24.19.0.

Tokens are estimated as bytes / 4. Claude's tokenizer cannot run offline without an API key, and
the conclusions below hold at any plausible bytes-per-token ratio (decision D13 in the nightshift
log). Byte counts come from `wc -c`.

`$S` below is the scratch folder. The helper scripts named in the commands
(`matrix_from_graph.py`, `inventory.sh`, `readset.sh`) are printed in full in the appendix.

Fixtures, built as the evals build them:

- **planted-defects**: `bash design-spec/evals/build-fixture.sh 3b $S/graphify/fx-3b` (head
  `a54aba2`, five packages, 15 Python and TOML files).
- **ParquetToXL at `f8f4a41`**: `git -C <ParquetToXL clone> archive f8f4a41 | tar -x -C $S/graphify/fx-ptx`
  (11 packages, 73 Python files under `packages/*/src`).

## 1. Graphify on code

**Version.** `graphifyy` 0.9.92 (PyPI, 2026-10-16, Apache-2.0; the PyPI name has two y's, the
command is `graphify`). The repository's plans prefer the newest release at least two weeks old, so
the code runs were repeated with 0.9.74 (2026-10-02); the differences are noted below.

**What runs without a model.** Code extraction is local: tree-sitter parses each file, and the graph
gets symbols, `calls`, `imports`/`imports_from` edges between files (with the line), and
`depends_on` edges between packages, read from each `pyproject.toml`. No key and no network are
needed after the first `uvx` download. Two commands build a code graph:

| Run | Command (from `$S/graphify/runs`, on a fresh copy of the fixture) | planted-defects | ParquetToXL |
|-----|------|------|------|
| Headless, code only | `uvx --from graphifyy==0.9.92 graphify extract <copy> --code-only` | 83 nodes, 175 edges; 1.7 s | 2,975 nodes, 8,796 edges; 6.6 s |
| Watch-style rebuild | `uvx --from graphifyy==0.9.92 graphify update <copy>` | 92 nodes, 186 edges | 3,345 nodes, 9,516 edges |
| Report | `uvx --from graphifyy==0.9.92 graphify cluster-only <copy> --no-label` | `GRAPH_REPORT.md` 3,977 bytes | `GRAPH_REPORT.md` 28,245 bytes |
| Graph size | `wc -c <copy>/graphify-out/graph.json` (after `extract`) | 74,008 bytes | 4,074,960 bytes |

Times are wall clock with a warm uv cache (`date` before and after the command). `update` also turns
the repositories' Markdown files into heading nodes, hence its larger counts; both commands give the
same dependency matrix.

**Do the graph's dependencies match the answer keys? Yes, cell for cell, on both fixtures.**
Graphify has no command that prints a package matrix, so `matrix_from_graph.py` (58 lines, appendix)
derives one from `graph.json`: an import edge between files under two different
`packages/<pkg>/src/` folders is an import, a `depends_on` edge is a declaration, and the two give
`Y`, `!` or `d`.

- planted-defects: `python -I matrix_from_graph.py ex-3b/graphify-out/graph.json tally- common io stage core cli`
  prints the matrix in `design-spec/evals/expected/eval-3b/answer-key.md` exactly: `io → core` **d**,
  `stage → io` **d**, `cli → core` **!**, and the six `Y` cells.
- ParquetToXL: `python -I matrix_from_graph.py ex-ptx/graphify-out/graph.json pqx- frame calendar common excel sidecar staging plan verify report pipeline`
  prints the matrix in `design-spec/evals/expected/eval-3/design.md` §6 exactly, including
  `report → frame` **!** and `report → plan`, `report → verify` **d**. That spec was written at
  `8ffaa6f`; its matrix also equals the one in ParquetToXL's own `docs/design.md` at `f8f4a41`.
- Resync: with eval 4's one reversed import applied (its `pqx_common/names.py` copied into a
  graphed copy), `uvx --from graphifyy==0.9.92 graphify update code-ptx4` re-extracted only the changed
  files (`AST extraction: 2/2 uncached files`) and the matrix gained `common → excel` **!**, the cell
  eval 4 expects.
- With 0.9.74 the planted-defects matrix is the same, but ParquetToXL gains a false
  `testing → common` **!**: 0.9.74 resolves the standard-library `import logging` in
  `pqx_testing/plugin.py:12` to `pqx_common/logging.py`. 0.9.92 fixes this. Imports are resolved by
  name, so a module named like a standard-library module is a risk to watch.

The matrix needs that script. The built-in queries do not answer the question:
`graphify explain pqx-report` (426 bytes) lists only the package's declarations (`plan`, `verify`)
and its dependant (`pipeline`). `graphify query "which packages does pqx-report import"` (6,581
bytes) hits its 2,000-token budget, shows 64 of 170 nodes, and does not include the
`model.py:17 → pqx_frame.timestamps` import that makes the **!** cell. That edge is visible only
from `graphify explain model.py`, one file at a time.

**What document mode reads, with and without the graph.** SKILL.md §4 tells the agent to read the
repository's rules and backlog (step 1), run inventory commands rather than read every file (step 3),
read the contracts and orchestration code (step 3), and map the existing docs (step 4). Measured on
each fixture with `bash readset.sh <fixture>` and `OUT=<dir> bash inventory.sh <fixture> <prefix>`:

| Input | planted-defects | ParquetToXL | Can the graph replace it? |
|-------|-----------------|-------------|---------------------------|
| Step 1 files: `CLAUDE.md`, `README.md`, backlog | 3 files, 1,627 bytes (~400 tokens) | 4 files, 37,604 bytes (~9,400 tokens) | No: rules and backlog are prose |
| Step 3 size command (`find … \| xargs cat \| wc -l`) | 3 bytes of output | 5 bytes | Not needed |
| Step 3 imports loop (the `grep -rhoE` command) | 148 bytes | 361 bytes | Yes |
| Step 3 declared dependencies (the `tomllib` command per package) | 303 bytes | 1,438 bytes | Yes |
| Step 3 contracts: files a `grep` for Protocols, Pydantic models, dataclasses and `Literal` finds (`inventory.sh`'s `contracts` line, a heuristic the skill does not prescribe) | output 172 bytes; finds 1 file, 983 bytes | output 8,735 bytes; finds 35 files, 332,068 bytes (~83,000 tokens) | Locates them; cannot replace reading them |
| Step 3 all source under `packages/*/src` (upper bound) | 5 files, 6,895 bytes (~1,700 tokens) | 73 files, 533,360 bytes (~133,300 tokens) | No |
| Step 4 existing docs (`docs/**/*.md` except backlog) | none | 18 files, 354,149 bytes (~88,500 tokens) | No (section 2) |
| Matrix from the graph (`matrix_from_graph.py` output) | 222 bytes | 609 bytes | — |
| `GRAPH_REPORT.md`, if the agent reads it | 3,977 bytes | 28,245 bytes | — |

The graph's nodes carry a label, a file, a line and a community; no field names, types or
annotations (checked by counting the keys of every node in `graph.json`). Docstrings appear only as
`rationale` nodes whose labels are cut at 80 characters (742 of them in ParquetToXL). So the contract
table, the invariants, the decision each component owns and rule 4's "no dicts across a boundary"
still come from reading the source.

The graph replaces only the two matrix commands: their 451 bytes become 222 on planted-defects,
and 1,799 become 609 on ParquetToXL, a saving of 229 and 1,190 bytes (about 60 and 300 tokens).
Against the whole read set that is small whichever bound is taken. The lower bound reads step 1, the
command output, the contract files only and the docs: 3,236 bytes for planted-defects and 734,360
for ParquetToXL, so the saving is 7.1% and 0.16%. The upper bound reads all source instead of the
contract files: 9,148 and 935,652 bytes, so 2.5% and 0.13%. Reading `GRAPH_REPORT.md` as well costs
more than the matrix saves: 3,748 bytes net on planted-defects and 27,055 on ParquetToXL.

Graphify's own benchmark reports much larger savings (`graphify benchmark graphify-out/graph.json`
on the `update` graphs: 3.8x on planted-defects, 136.5x on ParquetToXL). Its baseline is every file graphify
detected (for ParquetToXL 167,250 words, which it counts as ~223,000 tokens, tests and docs included),
set against the cost of one 2,000-token query. Document mode never reads the whole corpus, and a query is not a spec, so that ratio does not
apply here.

**Verdict on code.** The graph is accurate for the dependency matrix, the one structural fact it
captures that design-spec needs, and it updates incrementally in seconds. Design-spec already gets
that fact from two commands whose output is smaller than the graph's, and the grader in PR #21
(task 5) gets it from grimp. Everything else document mode reads is not in the graph.

## 2. Graphify on docs and specs

**Corpus.** This repository's `docs/` at `main` (`eca6ff5`: the four plans and the type-checker
evaluation), the two skills' `SKILL.md` files, and ParquetToXL's `docs/` at `f8f4a41` (20 Markdown
files and 4 JSON files), copied into `$S/graphify/runs/docs`. That is 27 Markdown files, 500,347
bytes (~125,000 tokens): `find docs -name '*.md' -print0 | xargs -0 cat | wc -c`.

**What indexing needs.** Graphify sends Markdown to a language model; locally it extracts only the
headings (below). Without a key, the headless command refuses:
`uvx --from graphifyy==0.9.92 graphify extract docs` prints "error: no LLM API key found (27
doc/paper/image file(s) need semantic extraction). Set GEMINI_API_KEY or GOOGLE_API_KEY (gemini),
MOONSHOT_API_KEY (kimi), ANTHROPIC_API_KEY (claude), OPENAI_API_KEY (openai), DEEPSEEK_API_KEY
(deepseek), or pass --backend." The options are:

- a hosted key; the default Gemini model is `gemini-3-flash-preview` (`graphify/llm.py` in the
  0.9.92 wheel);
- a local server: `--backend ollama`, or any OpenAI-compatible server through `OPENAI_BASE_URL`
  (llama.cpp, vLLM, LM Studio), per `graphify --help`;
- inside Claude Code, the `/graphify` skill (installed by `graphify install` into `~/.claude/skills`),
  which makes the session itself the model: it splits the docs into chunks of 20 to 25 files and
  dispatches one general-purpose subagent per chunk, each given the 7,960-byte (~2,000-token)
  `references/extraction-spec.md` prompt. The tokens come out of the Claude plan's usage.

None of these was set up (decision D14): the approval excludes keys and installing the skill, and
this machine has no Ollama. What a full index of this corpus costs is therefore measured as volume,
not money: about 125,000 input tokens of documents, plus ~2,000 tokens of prompt for each of the two
chunks the skill would make (27 files, at its `ceil(files / 22)` estimate), plus the output graph,
which could not be measured. Graphify caches per file by SHA-256, so later runs pay only for the
documents that changed. The price is that volume times the chosen backend's rate.

**What runs without a model.** `uvx --from graphifyy==0.9.92 graphify update docs` (3.0 s) builds a
410-node, 382-edge graph. Every edge is `contains`; 370 nodes are Markdown headings and the other 40
are keys of the four JSON files (counted from `graph.json`). Without a model the doc graph is
an outline of headings, with no links between documents and no concepts.

**Questions.** Five questions whose answers are in the corpus, each asked as written with
`uvx --from graphifyy==0.9.92 graphify query "<question>"` (from `$S/graphify/runs/docs`, on the
no-model graph). The baseline is the search an agent does anyway: one `grep` for the question's main
noun phrase, `grep -rni --include=*.md --exclude-dir=graphify-out "<phrase>" .` from the same folder.
The phrases were picked by this evaluation, which knew the answers, so the grep column is a
best case. **A**: the output contains the answer. **P**: it names the file or the heading the answer
is under, without the answer. **M**: neither.

| # | Question | Answer (where) | grep phrase: result, output size | graphify query: result, output size |
|---|----------|----------------|-----------------------------------|-------------------------------------|
| 1 | Which decision record covers the century-window rule? | ParquetToXL `docs/decisions/2026-09-15-phase-b.md` (its `design.md:158` maps it) | `century`: **A**, 15 lines, 2,695 bytes | **M**, 7,043 bytes: lists phase A, phase 0 and phase H records, not phase B; still absent with `--budget 4000` (22,422 bytes) |
| 2 | What columns does the boundary contract table have? | `boundary \| input \| output \| invariants \| owner` (design-spec `SKILL.md:61`) | `contract table`: **A**, 9 lines, 1,818 bytes | **M**, 10,264 bytes: starts from ParquetToXL's "5. Boundary contracts" heading, an instance of the table, not the rule |
| 3 | When does design-spec require a dependency matrix? | More than 4 internal modules or workspace packages (`SKILL.md:48`) | `dependency matrix`: **A**, 12 lines, 2,853 bytes | **P**, 6,862 bytes: includes the "3. Spec artifacts" heading (`SKILL.md:36`) the rule sits under, among 50 shown nodes |
| 4 | Which type checkers does the type checker evaluation recommend? | Keep Pyright and MyPy, add none (`type-checker-evaluation.md:8`) | `type checker`: **P**, 7 lines, 1,491 bytes (the file's title line) | **P**, 5,051 bytes: the "Recommendation" heading at line 6 |
| 5 | Where does the design-spec mechanical grader live? | `python-code-standards/evals/design_spec_grade.py` (`plans/design-spec-review.md:21`) | `grader`: **A**, 10 lines, 1,718 bytes | **P**, 7,031 bytes: the plan's title node only |

Without a model, graphify answered none of the five and pointed at the right place for three. A
single `grep` answered four and pointed at the fifth, with 18% to 42% of the
output's bytes. The
semantic graph might do better, since it extracts concepts and cross-document links, but that needs
the model pass above.

**Verdict on docs.** On docs, graphify's value depends on a model pass that costs about the size of
the corpus in input tokens per full index. Without that pass it is a heading outline that loses to
`grep`. Design-spec's step 4 maps existing docs as a table of each record and what it covers, which
listing the files and reading their titles already gives; a heading outline adds little to that.

## 3. Other tools

**Search.** Web searches on 2026-10-18 for tools that index or manage docs and specs for coding
agents found two kinds: indexers, which let an agent search existing docs, and spec managers, which
give the agent a spec format and workflow. Three were chosen to run beside graphify (decision D15):

- **QMD** (`@tobilu/qmd`), a local Markdown search engine with a CLI and an MCP server: BM25
  full-text search, vector search, and LLM reranking, all on this machine with GGUF models.
- **OpenSpec** (`@fission-ai/openspec`), a spec layer for existing codebases: specs as requirements
  with scenarios, and changes as proposal, spec deltas, design and tasks.
- **GitHub Spec Kit** (`specify`), the most-starred spec-driven workflow (141,707 stars): a constitution, then a
  spec, plan and tasks per feature.

Found and not run: Context7 indexes third-party library documentation, not a project's own specs;
DeepWiki and deepwiki-open write a wiki with a hosted service or a model key; Repomix packs a
repository into one file rather than indexing it; Kiro is an IDE, not a CLI.

**Versions.** QMD 2.8.3 (2026-08-16) is the newest release and older than two weeks. OpenSpec 1.14.3
(2026-10-17) and Spec Kit 1.2.1 (2026-10-16) are the newest and younger than two weeks; they only
initialised a project and validated files, which does not depend on the patch level. The two-week
rule matters at adoption, which no tool reaches here.

**QMD on the docs corpus.** Same 27 Markdown files and the same five questions as section 2, from
`$S/qmd/run` with its own scratch `HOME`. Output sizes leave out npx's `npm notice` lines.

- Index: `npx -y @tobilu/qmd@2.8.3 collection add ./docs --name docs` indexed 27 files in 2.0 s, with
  no model (BM25 in SQLite).
- Embeddings: `npx -y @tobilu/qmd@2.8.3 embed -c docs` downloaded `embeddinggemma-300M-Q8_0.gguf`
  (333,590,944 bytes) and embedded 260 chunks from 27 documents in 56 s, download included.
- `qmd vsearch` also downloaded the 1.7B query-expansion model (1,282,438,912 bytes) on first use, and
  `qmd query` the 0.6B reranker (639,153,184 bytes): 2,255,183,040 bytes (2.1 GiB) of models in all
  (`find $S/qmd/home -name '*.gguf' -printf '%s %f\n'`). A hybrid `qmd query` took 29 to 65 s per
  question on this machine.

| # | grep (section 2) | graphify, no model (section 2) | `qmd search` (BM25, no model) | `qmd vsearch` (embeddings + expansion) | `qmd query` (hybrid + rerank) |
|---|------|------|------|------|------|
| 1 | **A** | **M** | **P**: `phase-b.md` ranked first, snippet not the rule; 1,978 bytes | **M**: other decision records; 1,114 bytes | **P**: `phase-b.md` ranked third; 2,270 bytes |
| 2 | **A** | **M** | **M**: two ParquetToXL specs; 819 bytes | **A**: `SKILL.md:61` ranked first; 1,162 bytes | **A**: `SKILL.md:61` ranked third; 2,802 bytes |
| 3 | **A** | **P** | **M**: the two design-spec plans; 1,069 bytes | **P**: `SKILL.md:65`, the import-contract paragraph in the rule's section; 3,042 bytes | **P**: `SKILL.md` (its front matter) ranked second; 2,897 bytes |
| 4 | **P** | **P** | **P**: the evaluation's title; 867 bytes | **P**: the evaluation's title; 2,664 bytes | **P**: the evaluation's title; 2,938 bytes |
| 5 | **A** | **P** | **M**: "No results found."; 18 bytes | **P**: the plan's title; 1,124 bytes | **P**: the plan's title; 2,455 bytes |
| | 4 A, 1 P | 0 A, 3 P, 2 M | 0 A, 2 P, 3 M | 1 A, 3 P, 1 M | 1 A, 4 P, 0 M |

Each QMD cell comes from `npx -y @tobilu/qmd@2.8.3 <search|vsearch|query> "<question>" -c docs`, with
the question asked as written. QMD's models turn a natural-language question into the right place
more often than graphify's outline or BM25 alone, but on a corpus this size a keyword `grep` chosen by
someone who knows the vocabulary still answers more.

**OpenSpec on design-spec's files.** In a scratch copy of planted-defects,
`npx -y @fission-ai/openspec@1.14.3 init tally --tools claude --no-animation` created
`openspec/config.yaml`, `openspec/specs/`, `openspec/changes/archive/`, and 6 skills and 6 commands in
the project's `.claude/`. With eval 3's `design.md` saved as `openspec/specs/architecture/spec.md`,
`openspec validate --specs` fails: "Spec must have a Purpose section. Missing required sections.
Expected headers: "## Purpose" and "## Requirements"", with requirements written as
`### Requirement:` and `#### Scenario:` blocks. As a change's design (`openspec new change
remove-stage`, then the file copied to `openspec/changes/remove-stage/design.md`), `openspec status
--change remove-stage` marks `design` done, since that artifact is free-form, but
`openspec validate remove-stage --type change` fails until the change also has spec deltas
(`## ADDED/MODIFIED/REMOVED/RENAMED Requirements`) or is marked `skip_specs: true`. The CLI needs no
key or model, and indexes nothing; the writing is done by the agent through its skills. Its README
shows how to switch off its telemetry (`openspec config set telemetry.enabled false`).

**Spec Kit on design-spec's files.** In another scratch copy,
`uvx --from git+https://github.com/github/spec-kit.git@v1.2.1 specify init --here --force --integration claude --script sh --non-interactive --ignore-agent-tools`
created `.specify/` (templates for constitution, spec, plan, tasks and checklists, bash scripts, a
workflow; 105,881 bytes) and 10 skills in `.claude/skills/` (139,576 bytes), from
`speckit-constitution` to `speckit-implement`. Its plan template writes, per feature,
`research.md`, `data-model.md`, `quickstart.md` and `contracts/`, which overlap design-spec's
contract table and class diagram. No indexing; no key; the model work is the agent's. It is not on
PyPI; `uvx` installs it from the git tag.

**Comparison.** Facts from the runs above and from `gh api repos/<repo>` on 2026-10-18; activity
counts commits (`gh api "repos/<repo>/commits?since=2026-07-18T00:00:00Z&per_page=100" --paginate`)
and releases (`gh api "repos/<repo>/releases?per_page=100"`, published after 2026-07-18) in the 90
days to the evaluation. Open issues include open pull requests, as GitHub counts them.

| | graphify | QMD | OpenSpec | Spec Kit |
|---|---|---|---|---|
| Kind | Knowledge graph of code and docs | Search index for Markdown | Spec format and change workflow | Spec-driven feature workflow |
| Indexing | Code: local (tree-sitter). Docs: a model (hosted key, local server, or the Claude Code session) | Local: BM25 with no model; vectors and reranking with local GGUF models | None | None |
| Cost | Code free. Docs ~corpus size in input tokens per full index (~125,000 here), then per changed file | Free; 2.1 GiB of models and 29 to 65 s per hybrid query here; a BM25 search took 1.5 to 2.6 s through `npx` (`date` around `qmd search "century-window rule" -c docs`, run twice) | Free CLI; the agent's own tokens | Free CLI; the agent's own tokens |
| Licence | Apache-2.0 | MIT | MIT | MIT |
| Maintenance (90 days) | 74 releases, 1,266 commits; repository created 2026-04-03; 1,537 open issues and PRs | 1 release, 201 commits; created 2025-12-08; 227 open | 13 releases, 346 commits; created 2025-08-05; 191 open | 38 releases, 758 commits; created 2025-08-21; 187 open |
| Install footprint | `graphify install` copies a skill into `~/.claude/skills`; `graphify claude install` adds a CLAUDE.md section and a PreToolUse hook (`graphify --help`) | An npm CLI, used through its MCP server (`qmd mcp`) or its skill (`qmd skill install`) | 6 skills and 6 commands per project | 10 skills and `.specify/` per project |
| Fit with design-spec's `docs/design.md` and `docs/adr/` | Reads them as-is, but adds only the dependency matrix on code and a heading outline on docs | Reads them as-is; finds sections by meaning | Its own format; `design.md` fits only as a change's free-form design, beside required requirement deltas | Its own per-feature folders; overlaps design mode's spec, contracts and approval gate |

The fast release pace that makes graphify capable also moves its results: section 1 found a false
dependency in a release two weeks older than the newest.

## Appendix: helper scripts

All three live in `$S/graphify/scripts/` and only read the fixture or graph they are given.

`matrix_from_graph.py`:

```python
"""Derive design-spec's package dependency matrix (Y / ! / d) from a graphify graph.json.

Usage: python -I matrix_from_graph.py <graph.json> <package-prefix> [row order...]

Imports: `imports_from` / `imports` edges whose source file is under packages/<pkg>/src/
and whose target node's source file is under another packages/<pkg2>/src/ (source only, not tests).
Declarations: `depends_on` edges between package nodes (graphify reads them from each pyproject.toml).
"""
import json
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")

graph_path, prefix = sys.argv[1], sys.argv[2]
order = sys.argv[3:]
g = json.load(open(graph_path, encoding="utf-8"))
nodes = {n["id"]: n for n in g["nodes"]}
src_re = re.compile(r"packages/([^/]+)/src/")


def pkg_of_file(node):
    m = src_re.search(node.get("source_file", "") or "")
    return m.group(1) if m else None


imports, declares = set(), set()
for e in g["links"]:
    s, t = nodes.get(e["source"], {}), nodes.get(e["target"], {})
    if e["relation"] in ("imports_from", "imports"):
        a, b = pkg_of_file(s), pkg_of_file(t)
        if a and b and a != b:
            imports.add((a, b))
    elif e["relation"] == "depends_on":
        a, b = s.get("label"), t.get("label")
        if a and b and a.startswith(prefix) and b.startswith(prefix) and a != b:
            declares.add((a, b))

pkgs = sorted({p for pair in imports | declares for p in pair})
short = lambda p: p[len(prefix):]
rows = [prefix + r for r in order] if order else pkgs
cols = [p for p in rows if any((r, p) in imports | declares for r in rows)] if not order else rows


def cell(a, b):
    i, d = (a, b) in imports, (a, b) in declares
    return "Y" if i and d else "!" if i else "d" if d else ""


print("| imports ↓ / of → | " + " | ".join(short(c) for c in cols) + " |")
print("|---" * (len(cols) + 1) + "|")
for r in rows:
    print(f"| {short(r)} | " + " | ".join(cell(r, c) for c in cols) + " |")
extra = sorted(set(pkgs) - set(rows))
if extra:
    print("packages with edges not in the row order:", ", ".join(extra))
    for a, b in sorted(imports | declares):
        if a in extra or b in extra:
            print("  ", a, "->", b, cell(a, b))
```

`inventory.sh` (SKILL.md §4 step 3's commands, with the prefix filled in; `contracts` is this
evaluation's heuristic):

```bash
#!/usr/bin/env bash
# Run design-spec SKILL.md §4 step 3's inventory commands in fixture $1 (prefix $2) and
# print each command's output size in bytes. Read-only on the fixture.
set -u
cd "$1"; p=$2
run() { local name=$1; shift; local out; out=$(eval "$@" 2>&1); printf '%-18s %6d bytes\n' "$name" "$(printf '%s' "$out" | wc -c)"; printf '%s\n' "$out" > "$OUT/$name.txt"; }
run size "find . \( -name .git -o -name .venv -o -name node_modules -o -name build -o -name dist -o -name graphify-out \) -prune -o -type f \( -name '*.py' -o -name '*.sql' \) -print0 | xargs -0 cat | wc -l"
run imports "for d in packages/*/src/*; do me=\$(basename \$d); echo \"\$me: \$(grep -rhoE '^\s*(from|import) ${p}_[a-z]+' \$d | grep -oE '${p}_[a-z]+' | grep -v \"^\$me$\" | sort -u | tr '\n' ' ')\"; done"
run declared "for t in packages/*/pyproject.toml; do echo \"\$t: \$(python -I -c \"import tomllib,sys; d=tomllib.load(open(sys.argv[1],'rb')); print(d['project'].get('dependencies', []))\" \$t)\"; done"
run contracts "grep -rnE '^class .*\((Protocol|BaseModel|ABC|TypedDict|Enum|StrEnum)|@dataclass|Literal\[' --include='*.py' packages/*/src"
```

`readset.sh`:

```bash
#!/usr/bin/env bash
# Sizes of the file groups design-spec document mode reads in full, in fixture $1.
# Prints: group, files, bytes, bytes/4 (token estimate).
set -u
cd "$1"
grp() { local name=$1; shift; local files; files=$(eval "$@" | sort -u); local n b; n=$(printf '%s\n' "$files" | grep -c .); b=$(printf '%s\n' "$files" | grep . | tr '\n' '\0' | xargs -0 cat 2>/dev/null | wc -c); printf '%-28s %4d files %9d bytes %8d tokens\n' "$name" "$n" "$b" "$((b/4))"; }
grp "step1 rules+backlog" "ls CLAUDE.md README.md CONTRIBUTING.md BACKLOG.md docs/backlog*.md 2>/dev/null"
grp "step3 source (packages/*/src)" "find packages/*/src -name '*.py' -o -name '*.pyi' | grep -v graphify-out"
grp "step4 docs/ (md, not backlog)" "find docs -name '*.md' ! -name 'backlog*' 2>/dev/null"
grp "tests (not read by procedure)" "find tests packages/*/tests -name '*.py' 2>/dev/null"
```
