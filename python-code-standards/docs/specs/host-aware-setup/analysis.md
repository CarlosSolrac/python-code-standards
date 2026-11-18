# Requirements analysis: host-aware setup

Merges three independent drafts in `requirements/`: Sonnet 5.5 (S), Opus 5.5 (O), Codex (C). The spec in `design.md` is built from this table.

## Agreement (all three)

| Topic | Result |
|---|---|
| Machines are separate; no profile switching | Non-goal. Per-machine state under the home directory |
| Nothing environment-specific in the target repo | Hard constraint (S N1, O N2/R14, C NFR2/R7) |
| Every write outside the repo is previewed and confirmed; `-y` is the only bypass | Kept from `setup_models.py` today |
| `-y` keeps stored choices, writes defaults only when none exist | Kept |
| Interactive re-run offers stored values as defaults | Kept |
| No model validation; entitlement is unknowable | Non-goal |
| Shared gate code is identical across hosts; only an adapter differs | Constraint |
| Windows and WSL/Linux homes both work | Constraint |
| Copilot hooks are preview; contracts may drift | Risk, with dated sources |
| Claude-only installs keep working | Constraint (S N6, O N6, C R14) |

## Verified Copilot facts (Opus, 2026-11-17, official docs)

- User instructions: `~/.copilot/copilot-instructions.md`, or `$COPILOT_HOME/` when set (Copilot CLI). VS Code's Copilot harness uses the same file.
- Copilot also reads repo `AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md`, and repo `.claude/settings.json` hooks.
- Hooks: repo `.github/hooks/*.json`, user `~/.copilot/hooks/`; lower camelCase events (`agentStop`, `preToolUse`); PascalCase accepted with Claude matcher rules.
- VS Code, Copilot CLI and the Copilot app share one harness; hooks are in preview; enterprise-managed settings can disable the Claude and Codex harnesses.

Still unknown: default-model settings key for the CLI (`config.json` vs `settings.json`), any file-based default in VS Code, whether `Stop` maps to `agentStop`, the enterprise's model names.

## Conflicts and how the spec resolves them

| # | Conflict | S | O | C | Resolution |
|---|---|---|---|---|---|
| 1 | One Copilot host or two surfaces | not split | one harness | distinct surfaces (R9) | One `copilot` adapter, because the verified docs show one instruction file and one harness. Setup reports the two surfaces separately in its summary and checklist. |
| 2 | Is Codex a host | reviewer only (non-goal to make Claude Code run on Copilot) | reviewer only unless Q1 | supported host (R1) | Reviewer only. Codex's contracts are unverified (C says so itself). Open question 1. |
| 3 | Automated smoke test of each host (C R11) | none | none | required | Not automated: it needs the host installed and running. Setup prints a per-host manual checklist; fixture-based contract tests stay automated. Recorded as ADR-4. |
| 4 | Host detection | not covered | suggest default, never act unconfirmed | not covered | Adopted for hosts: existence of the host home directories only, a default for the question, never an action. |
| 5 | Where host choice is stored | per machine | implied | per machine | No new state file. A host counts as configured when its instruction file holds a managed block. ADR-2. |
| 6 | `--show` command (O R16) | none | wanted | none | Cut. The end-of-run summary covers it; add when asked. |
| 7 | Stop-gate and `.claude/settings.json` hooks under Copilot (O R12/R13, K1) | not covered | in scope | contract tests per host | Not changed here. Setup prints the gate status per host. The real hook adaptation is the separate portability work; open question 2. |
| 8 | Copilot default-model key | write if documented (R9) | write only if verified (R6) | report unknown, never emulate (R6) | Write nothing to any Copilot settings file until the key is verified; record preference in the instruction block and say so. |

## Requirements carried into the spec

R1 host question with detected default; R2 reviewer provider adds `copilot`; R3 per-host instruction block, same markers; R4 text outside the block byte-identical; R5 confirm-first writes, `-y` rule unchanged; R6 Claude Code behaviour unchanged; R7 Copilot writes only the instruction file; R8 per-host summary naming unsupported or unknown capabilities and the manual checklist; R9 failure of one host does not touch another; R10 no repo writes from the model step. Cut: `--show`, automated host smoke tests, Codex as host, hook changes.

## Requirements the first revision dropped without a note (review finding)

