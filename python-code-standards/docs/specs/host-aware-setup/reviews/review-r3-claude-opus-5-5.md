# Review r3: host-aware setup, section 6A and revision 3 additions (Claude Opus 5.5)

Reviewed 2026-11-17: `design.md` (rev 3), `verification-2026-11-17.md` (`ver:`), `analysis.md` (Revision 3 table), `reviews/` (r2), `skill/SKILL.md`, `skill/tools/review_brief.py`, the Codex plugin 1.0.6 `commands/review.md`, `commands/adversarial-review.md`, `prompts/adversarial-review.md`, and this machine's `~/.codex`, `~/.agents/skills`, `~/.claude/skills`, `~/.copilot` (listing only). Line refs are `design.md:N` unless named. R2 findings are not re-raised.

## Blockers

**B1. The always-on files the spec leaves untouched tell every reviewer to load the coding guide.** `:150,154,160,264`
- `~/.claude/CLAUDE.md:7` and `~/.codex/AGENTS.md:7` (655 words, user text outside any block) both say "Python: invoke the `python-code-standards` skill before reading or editing code". A reviewer reads code, so it must load the guide ADR-8 keeps from it.
- `~/.agents/skills/python-code-standards` already exists here (a symlink to `skill/`, created today). Codex scans that directory (`ver:25`). NFR-11 checks only what the installer writes, so it passes while the isolation fails.
- `:154` "Codex's always-on text stays a few dozen words" is false on this machine. NFR-02 keeps the 655 words outside the block.
- Fix: add a migration step and an NFR. It reports or removes (behind a confirm) the coding skill in `~/.agents/skills`. The "invoke python-code-standards" rule becomes "when writing or editing" in both global files (the user's files, so this joins open question 2).

**B2. The reviewer bundle has no channel for `review_brief.py` output, and the guard hides it.** `:152,156`
- `:156` says the brief goes to every run, but the focus string is "fixed". The brief changes each run.
- The reviewer cannot make the brief itself. The companion runs Codex `sandbox: "read-only"` (`codex-companion.mjs:414`). `review_brief.py` runs through `uv run` and writes `.complexipy_cache/review-brief.json` (`review_brief.py:32`).
- The guard (`:152`) forbids `skill/`, which holds `tools/review_brief.py` and, in this repo, most of the code under review. Every change touches `skill/`, so the exception always fires and the guard does nothing here.
- Fix: the coordinator runs the brief and appends it to the per-run focus text, so the focus becomes "fixed preamble + brief". Drop the repo-specific `skill/` from a sentence that is written to global files used in every repo.

## Should-fix

1. **6A overstates the Codex facts.** `:141` "never `CLAUDE.md`". `ver:17-18` says CLAUDE.md is ignored *unless* it is listed in `project_doc_fallback_filenames`, and `AGENTS.override.md` replaces `AGENTS.md` (`ver:12`). Fix: write "by default". Detect `$CODEX_HOME/AGENTS.override.md` and report that the guard block would be ignored.
2. **6A understates Claude Code and Copilot loading.** `:141` omits that Claude Code reads repo `AGENTS.md` natively when there is no `CLAUDE.md` (`ver:57`). It also omits that Copilot CLI auto-loads repo `CLAUDE.md` and `.claude/CLAUDE.md` (`ver:41`). So the guard (`:152`) tells hosts that a file they load as project instructions "is not for you", and at work this repo's root `CLAUDE.md` is read anyway. That breaks "nothing is read twice" (`:135`). Fix: limit the guard to files the host does not auto-load. State the repo `CLAUDE.md`-under-Copilot case as a limit.
3. **The skill-directory claims are a lower bound, so the isolation proof rests on silence.** `:140,143`. VS Code's table "is not every directory it recognizes" (`ver:46`). VS Code also reads `~/.claude/skills` and `~/.agents/skills` (`ver:46`), but `:140` lists only `~/.copilot/skills` and `~/.agents/skills` for Copilot. "Invisible to Claude Code" (`:143`) means only "not documented" (`ver:56,70`). Fix: say "not documented to scan" and put VS Code's four user directories into `:140`.
4. **A machine with several hosts is not modelled, and this machine is one.** `~/.copilot` exists here (with `config.json`), so `detected_hosts` offers Copilot at home. The 6A table (`:145`) has one column per machine type, not per selected host. With both selected, Copilot (CLI and VS Code) reads `~/.agents/skills`, so the Copilot coder sees the review skill, and VS Code sees the coding skill in `~/.claude/skills`. Fix: key the install plan on the set of selected hosts and reviewer provider. Add an NFR-11 case for {claude-code, copilot} with provider `codex`.
5. **Reviewer provider `claude` defeats isolation, and Limits does not say so.** `:149,161`. A Claude reviewer runs under Claude Code with `~/.claude/CLAUDE.md` and the coding skill in `~/.claude/skills` loaded. That is the same-host case as at work, but `:161` names only work. Fix: add it to `:161` and to the "Same-host reviewer" risk (`:277`).
6. **The Codex row does not fit the `Host` contract.** `:111` has no `roles` field. Section 1 still counts 2 hosts, 8 values and 2 homes (`:7,9,10`). The context view (`:17-31`) lacks `~/.codex`, `~/.agents/skills` and `~/.copilot/skills`. The state machine has no meaning for a block without model lines, and no contract says the Codex row is selected exactly when the reviewer provider is `codex`. Fix: drop the Codex row and let the module installer write the one guard line (see Over-building), or add `roles` and the selection rule to sections 1-5.
7. **ADR-6 contradicts open question 1.** ADR-6 (`:230`) decides "Setup copies only the chosen host's files". Open question 1 (`:294`) recommends that setup only prints an installer command. Section 5 has no row for `install_modules`, and section 3 has no install states. Fix: make ADR-6 say "the module installer copies" and add its contract row (input: hosts, provider, home, environ; output: plan; invariant: NFR-11).
8. **The host file has no stable name.** `:148` keeps either `hosts/claude-codex.md` or `hosts/copilot.md`, and "the skill" references it. One `SKILL.md` cannot name a file that exists under one of two names. Fix: install the chosen file as `host.md`.
9. **"Common" is not host-neutral.** `:147` takes "today's `SKILL.md` body". That body uses `${CLAUDE_SKILL_DIR}` (`SKILL.md:44,99`), `mcp__ide__getDiagnostics` (`:110`) and a Claude-hooks section (`:52-60`). Copilot expansion of that variable is unverified. Fix: move these lines to `hosts/claude-codex.md`, and list `CLAUDE_SKILL_DIR` under Copilot as an item for the seat to check.
10. **The review protocol does not need `adversarial-review` to pass the guard, and the switch changes more than focus.** Native `review` already runs Codex, which loads `~/.codex/AGENTS.md`, so the guard block reaches it without focus text. What really needs a focus channel is the brief (B2) and naming the review skill explicitly (`ver:28`; implicit matching is unreliable under a fixed adversarial prompt). Swapping in `adversarial-review` also changes the stance to a design challenge with "material findings only, no style" and JSON output (`prompts/adversarial-review.md:7,38-40,49`). Fix: in ADR-7, state the real reason (brief + explicit skill name) and the stance change, and let open question 2 ask about both.
11. **The name `adversarial-review` collides with the companion subcommand and `/codex:adversarial-review`.** `:149,156,295`. Fix: name the skill `review-standards` (or similar).
12. **There is no review path at work.** The protocol lives in `~/.claude/CLAUDE.md` and drives the Codex companion. Copilot has neither, so `:149` installs a review skill that nothing invokes. Fix: state how a Copilot review is started and where its protocol text lives, or mark it pending open question 3.
13. **Codex as a coder (`codex:rescue`) loses the standards.** Moving the coding skill out of `~/.agents/skills` (NFR-11) leaves Codex rescue/coding runs without `python-code-standards`, while `~/.codex/AGENTS.md` still holds coding rules. Fix: record the decision that Codex never codes here, or make it a risk.

## Nits

- `:13` "800 words" for global CLAUDE.md: measured 808. Fine. The skill is 1,417 + 2,785 = 4,202 words. Fine.
- `:295` "the file `~/.claude/CLAUDE.md` links to" is unclear (it *is* that file). Fix: "your global `~/.claude/CLAUDE.md`".
- `:248` drift test has no file in section 8 (`:168-182`). Fix: name it (for example `tests/test_review_skill.py`).
- `:162` the Codex cap is `project_doc_max_bytes`, which is configurable (`ver:15`). Fix: "32 KiB by default".
- `:152` "Each host omits its own file's name": Codex's own file is `AGENTS.md`, but Copilot also loads it natively (`ver:41`). The per-host rule needs a table, not a sentence.

## Over-building

- **The Codex `Host` row** (`:154`, ADR-1 `:190`) brings the 8-value matrix, the state machine and detection for one sentence in `AGENTS.md`. Fix: let `install_modules` write the guard line in a marked block, with no `Host` row.
- **Per-host `hosts/*.md` files** (`:148,175-176`) for a few lines of hooks and picker notes. Fix: put them in the managed block, or one `host.md` section (Should-fix 8).
- **The guard in the focus string and in AGENTS.md** (`:238`) is duplicate text for the same Codex run. Fix: keep one.

## Missing risks

- Existing installs (symlinks in `~/.agents/skills`, user rules in global files) break isolation silently (B1).
- `AGENTS.override.md` hides the guard block (Should-fix 1).
- An argv focus string carrying a multi-line brief on Windows may hit quoting or length limits. Fix: test it through `node "$CX" adversarial-review` on Windows.
- Implicit skill matching: the review skill may not load in a run whose prompt never names it.
