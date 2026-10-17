# TODO

1. **Fill the template.** Skill §8 sends every Standard pipeline to `template-0-summaries`, whose index holds only a README; `template-sqlmesh-duckdb` is empty. Until it is filled, eval 1 (template found) fails and eval 4 can't build its fixture. Planned for a separate session.

Approved 2026-10-17 from the review of the "LLM Visualization Standard". Items 2–7 edit `design-spec/skill/SKILL.md` and each needs eval assertions; more than two files, so post a plan first.

2. **Evidence citations (document mode).** Add a `source` column (`path:line`) to the boundary contract table and the dependency matrix footnote; every non-inferred node in the component flowchart cites one. Replaces "facts read from code are stated plainly" (§4 step 6). Update `evals/expected/eval-3/design.md` and add an eval assertion that citations resolve in the planted-defects fixture.
3. **Inferred marker on diagrams.** Inferred nodes get a `?` label suffix and `classDef inferred stroke:#555,stroke-dasharray:5 5` (dashed border). Dashed arrows stay reserved for Protocols (§7); don't use them for inference.
4. **Change-impact diagram.** New artifact #15, design mode restructuring an existing codebase only: `flowchart` with `classDef added` / `changed` / `removed`; reusable as the PR-description diagram.
5. **Grain and key in the contract table.** Columns become `boundary | input | output | grain/key | invariants | owner` (§3).
6. **Replace `C4Context`/`C4Container` with `flowchart` + boundary subgraphs.** Mermaid's C4 is experimental, lays out poorly, and ignores `classDef`, so items 3–4 can't mark it. Change artifacts #2–#3 in the skill, the worked example in `template-0-summaries` and `template-sqlmesh-duckdb` (do this while filling them, item 1), and the other files that name `C4Context`/`C4Container`: `design-spec/evals/evals.json`, `evals/expected/eval-3/design.md`, `design-spec/tests/validate_mermaid.test.mjs`.
7. **OpenAPI pointer.** One line in §3: if the project exposes an HTTP API, the contract table cites its OpenAPI file.