| Source | Requirement | Resolution |
|---|---|---|
| S R13 | A selected host that is not installed does not fail setup | Carried: writes are still offered; the summary says the host was not detected (design section 6, `summarize`) |
| S N4 | Atomic writes, repair of a partial state | Carried: ADR-4, NFR-08; the `-y` settings repair already repairs a block without its model |
| S N5 | An unparsable file aborts with its name | Carried, narrowed: that host is `Invalid` and named, the others continue (ADR-4) |
| O R13 | The Stop gate has a stated result per host, with a manual command | Carried: the summary text in section 6 |
| O Q5, K5 | Which home when VS Code runs on Windows and the CLI in WSL | Carried as a risk and a review note; setup writes the home it resolves and the summary names the path |
| C NFR4 | Spaces and non-ASCII characters in paths | Carried: NFR-06 |
| C Q2 | An unavailable model, Copilot's `Auto` | Cut: no validation (non-goal); `picker` is the default and names are free text |
| C R11 | Automated smoke test per host | Declined with reasoning: ADR-3; Copilot is reported "configured, not verified" |
| C R1 | Codex as a supported host | Open question 1, recommended as a follow-up after its contracts are researched |
| O R16 | `--show` | Cut |

## Review resolutions

Reviews: `reviews/review-claude-opus-5-5.md` (2 blockers, 13 should-fix) and `reviews/review-codex.md` (3 blockers, 10 should-fix, 2 nits).

| Finding | Resolution in design.md |
|---|---|
| Opus B1: no Copilot defaults, `IndexError` and Claude aliases in the Copilot file | Per-host `defaults` and `suggestions` in the `Host` row; `picker` sentinel; changed provider takes the host default |
| Opus B2, Codex 3: orphan marker deletes user text (reproduced on merged code) | `Invalid` state, no write, named, non-zero exit; ADR-2; NFR-03. The merged code has this defect today and the change fixes it |
| Codex 1: Codex host deferred | Not settled by the author. Open question 1 with a recommendation |
| Codex 2, Opus 7: failure isolation | ADR-4: per-host plans and writes, no cross-host rollback, invariant weakened to match |
| Codex 4: ADR-4 (old) on smoke tests | ADR-3 states the cost: "configured, not verified", automated verifier listed as a follow-up |
| Codex 5, Opus 1: `-y` host selection | Pure `selected_hosts` with a contract row |
| Codex 6, Opus 9, Codex 10: row too small, defaults | Full `Host` fields listed in section 6 |
| Codex/Opus: declined edit goes to Unconfigured | Split `PlannedNew` and `PlannedUpdate`; declining an update stays `Recorded` |
| Opus 4: Kept sometimes writes | `Repaired` state |
| Opus 5: NFR-04 untouched tests | Reworded (NFR-04) |
| Opus 6: detection reads the process environment | `environ` injected (contract table, NFR-06) |
| Opus 8: summary has no owner | `summarize` node and contract row |
| Opus 10: reviewer providers on Copilot host | `copilot` and `none` on the Copilot host only; `codex`/`claude` wait for open question 3 |
| Codex 9: existing settings model, hand-edit message | Pre-existing value preserved; the summary is the outcome |
| Opus 12, Codex 11: facts without sources | URLs and date in section 6 |
| Opus 13: `COPILOT_HOME` for VS Code | Warn in the summary; CLI-only documented |
| Codex 13, Opus R-e: existing hooks under Copilot | Promoted to a risk; the summary says it |
| Codex 14, 15, Opus over-building | ADR-1 reworded to two hosts; README line dropped; `label` dropped |
| Opus nits | Applied: "at most", detection wording, flowchart edge, one pending-changes form, line endings |

## Revision 3 (user request after revision 2)

| Request or recommendation | Resolution in design.md |
|---|---|
| No overlap between home and work; no cross-reading | Structural: host config only in the machine's home directories; modules installed only into directories their audience scans (section 6A, ADR-6, NFR-11) |
| Partition knowledge: common, Claude/Codex, Copilot Enterprise | Skills for common and review, one host file per host; only the chosen host's file is copied |
| Reviewer must not read the coding guide; use review knowledge | `adversarial-review` skill plus `review_brief.py` output; NFR-13 tests that it carries no coding how-to |
| Reviewer needs the definition of done (recommendation, approved) | ADR-8: project invariants as checkable claims, with a drift test |
| Short text so a model does not open other models' files (recommendation, approved) | ADR-7: one guard sentence per host's always-on file and a fixed focus string; limits stated |
| Verify Codex loading, Codex skills, Copilot path scoping first (recommendation, approved) | `verification-2026-11-17.md`: Codex reads only `AGENTS.md`, supports skills in `.agents/skills`; Copilot supports `applyTo` and skills |
| Open question 1 (Codex as a host) | Resolved as a reviewer-only target; the verified loading rules make it a small row |
| Token savings | Not claimed: always-loaded text is about 800 words, the skill about 4.2k words on demand |

## Revision 4 (reviews of revision 3)

