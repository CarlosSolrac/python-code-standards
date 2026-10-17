Everything is merged into `main`, mine included. The rules files now agree with one another. The real problems are a backlog and plans nightshift would re-run, a few stale statements, and two open decisions the night left you.

## What's most current

| Area | Current source | State |
|---|---|---|
| Global rules | `CLAUDE.md` (PR #10, 10-16) | Agrees with the Python skill and `design-spec`: architecture designed from the domain outward, each unit implemented top-down, a spec before the edit plan |
| Python skill | `python-code-standards/skill/SKILL.md` (PR #10) | Agrees |
| Nightshift | `nightshift/SKILL.md`, my `05412fe`, unchanged since | `prep-nightshift` points to its sections correctly |
| Design-spec | `design-spec/skill/SKILL.md` (PR #9) | Follows the plan's decisions |
| Prep-nightshift | `prep-nightshift/SKILL.md` (PR #14, plus the B1 fixes in PR #17) | Applied |
| Design-spec decisions | `docs/plans/design-spec.md` | This plan wins over `handoff/`, by its own statement |
| Last night | `.nightshift/LOG-2026-10-16.md` | Complete. B1 and B2 were fixed in PR #17 (I confirmed the `TallyError` fix in the fixture) |

The README matches the skills. Installed links: `design-spec` and `prep-nightshift` are now in `~/.claude/skills`, with the other two.

## Contradictions and stale items, by impact

1. **`TODO.md` lists four tasks that are all done.** Those are the upgrade plan, the CI plan, the type-checker evaluation, and `/prep-nightshift`. The next `/nightshift` will collect them and do them again. Fix: clear the four items.
2. **Plan files nightshift will collect again:**
   - `docs/plans/design-spec.md` has no done markers on tasks 1–4.
   - `docs/plans/ci-pipeline.md` and `package-upgrades.md` end in daytime steps for you that change dependencies and CI, so the night would end them blocked.
   - Fix: mark the plans done, or move them under `docs/plans/done/` where nightshift's *Plan* doesn't look. I can't tell from the files whether you still want the two upgrade plans worked, so that part is your call.
3. **The template `design-spec` relies on is empty.**
   - Skill §8 sends every Standard pipeline to the templates in `template-0-summaries`, whose index holds only a README; `template-sqlmesh-duckdb` is an empty repository.
   - Eval 1 asserts the template is found, and eval 4 can't build its fixture. This was planned (a separate session fills it), but until then the skill points at nothing.
4. **Stale statements:**
   - `docs/plans/ci-pipeline.md:10` says PR #12 is "not merged"; it is.
   - The `design-spec-skill-state` memory still says PR #17 is open, and lists "link the skills" as pending; both are done.
   - `MEMORY.md` still says "next: production trial", already noted in `TODO2.md`.
5. **`design-spec` contradicts itself on Small requests.** Line 10 says design mode always produces the spec and stops for approval. Line 17 says a Small request skips the spec and writes code directly. Codex flagged this in the draft and it survived. Fix: one clause on line 10, "except Small".
6. **Two decisions the night left open:**
   - **D6:** the size gate still counts "an existing ADR already forces the answer" as Small, in both the skill and the README. Codex wanted that limited to design mode.
   - **D20:** `prep-nightshift` fences files off with a "Not for nightshift" first line, but nightshift's *Plan* has no rule for that line. It's honoured, not enforced, so one line in nightshift's *Plan* would make it a rule.
7. **The night broke two of nightshift's own rules:**
   - **D12:** it went one fix round past the three-round Codex limit.
   - Its log has the duplicate `## Plan` heading again. I said it hadn't recurred after the reruns, but in a real night it did. Both are worth a sentence in the skill if they happen again.
8. **Minor:**
   - `handoff/` is now tracked on `main`, while the plan's morning step 4 says to delete it. `HANDOFF.md` also describes the old precedence order.
   - The README's "What it may do alone" leaves out schema migrations, which nightshift's Authority allows.

**Still in the plan's morning steps:** the `hooks:` entry in `design-spec`'s frontmatter, the live hook test, deleting `handoff/`, filing the frontmatter bug report, and filling the template.

I changed nothing. Items 1, 4 (the repo files) and 5 are quick fixes I can make. Items 2 and 6 need your decisions first. The memory updates go through `TODO2.md`, which says to apply them only once you agree.


-------------------------------------------------------------


Items 1 and 5 are done. Items 2 and 3 are made but not committed, so they don't count yet: your global rules ask before a commit.

1. **Removed** the `pcs-fixes` worktree, after checking it was clean and stopping its Codex service, plus the `post-nightshift-fixes` branch, which was merged, both locally and on `origin`.
2. **Cleared `TODO.md`.** All four items were done. I kept the file, empty, because nightshift and `/prep-nightshift` look for it.
3. **Removed `handoff/`** (`git rm`), and fixed what referred to it:
   - **`docs/plans/design-spec.md`:** its source-material links now point to the two files on GitHub at commit `eb189bb`, the last one that has them. Both links resolve.
   - **`docs/plans/package-upgrades.md`:** its Mermaid check command validated the draft by path and would have failed. It now checks `design-spec/skill/SKILL.md`, which I ran, and the expected output is updated to match. I also dropped a sentence describing the deleted draft.
   - **Left as they are:** a dated record in `ci-pipeline.md`, the plan's instructions to delete `handoff/`, and an example folder name in `prep-nightshift`.
5. **Bug report saved** to `E:\_src\claude-bug-report\bug-skill-frontmatter-dashes.md`. It's byte-identical to the draft, and the Claude Code version it cites (2.1.294) is still what's installed.

`git status` shows `TODO.md`, `docs/plans/design-spec.md` and `docs/plans/package-upgrades.md` modified, and the two `handoff/` files deleted. Shall I commit these to `main` and push?

**Before you run nightshift again:** it also reads `docs/plans/`, which still holds three plans:
- **`design-spec.md`:** all its tasks are done.
- **`package-upgrades.md`:** dependency changes, so nightshift would block.
- **`ci-pipeline.md`:** CI changes, so it would block too.

A future run would pick all three up. When you're ready, mark the finished plan done, or move the plans to a non-plan folder such as `docs/decisions/`, so they stay out of the next run.