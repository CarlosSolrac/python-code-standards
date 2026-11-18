# Requirements: host-aware setup for two agent environments

Author: Claude Opus 5.5 (independent draft). Date: 2026-11-17. Status: draft for comparison.

## 1. Goal and users

One user works on the same repositories from two machines: a personal machine with Claude Code (Claude Pro) and Codex (Codex Pro), and a work machine with GitHub Copilot Enterprise used through VS Code agent mode and the Copilot CLI. Setup must give both machines the same quality gates, while recording each machine's agent host, models and personal instructions only in that machine's home directory.

## 2. Functional requirements

Host detection and choice
- R1. Setup asks which agent host or hosts the machine uses, from at least `claude-code` and `copilot` (VS Code agent mode and Copilot CLI, one Copilot harness). It suggests a default from what is installed (`~/.claude`, `~/.copilot`, `claude`/`copilot`/`codex` on PATH) but never acts on a detection the user has not confirmed. Test: with a fake home holding only `.copilot`, the suggested default is `copilot`; the answer recorded is the one typed.
- R2. `-y` (non-interactive) keeps the host choice already recorded on this machine; with none recorded it takes the detected default, and with nothing detected it takes `claude-code` (today's behaviour). Test: each of the three cases against a fake home.
- R3. A re-run offers the stored host and model answers as defaults, as `setup_models.py` does today. Test: second run with empty answers writes the same files byte for byte.

Model questions per host
- R4. Model questions, suggestions and defaults come from the chosen host. For `claude-code` they stay as today (coordinator, coding, reviewer provider and model). For `copilot` the questions are the same three roles, but suggestions are Copilot model identifiers and any identifier the user types is accepted. Test: Copilot run accepts an identifier not in the suggestion list.
- R5. The reviewer question allows a provider that is not the coordinator host (for example Codex reviewing on the personal machine) and allows "same host" (a Copilot model reviewing at work). Test: both combinations record without error.
- R6. Setup does not claim to enforce a model in a host that offers no file-based default. For each host it records the choices in that host's user instruction file (R7), and writes a host default-model setting only where the host documents one (Claude Code: `~/.claude/settings.json` `model`; Copilot CLI: see open question Q3). Test: Copilot run without a verified default-model key writes no model setting and prints that the model is chosen in the picker or with `--model`.

User-level instruction files (outside the repo)
- R7. For `claude-code`, the marker-delimited block stays in `~/.claude/CLAUDE.md` (unchanged behaviour). For `copilot`, the same block is written to `~/.copilot/copilot-instructions.md` (or `$COPILOT_HOME/copilot-instructions.md` when `COPILOT_HOME` is set). Test: fake home with `COPILOT_HOME` set writes under it, not under `~/.copilot`.
- R8. Writing the block keeps every byte of the file outside the markers, and a re-run replaces only the block. Test: file with text before and after the markers survives two runs unchanged outside them.
- R9. Each write outside the repo is shown as a diff or full new content and needs a yes, except under `-y`, which may only create a missing block or missing file, never overwrite stored answers. Test: answering no leaves every file unchanged (compare mtimes and bytes).
- R10. The block's content tells the agent which roles use which models and that the coordinator runs the gates itself; it contains no account names, emails, tokens, organisation names or absolute paths. Test: rendered block matches a fixed template; a check rejects `@`, `\Users\`, `/home/`.

Hooks and gates
- R11. The shared gate code (pre-commit config, pytest and coverage settings, diff-cover, `tools/hooks/*.py` policy) is identical whichever host is chosen. Test: running setup with each host choice in a fresh repo yields an identical repo tree.
- R12. Hook registration that lives in the repo must work for, or be harmless to, every host that reads it. Copilot CLI and the VS Code Copilot harness both read the repo's `.claude/settings.json`, so each event and output envelope registered there is checked against the Copilot hooks reference; an event Copilot does not map is either registered additionally in a Copilot-documented form or listed as a known gap in the setup output. Test: adapter tests with Copilot-shaped input for each registered event, including the Stop gate.
- R13. The Stop gate (tests, coverage, diff-cover after a turn) has a defined result on each host: it runs, or setup says plainly that the host does not run it and gives the command to run by hand. Test: setup output for `copilot` names the gate status.
- R14. Host-specific hook files that hold machine paths or personal choices go in the user's host directory (`~/.claude/settings.json`, `~/.copilot/hooks/`), never in the repo. Test: `git status` after a Copilot setup in a clean repo shows only the shared files of R11.

Reporting
- R15. Setup ends with a summary: host, models per role, each file written or left alone, and each gate that will not run automatically on this host. Test: snapshot of the summary for each host.
- R16. A command reports the current machine's recorded choices without writing anything (dry run or `--show`). Test: no file changes after the command.

## 3. Non-functional requirements and constraints

- N1. Privacy: setup sends nothing over the network, and no file it writes contains personal data (names, emails, account or organisation identifiers, tokens). Detection reads only file existence and PATH, never credentials or session logs.
- N2. Nothing environment-specific is committed: no host choice, model name, home path or employer detail in any file under the repo. The repo stays valid on both machines with no local edits.
- N3. Every write outside the repo is shown and confirmed first (R9); writes inside the repo keep today's setup behaviour.
- N4. Home resolution works for native Windows (`%USERPROFILE%`), WSL and Linux (`$HOME`), and honours `COPILOT_HOME`. A WSL shell on a Windows machine uses the WSL home unless the user says otherwise (Q5). Paths are built with `pathlib`, and files are written UTF-8 with the file's existing line endings preserved.
- N5. Idempotent: a second run with the same answers changes no bytes.
- N6. Personal-machine behaviour without the new options is unchanged; existing tests of `setup_models.py` keep passing.
- N7. Each Copilot fact the code relies on is cited to an official reference in the docs (as `docs/agent-hooks.md` does) and dated, because the Copilot hook feature is in preview.
- N8. Changed code meets the repo's own gates: strict typing, Ruff, 100% statement and branch coverage of changed lines.

## 4. Non-goals

- Switching profiles or hosts on one machine; each machine has one recorded configuration (more than one host may be listed on it).
- Copilot cloud agent and Copilot code review on github.com.
- Codex as a coordinating host (Codex stays a reviewer only), unless the user answers Q1 otherwise.
- Validating that a model name exists or that the user's plan or enterprise policy grants it.
- Installing or authenticating Claude Code, Codex or Copilot.
- Editing VS Code user `settings.json`, enterprise-managed settings or organisation policy files.
- Syncing settings between the two machines.
- Translating the skill (`SKILL.md`) into Copilot's skill format; that is separate work.

## 5. Open questions and unverified facts

Questions only the user can answer
- Q1. On the personal machine, is Codex ever the main coding agent, or only the reviewer?
- Q2. At work, which models do you want per role (coordinator, coding, reviewer), and may the reviewer be a different model on the same Copilot host?
- Q3. At work, should setup write a Copilot CLI default model, or do you prefer to pick it per session?
- Q4. Does your enterprise restrict hooks or user instruction files? (VS Code says organisations may restrict hooks.) If so, which gates must still run, and by what means?
- Q5. Do you run the agents from WSL, native Windows, or both on the same machine? If both, should setup write both homes?
- Q6. Will the existing `.claude/settings.json` hooks firing under Copilot be wanted, or should they stay Claude-only?
- Q7. At work, do you need the Codex review step (it would need a Codex licence there), or should review use a Copilot model?

Verified facts (fetched 2026-11-17)
- Copilot CLI reads user instructions from `$HOME/.copilot/copilot-instructions.md` and `$HOME/.copilot/instructions/**/*.instructions.md`, or under `COPILOT_HOME` when set; it also reads repo `AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md`. https://docs.github.com/en/copilot/how-tos/copilot-cli/add-custom-instructions
- VS Code: the Copilot harness's user instructions are `~/.copilot/copilot-instructions.md`; the Claude harness's are `~/.claude/CLAUDE.md`; choosing a Claude model in a Copilot session does not switch harness. https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference and https://code.visualstudio.com/docs/copilot/customization/custom-instructions
- Copilot hooks: repo `.github/hooks/*.json`, user `~/.copilot/hooks/` (or `$COPILOT_HOME/hooks/`), inline in `~/.copilot/settings.json`; repo `.claude/settings.json` and `.claude/settings.local.json` are also read. Event names are lower camelCase (`agentStop`, `preToolUse`, ...); PascalCase `PreToolUse` is accepted with Claude matcher rules. https://docs.github.com/en/copilot/reference/hooks-reference
- VS Code, Copilot CLI and the GitHub Copilot app share the Copilot harness and its hook locations; agent hooks are in preview; Claude and Codex harnesses are disabled when Copilot enterprise-managed settings apply. https://code.visualstudio.com/docs/agent-customization/hooks
- Copilot CLI user settings file is `settings.json` in `~/.copilot` or `$COPILOT_HOME`. https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference
- Copilot CLI takes `--model` and `COPILOT_MODEL`. https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/copilot-cli-reference/cli-programmatic-reference (search snippet only, page not read in full)

Unverified
- U1. The settings key for the Copilot CLI default model, and whether the file is `config.json` or `settings.json` (sources disagree).
- U2. Whether VS Code agent mode has a file-based default model; only the in-editor picker was found.
- U3. Whether Copilot maps Claude's PascalCase `Stop` event in `.claude/settings.json` to `agentStop`, and with what payload, exit-code and timeout semantics.
- U4. Exact model identifiers available to this enterprise seat.
- U5. Whether `COPILOT_HOME` also moves the VS Code Copilot harness's instruction file.

## 6. Risks

- K1. Copilot already reads the repo's `.claude/settings.json`, so current Claude hooks may fire at work with different payloads or failure rules (for example fail-closed `preToolUse` errors) and block work or silently pass. This exists today, before any change.
- K2. Copilot hooks are in preview; event names and payloads may change and break the adapter between setup runs.
- K3. Enterprise policy may disable user hooks or the Claude harness, leaving the Stop gate unenforced at work without the user noticing.
- K4. Copilot reads repo `CLAUDE.md` and `AGENTS.md` too, so instructions written for one host may be applied, with different model names, by the other.
- K5. Wrong home on Windows plus WSL writes the block where the agent never reads it; the setup looks successful and nothing changes.
- K6. Model names in the user instruction block drift from what the host offers, and the agent follows a name it cannot use.
- K7. Detection that guesses wrong could write to the wrong host's files; confirmation (R1, R9) is the mitigation.