Reviews: `reviews/review-r3-claude-opus-5-5.md` (2 blockers, 13 should-fix) and `reviews/review-r3-codex.md` (4 blockers, 4 should-fix, 1 nit). Both found that "isolation by directory" overstated the verified facts.

| Finding | Resolution |
|---|---|
| Both: isolation fails on a multi-host machine and for Claude and Copilot reviewers | Guarantee table in 6A: structural for the Codex reviewer only, advisory otherwise; placement table with remaining overlaps; ADR-6 reworded; NFR-11 checks every selected host's scan set |
| Opus B1: user text and links on this machine load the coding guide (verified: `~/.codex/AGENTS.md`, `~/.agents/skills` links) | "Existing installs" in 6A, NFR-14, risk; setup reports, never edits; open question 2 asks permission |
| Opus B2, Codex 4: no route for the review brief; guard hides it | Coordinator runs the brief and builds the prompt; exact command in 6A; reviewer guard has no `skill/` path; ADR-7 |
| Codex 3, Opus over-building: Codex row does not fit `Host` | Separate `ReviewTarget` type and contract row; counts in section 1 updated |
| Codex 7, Opus 7: installer under-specified, second configuration path | Module copies folded into `Plan`; `install_modules.py` removed; open question 1 now asks embed vs clone |
| Opus 1, 2, 3, Codex 5: overstated or incomplete facts | 6A qualifies by default, fallback, override and import; scan-set table marks "not documented" |
| Opus 8, 9 | Stable `host.md`; Claude-only lines move to the host file |
| Opus 11 | Skill renamed `review-standards` |
| Opus 13 | Recorded as a decision: Codex does not write code in this setup |
| Codex 9, Opus 10 | ADR-9: explicit skill naming, activation eval, skill provisional |
| Codex 8, Opus missing risks | Added: routing, `CODEX_HOME`, stale modules, anchoring, argv length, `AGENTS.override.md` (NFR-15) |
| Opus 12 | No Copilot review launcher until open question 3 is answered |

## Machine alignment and user decisions (2026-11-17)

| Item | Result |
|---|---|
| Delivery | Embedded copies are setup's only path; hand-managed symlinks on the home machine are respected (NFR-14) |
| `~/.codex/AGENTS.md` | Now a symlink to `codex/AGENTS.md` (reviewer guard only); the previous file is saved at `~/.codex/backups/AGENTS.md.2026-11-17`. Codex no longer carries the coding rules or its own review protocol when it codes |
| `~/.agents/skills` | `python-code-standards` and `design-spec` links removed; `review-standards` linked |
| `~/.claude/CLAUDE.md` (repo root `CLAUDE.md`) | "when writing or editing" wording and a coder guard line |
| Copilot at home | default (no configuration) |
| Copilot Enterprise models | Six names recorded as suggestions; role mapping asked |
| New finding | `~/.claude/CLAUDE.md` is a symlink into the repo; the merged setup would write its block into a tracked file. NFR-16 added |

## Defaults and the Copilot file (2026-11-17)

| Item | Result |
|---|---|
| Orchestrator and coder, all hosts | Sonnet orchestrates, Opus 5.5 codes. Claude: `sonnet`, `claude-opus-5-5`; Copilot: `Sonnet`, `Opus 5.5` (picker names unverified) |
| Claude `model` in `settings.json` | Already `sonnet`; unchanged |
| Copilot default file | `copilot/copilot-instructions.md` with the guard and the models block; `~/.copilot/copilot-instructions.md` links to it |
| Models block in the global `CLAUDE.md` | Written in the setup block format, so `stored_choices` reads it back |
| Copilot reviewer | `gpt-astra`, inferred from the repo's `.github/copilot-instructions.md`; to be confirmed |

## Picker screenshot (2026-11-17)

| Item | Result |
|---|---|
| Sonnet and Opus 5.5 at Copilot | Confirmed in the picker as `Claude Sonnet 5.5` (default) and `Claude Opus 5.5`; the Copilot default file now uses those names |
| User's earlier list | Corrected to picker spelling: `GPT-6.1 Sol`, `GPT-5.3-Codex`, `Gemini 4 Argon`, `Grok 4.7`, `MAI-Code-1.1-Flash` (written `main-code-1.1-flash`), `GPT-6 Astra` (written `gpt-astra`) |
| Reviewer | `GPT-6 Astra`, confirmed by the user; `.github/copilot-instructions.md` says `GPT-Astra`, which matches neither `GPT-6 Astra` nor `GPT-6.2 Astra` exactly (pre-existing, reported not changed) |
| Source | A screenshot supplied by the user, not documentation; seat and surface not stated |
