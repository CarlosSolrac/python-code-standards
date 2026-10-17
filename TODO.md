# TODO

1. **File the frontmatter bug report** at `anthropics/claude-code`, from `E:\_src\claude-bug-report\bug-skill-frontmatter-dashes.md` (title from its *Title* section, body from *What's wrong?* on). Auto mode blocks `gh issue create`, so this needs you or a permission rule.
2. **Fill the template.** Skill §8 sends every Standard pipeline to `template-0-summaries`, whose index holds only a README; `template-sqlmesh-duckdb` is empty. Until it is filled, eval 1 (template found) fails and eval 4 can't build its fixture. Planned for a separate session.

## Watch for

3. **Nightshift rule breaks seen on 2026-10-16** (`.nightshift/LOG-2026-10-16.md`): D12, one fix round past the three-round Codex limit; and the duplicate `## Plan` log heading recurred. Add a sentence to the nightshift skill for each if it happens again.
