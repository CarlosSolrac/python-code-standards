# Review: host-aware setup design (Claude Opus 5.5)

Reviewed: `design.md`, `analysis.md`, `requirements/*.md`, `skill/tools/setup_models.py`, `tests/test_setup_models.py` (call sites only). Date: 2026-11-17.
Line references are `design.md:N` unless another file is named. Sources were checked 2026-11-17.

## Blockers

**B1. Copilot has no defaults, so the planned code fails or writes Claude aliases into the Copilot file.** `design.md:46,86,98-99`; `setup_models.py:32,46,128,153`.
- `ModelChoices` has one global `DEFAULTS` (`opus`, `sonnet`, `codex`, `gpt-5.4`). `stored_choices` fills a missing line from it (`setup_models.py:128`).
- So `-y` on an unconfigured Copilot host, or an empty interactive answer, records `opus`/`sonnet` in `copilot-instructions.md`. That contradicts the rule that Copilot gets no suggestions because its names are unknown (`:99`), and Codex R3 (`requirements-codex.md:13`: never translate a model name across hosts).
- Picking provider `copilot` runs `SUGGESTED[provider][0]` (`setup_models.py:153`). With no Copilot suggestions (`:99`) that list is empty, so it raises `IndexError`.
- Fix: put per-host defaults and suggestions in the `Host` row. State what Copilot's defaults are, or that `-y` leaves the Copilot model lines blank or marked "picker". Say what the reviewer model defaults to when the provider is `copilot`.

**B2. ADR-2's "unclosed marker reads as unconfigured" deletes the user's text on the next run.** `design.md:137,169`; `setup_models.py:102-106,131-138`.
- I reproduced it. Start with `intro\n<START>\nuser text kept\n`. `block_span` returns None, so `merge_block` appends a new block. On the second merge, `find(START)` matches the orphan marker and `find(END)` matches the new block's end, so the span covers the user's text, which is then replaced. Result: `'user text kept' in t3 == False`.
- Under ADR-2, `-y` treats this host as unconfigured and appends defaults, which sets up the loss on the following run. Nothing "reports" the orphan today.
- Fix: treat a START without a matching END (or any second START) as an error for that host. Write nothing to that file, report the file, and add the case to the NFR-02 tests.

## Should-fix

1. **`-y` with no configured host is undefined.** The flowchart says "yes keeps recorded hosts, else ask" (`:65`), but `-y` must never ask. Opus R2 (`requirements-claude-opus-5-5.md:13`) gave the rule; the analysis does not mark it as cut. Fix: state that `-y` uses configured hosts, else detected hosts, else `claude-code`, and never prompts.
2. **There is no way to un-select a host.** If the user drops a host interactively, its block stays, and ADR-2 still counts it as configured, so the next `-y` keeps it (`:132-137`). Fix: say that a deselected host's block is left alone and listed in the summary as "still configured; delete the block to remove". Alternatively, offer removal behind a confirm.
3. **Declined goes to the wrong state.** `Declined --> Unconfigured` (`:42`) is wrong for a host that was already Recorded: nothing was written, so it stays Recorded. Fix: send Declined back to its prior state.
4. **Kept is not always a no-write.** `Recorded --> Kept` on `-y` (`:37`) hides today's settings.json repair (`setup_models.py:84-88`), which does write. Fix: add a `Kept --> Written` edge for "settings model missing", or name the repair in the Kept label.
5. **NFR-04 "existing tests pass untouched" (`:170`) cannot hold.** The tests drive `main(argv, ask=replies(...), home=...)` with answers in role order (`tests/test_setup_models.py:108`) and call `ask_choices(defaults, ask)` (`:79-91`). A new host question shifts every reply, and the new `pending_changes(host, home, ...)` signature (`:88`) breaks callers. Fix: reword as "every existing behaviour is kept; tests are updated only to answer the host question", or skip the host question when only `~/.claude` exists.
6. **Detection reads the real environment.** `COPILOT_HOME` comes from `os.environ`, but `main` injects only `home` (`setup_models.py:66`). Tests on a dev box with `COPILOT_HOME` set would turn non-deterministic. Fix: add an injected `environ: Mapping[str, str]` and list it in the contract table (`:85-90`).
7. **Failure isolation has no mechanism.** `apply` confirms once and writes sequentially with no exception handling (`setup_models.py:193-206`, `design.md:62,89`). One `PermissionError` crashes the run. Hosts written before the failure are written; hosts after it are not, and none is reported. NFR-07 (`:173`) and Codex R12 (`requirements-codex.md:31`: non-success result per host) need defining. Fix: write and catch per host, report per host, and return non-zero when any host failed. Today `main` always returns 0 (`setup_models.py:75-76`).
8. **The summary has no owner.** Analysis R8 (`analysis.md:44`) and the gate note (`:100`) need a summary step, but there is no summary node in the flowchart (`:50-77`) and no row in the contract table. Fix: add a `summary` function and row (per host: written, kept, unknown, checklist).
9. **The `Host` fields cannot carry what ADR-1 puts in the row.** The fields are "name, instructions file, settings model key, label" (`:46`). ADR-1 says the gate note is data in the row (`:129`), and the table also needs a detection dir, a home env var (`COPILOT_HOME`), defaults and suggestions (B1). Fix: list every field.
10. **The reviewer providers contradict open questions.** The table offers `codex` and `claude` on the Copilot host (`:98`). Open question 3 (`:190`) and Sonnet Q4 (`requirements-claude-sonnet-5-5.md:83-84`: the work machine should not call personal services) are still unresolved. The design also has no "skip review" option. Fix: mark that row "pending Q3", or offer `copilot` plus `none` at work.
11. **Requirements dropped without a note in the analysis:**
    - Sonnet R13 (`requirements-claude-sonnet-5-5.md:38`): a selected host that is not installed must not fail the run.
    - Sonnet N4 (`:49`): atomic writes. `apply` uses plain `write_text`.
    - Sonnet N5 (`:52`): an unparsable file aborts with its name. `json.loads` at `setup_models.py:184` raises a bare traceback.
    - Opus R13 (`requirements-claude-opus-5-5.md:30`): print the command to run the Stop gate by hand. The `:100` note omits it.
    - Opus Q5 / K5 (`:66,91`): which home is used when VS Code runs on Windows and the CLI in WSL. NFR-05 (`:171`) says only that "both work".
    - Codex NFR4 (`requirements-codex.md:42`): spaces and non-ASCII characters in paths.
    - Codex Q2 (`:65`): an unavailable model, and Copilot's `Auto`.

    Fix: add each one to the analysis as carried or cut, with a reason.
