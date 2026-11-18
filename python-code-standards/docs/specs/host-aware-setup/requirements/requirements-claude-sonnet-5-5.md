# Requirements: host-aware setup (Claude Sonnet 5.5)

Written independently from the shared brief. No Copilot fact below is verified against current
documentation; each is marked **unverified**.

## 1. Goal and users

One person works in two environments on separate machines: a personal one (Claude Code with
Claude Pro, plus Codex with Codex Pro) and a work one (GitHub Copilot Enterprise, used from VS
Code agent mode and the Copilot CLI). Running setup on a machine should leave that machine's
agent host(s) configured with the user's model preferences and the same quality gates, with no
hand editing and no environment-specific data in a shared repo.

## 2. Functional requirements

- **R1.** Setup asks which agent host or hosts the machine uses: Claude Code, Copilot CLI, VS
  Code agent mode, or any combination. The answer is stored per machine, in the home directory.
- **R2.** Setup keeps asking the three existing questions (coordinator, coding, adversarial
  reviewer) and offers the stored answers as defaults on a re-run.
- **R3.** The reviewer provider choice gains `copilot` next to `codex` and `claude`; for each
  provider the model prompt shows suggestions that match it.
- **R4.** The model preferences are written to each selected host's own instruction location,
  not only `~/.claude/CLAUDE.md`, inside a marker-delimited block that setup owns.
- **R5.** Text outside setup's block in any host file stays byte-identical across runs.
- **R6.** Every write outside the repo is shown and confirmed first; `-y` confirms unasked.
- **R7.** `-y` keeps an existing block for a host and writes defaults only for a host with none.
  It never overwrites a user-set value in a host's settings file.
- **R8.** For Claude Code, the coordinator is also written to `settings.json` `model`, as today.
- **R9.** Where a Copilot surface offers a configuration key for a default model, setup sets it
  under the same confirm-first and never-overwrite rules; where it does not (the picker is the
  only control), setup records the preference in the instruction file and says so.
- **R10.** The shared gate code (pre-commit, tests, coverage record check, diff-cover) is the
  same for every host. Only the host adapter (instruction file path, hook wiring, hook output
  shape) differs per host.
- **R11.** Hook wiring for Copilot is generated from the host's documented event names and
  input/output contracts, and each shape has a test that reads a recorded sample event.
- **R12.** Setup prints, per host, what it wrote, what it kept, and what it could not do.
- **R13.** A host that is selected but not installed does not fail setup; its writes are still
  offered, and the summary says the host was not found.

## 3. Non-functional requirements and constraints

- **N1.** Nothing environment-specific (model names, provider, host list) is written into the
  target repo or committed. All of it lives under the user's home directory.
- **N2.** No personal data (user name, email, paths under the user's home) is sent to any
  external service, including during any online lookup of host documentation.
- **N3.** Home directory resolution works on Windows and on WSL/Linux. Under WSL the Linux home
  is used, and the docs say the Windows host's home is a separate configuration.
- **N4.** Writes are atomic enough that an interrupted run leaves either the old or the new
  file, never half of one; a re-run repairs a partial state (for example a block without its
  settings key).
- **N5.** A settings or instruction file that cannot be parsed aborts setup before any repo file
  is written, with a message naming the file.
- **N6.** The tool stays standard-library-only and embedded byte-identically in
  `setup-standards.sh`, with the existing drift tests extended to any new embedded file.
- **N7.** New code meets the project's gates: strict typing, declarations before first binding,
  100% statement and branch coverage on changed lines, no suppressions.
- **N8.** Model names are free text with suggestions; setup does not validate them against a
  provider, because it cannot know a provider's current catalogue.

## 4. Non-goals

- Switching between personal and work settings on one machine (the user said the machines are
  separate).
- Validating that a model name exists, or that the user has an entitlement to it.
- Making Claude Code run on a Copilot subscription (**unverified**: believed unsupported).
- Translating Claude Code skills into other hosts' skill or prompt formats, beyond the
  instruction text setup writes.
- Managing credentials, tokens or login state for any host.
- Rewriting the existing gate code to be host-neutral beyond its hook adapter.

## 5. Open questions and unverified facts

For the user:

1. Which instruction location does each work surface honour on the work machines: a repo file
   such as `.github/copilot-instructions.md` or `AGENTS.md`, a user-level file, or an
   organization policy? A repo file would conflict with N1 unless it holds no model data.
2. Does the enterprise administrator restrict which models, hooks or custom instructions are
   allowed? If so, setup may be unable to do part of R4 or R9 and must say so (R12).
3. Should the adversarial reviewer at work be a Copilot model, or does the work machine have no
   second-model option and the reviewer step simply be skipped there?
4. Should the work machine's reviewer ever call out to the personal Codex or Claude services?
   This brief assumes no, for data-handling reasons; confirm.

Unverified facts (all **unverified**; research before design):

- Copilot CLI and VS Code agent mode each read some user-level instruction file.
- Copilot hooks exist in both surfaces, with PascalCase event names and a different output shape
  per surface (the portability branch asserts this; its sources were not re-checked here).
- Whether either surface lets a configuration file set the default model, and whether a
  subagent or reviewer model can be chosen programmatically.
- Whether Copilot Enterprise exposes Anthropic or OpenAI models in the picker, and under what
  names, which decides the suggestion lists in R3.

## 6. Risks

- **Contract drift.** Host contracts change faster than this repo releases. Mitigation: record
  the source and date of each adapter's contract, and fail the adapter's tests when a recorded
  sample no longer parses.
- **Admin policy blocks writes.** The feature degrades to "print what to set by hand" and says
  so, rather than failing setup.
- **Silent overwrite of user text.** A bug in block replacement could damage a hand-edited
  instruction file. Mitigation: R5 tests with CRLF, missing trailing newline and unmatched
  markers.
- **Scope growth.** Three hosts times three preferences is nine writes; keep the adapter
  interface to one decision per host (where does it live, and what shape is it) so a fourth
  host does not need a new code path.
- **Model-name rot.** Suggested aliases go stale. They are suggestions only (N8).
