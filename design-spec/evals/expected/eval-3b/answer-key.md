# Eval 3b answer key: planted defects in `tally`

The fixture `fixtures/planted-defects/` is a five-package uv workspace with exactly six planted defects: five new and one known (listed
in its `BACKLOG.md`). Paths below are relative to the fixture root. Its code is otherwise clean: Ruff, Pyright and MyPy (strict, with
`python-code-standards/pyproject.toml`'s settings), the declarations checker, and its 25 tests all pass.

## Expected dependency matrix

Five internal packages, so the spec has a matrix (more than four), not an import-direction line. Rows import columns; source only:

| imports ↓ / of → | common | io | stage | core | cli |
|---|---|---|---|---|---|
| common | | | | | |
| io | Y | | | **d** | |
| stage | Y | **d** | | | |
| core | Y | | | | |
| cli | Y | Y | Y | **!** | |

No cycles. Every runtime import points at `common` or is made by the composition root, `cli`.

The matrix footnote (skill §3) cites each `!` and `d` cell:

| Cell | Source |
|---|---|
| cli → core `!` | `packages/tally-cli/src/tally_cli/__init__.py:7` |
| io → core `d` | `packages/tally-io/pyproject.toml:8` |
| stage → io `d` | `packages/tally-stage/pyproject.toml:8` |

## The six defects

| # | Rule | Kind | File | Label |
|---|---|---|---|---|
| 1 | 6 | `!`: `tally_cli` imports `tally_core.daily_revenue`, but `tally-cli` does not declare `tally-core` | `packages/tally-cli/src/tally_cli/__init__.py:7`, `packages/tally-cli/pyproject.toml:6` | new |
| 2 | 6 | `d`: `tally-io` declares `tally-core` and never imports it | `packages/tally-io/pyproject.toml:8` | new |
| 3 | 6 | `d`: `tally-stage` declares `tally-io` and never imports it | `packages/tally-stage/pyproject.toml:8` | known (`BACKLOG.md` item 2) |
| 4 | 2 | `tally-stage` only forwards: `load_orders(source, path)` returns `source.read(path)` and enforces nothing | `packages/tally-stage/src/tally_stage/__init__.py:10` | new |
| 5 | 4 | A dict crosses a boundary: `tally_core.daily_revenue` returns `list[dict[str, object]]`, which `tally_io.write_report` consumes through `cli` | `packages/tally-core/src/tally_core/__init__.py:10`, `packages/tally-io/src/tally_io/__init__.py:66` | new |
| 6 | 14 | The `CLAUDE.md` layering diagram disagrees with the code: it routes `tally-cli → tally-stage → tally-core`, but `tally-stage` never imports `tally-core` and `tally-cli` calls it directly, with no `Cli → Core` edge in the diagram | `CLAUDE.md:14` (the `Stage --> Core` edge of the `flowchart LR` under *Layout*) | new |

Grading notes:

- Defects 1 and 2 interact, as in ParquetToXL's `pqx-report`: `tally-cli` installs today only because `tally-core` arrives
  transitively through `tally-io`'s unused declaration. Verified: with `tally-core` removed from `tally-io`'s dependencies,
  `uv sync --package tally-cli --no-dev` followed by `import tally_cli` fails with `ModuleNotFoundError: No module named 'tally_core'`.
  A finding that says so, or that orders the fixes (declare `tally-core` in `tally-cli` first), is better but not required.
- Defect 3 counts if the spec labels it known and cites `BACKLOG.md` item 2. A finding that also calls `tally-stage → tally-io` an
  outward declaration is the same finding, not an extra one.
- Defect 4: deleting `tally-stage` (the fix rule 2 names) also removes defect 3. Either fix direction counts.
- Defect 6: the diagram's other edges (`Cli → Io`, `Cli → Common`, `Stage → Common`, `Core → Common`, `Io → Common`) match the code.
- Defects may be ranked in any order, but each needs a rule number, a file, a consequence and a fix direction (skill §4 step 9).
- The `path:line` citations above are references: a spec citing another line of the same statement or declaration list (say the
  `dependencies = [` line of a `pyproject.toml`) is right. Every line a spec cites must exist in the fixture.

## Not findings

A finding on any of these is a false positive:

- Rule 3: `tally-cli` is the composition root. It picks `CsvOrders`, calls `load_orders`, `daily_revenue` and `write_report`, and
  catches `TallyError` once; it transforms nothing itself.
- Rule 5: `tally-io` enforces the order invariants where orders are produced (the header, three fields per row, an ISO day, an
  amount in whole cents, non-negative and below 10**12; an unreadable input or unwritable report is refused too) and raises
  `TallyError`, the one exception family, which `cli` catches once per run.
- Rule 4 elsewhere: `Order` is a frozen slotted dataclass; `OrderSource` is a Protocol. `csv.DictReader` rows stay inside `tally-io`.
- Rule 2 for `tally-core`: it owns the dedupe decision (a later row with the same `order_id` replaces the earlier one) and the daily
  totals.
- Rules 7, 8, 9, 11 (models and DuckDB parts): no SQL, no DuckDB, no SQLMesh. The spec marks them not applicable. Every package has
  tests under `tests/`.
- Rules 12 and 13: the project keeps no decision records or NFRs. Document mode records existing decisions as ADRs "recorded
  retroactively from code" (or a table) and lists only NFRs a check verifies (the 25 tests); neither is a finding.

## Inferred items

Facts in the spec that the code does not state must be marked *inferred*, for example: the domain states of an order (read →
validated or refused → deduplicated → totalled), the decision each component owns, and why `tally-stage` exists. Volumes, refresh
frequency and latency are unknown and belong under open questions, not as numbers.

In diagrams the marker is a label ending in ` ?` with the `inferred` classDef, a dashed border (skill §7), or one line above a
diagram whose every node is inferred. A dashed arrow used to mark inference is wrong: dashed arrows mean Protocols.