12. **Copilot facts have no sources in the spec.** `:96,101,103` ("verified VS Code and GitHub docs") and `analysis.md:20-27` cite no URLs. Fix: cite the URLs already in `requirements-claude-opus-5-5.md:71-76` with their dates. I re-checked them on 2026-11-17:
    - CLI user file `$HOME/.copilot/copilot-instructions.md`, moved by `COPILOT_HOME`: https://docs.github.com/en/copilot/how-tos/copilot-cli/add-custom-instructions
    - VS Code Copilot harness user file `~/.copilot/copilot-instructions.md`: https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference
13. **`COPILOT_HOME` is applied to VS Code without evidence.** The GitHub page documents `COPILOT_HOME` for the CLI only, and the VS Code reference does not mention it. Yet the spec applies it to "CLI and VS Code agent mode" (`:22,94-96`). If it is set, the block lands where VS Code may never read it. Fix: write the `COPILOT_HOME` path for the CLI, and warn in the summary when `COPILOT_HOME` differs from `~/.copilot`. This stays until review note 1 (`:180`) is answered.

## Missing risks

- **R-a. The VS Code "Local" harness reads `~/.claude/CLAUDE.md`.** The VS Code reference says: "Local checks the workspace-root `CLAUDE.md`, `.claude/CLAUDE.md`, `~/.claude/CLAUDE.md`, and `CLAUDE.local.md`" (setting `chat.useClaudeMdFile`; URL in item 12). On a machine that has both homes, an agent can load two model blocks that disagree. Fix: add a risk line, and consider a host name in the block heading (for example `## Models (Copilot)`).
- **R-b. An orphan or duplicate marker loses user text** (B2). This is not in the spec's risks.
- **R-c. A stale block outlives a host change** (Should-fix 2). The agent keeps following old model names.
- **R-d. One `PermissionError` aborts the whole run** (Should-fix 7). The user may read the hosts already written as "done".
- **R-e. Repo `.claude/settings.json` hooks already fire under Copilot** (Opus K1). This appears only as open question 2 (`:189`). Fix: state it in the summary at work, not only in the spec.

## Nits

- `:10` says Copilot writes "exactly 1" file, but the contract writes only files that would change (`:88`), so it can be 0. Fix: "at most 1".
- `:57` says detection is "home directory exists, nothing else", but `:101` also counts the `COPILOT_HOME` variable. Fix: say "dir exists, or `COPILOT_HOME` is set to an existing dir".
- `:53` defaults `ask_hosts` to configured hosts, but the flowchart has no edge from it to `Stored`. Fix: add `AskHosts --> Stored`, or note that `main` passes the configured set in.
- `:46` defines a `HostChoices` type, but the `pending_changes` contract (`:88`) takes host and choices separately. Fix: use one form.
- `:169` NFR-02 "CRLF included": `merge_block` adds LF separators (`setup_models.py:137-138`) to CRLF files. The text outside the block survives, but the file ends up with mixed line endings. Fix: state this, or use the file's own line ending (Opus N4).
- `:3` calls PR #120 "merged". Fix: check whether that is still true when the spec is approved.
- `:100`: the gate note could name the command to run by hand (Should-fix 11).

## Over-building

- **The `copilot` reviewer provider on the Claude Code host** (`:98`). No draft asked for a Copilot reviewer on the personal machine, and the review protocol drives the Codex companion. Fix: offer `copilot` only on the Copilot host.
- **ADR-3's separate per-surface checklist** (`:139-145`). It is justified only by Codex R9 and repeats ADR-4's checklist. Fix: merge the two into one checklist with a surface column.
- **`label` on `Host`** (`:46`) has no consumer named. Fix: drop it unless the summary uses it.
- Everything else traces to a requirement in at least one draft.
