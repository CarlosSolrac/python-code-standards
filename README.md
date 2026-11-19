# python-code-standards

A global `CLAUDE.md` and four skills for [Claude Code](https://claude.com/claude-code),
installed once into `~/.claude` and active in every project. The skill guidance is reusable
where supported, but the shipped hook setup targets Claude Code; see
[Agent Skills and Hooks Across Hosts](docs/agent-hooks.md) before adapting it elsewhere.

- `CLAUDE.md` — language-agnostic working rules: think first, minimal diffs, verify by
  running, stop-and-ask gates. Loaded in every session.
- `python-code-standards/skill/` — the `python-code-standards` skill: strict typing, a
  variable-declaration rule with its own checker, `uv`, Ruff, Pyright, MyPy, and pytest
  coverage. Loaded when Python work triggers it. See
  [python-code-standards/README.md](python-code-standards/README.md).
- `design-spec/skill/` — the `design-spec` skill: a sized, diagrammed design spec for a new
  system or an existing project. Loaded when a design or documentation request triggers it.
  See [Design or document a system](#design-or-document-a-system).
- `nightshift/` — the `nightshift` skill: works through the project's TODO and plan files
  overnight, one draft PR per task. Runs only when you type `/nightshift`. See
  [Work through the backlog overnight](#work-through-the-backlog-overnight).
- `prep-nightshift/` — the `prep-nightshift` skill: readies a repository for a nightshift
  run while you are awake. Runs only when you type `/prep-nightshift`. See
  [Work through the backlog overnight](#work-through-the-backlog-overnight).

Each rule lives in exactly one of these five files and folders; where a skill relies on
another's rules, it points to them instead of restating them, so all five can be installed
together without conflict. `nightshift` is the one deliberate override: while it runs, it
logs a decision and carries on wherever another rule says to stop and ask.

`copilot/nightshift/` and `copilot/prep-nightshift/` are the GitHub Copilot CLI versions of
the two nightshift skills, installed into `~/.copilot/skills` instead of the Claude ones. See
[In GitHub Copilot CLI](#in-github-copilot-cli).

## Install

The preferred way to install is to ask an LLM coding agent to do it. Claude Code is shown
below; it clones the repository, backs up what it replaces, links the files, and verifies
the result, stopping to ask wherever a choice is yours. To do it by hand instead, see
[Manual setup](docs/manual-setup.md). For GitHub Copilot CLI, use
[Scenario 4](#scenario-4-github-copilot-cli).

1. Open a Claude Code session in any folder.
2. Set the model and effort for your scenario from the table below.
3. Copy the **prompt** for your scenario and paste it into the session.

Each prompt clones this repository to `~/src/python-code-standards`; edit that path in the
prompt if you keep code elsewhere.

| Scenario | Model | Effort | Why this model |
| --- | --- | --- | --- |
| Brand-new install, or replace | Sonnet 5.5 (`/model sonnet`) | medium (`/effort medium`) | Cloning, backing up, and linking follow the README step by step, so the faster, cheaper model is enough. |
| Merge | Opus 5.5 (`/model opus`) | high (`/effort high`) | Telling a real conflict from two wordings of the same rule, and merging without dropping either side's intent, is judgment the stronger model handles more reliably. |
| GitHub Copilot CLI | Claude Sonnet 5.5 (`/model`) | default | The agent follows numbered steps and stops at each choice. The faster model is sufficient. |

### Scenario 1: brand-new install

Use this when you have no `~/.claude/CLAUDE.md` yet.

- **Prompt** — copy into Claude Code:

  ```text
  Install the python-code-standards from https://github.com/CarlosSolrac/python-code-standards.
  Clone it to ~/src/python-code-standards, then follow docs/manual-setup.md's Install section to link
  CLAUDE.md into ~/.claude and the four skills into ~/.claude/skills. If
  ~/.claude/CLAUDE.md or any of those skill folders already exists, stop and ask me. Finish by running
  the Verify step in docs/manual-setup.md and showing me the output.
  ```

### Scenario 2: replace your current CLAUDE.md

Use this to switch to this repository's rules, keeping a backup of yours.

- **Prompt** — copy into Claude Code:

  ```text
  Install the python-code-standards from https://github.com/CarlosSolrac/python-code-standards,
  replacing my current global CLAUDE.md. Clone it to ~/src/python-code-standards. Before
  changing anything, copy ~/.claude/CLAUDE.md to ~/.claude/CLAUDE.md.bak-<today's date> and
  show me that the backup exists. Then delete the original ~/.claude/CLAUDE.md, because a
  link cannot be created over an existing file. Follow docs/manual-setup.md's Install section to link
  CLAUDE.md and the skills, run its Verify step, and show me the output.
  ```

### Scenario 3: merge with your current CLAUDE.md

Use this to keep your own rules alongside these. Claude asks you about every overlap and
writes nothing until you approve the merged file.

- **Prompt** — copy into Claude Code:

  ```text
  Install the python-code-standards from https://github.com/CarlosSolrac/python-code-standards,
  merging its CLAUDE.md with my current global one. Clone it to ~/src/python-code-standards and
  copy ~/.claude/CLAUDE.md to ~/.claude/CLAUDE.md.bak-<today's date> before changing anything.
  Then go through both files section by section: keep any rule only one file has, and for each
  rule where they overlap or conflict, show me both versions and ask which to keep. Show me the
  complete merged file and wait for my approval before writing it. Write ~/.claude/CLAUDE.md as
  a regular file, not a link, and link only the skills. Finish by running the Verify step
  in docs/manual-setup.md and showing me the output.
  ```

A merged `CLAUDE.md` is your own file, so later changes to this repository's `CLAUDE.md` do
not reach it; pull them in by running the merge prompt again. The skills stay linked either
way.

Claude Code asks permission before changing anything in `~/.claude`, even when it is set to
accept edits automatically. Approve those prompts; the install waits on them rather than
stalling.

On Windows, links need Developer Mode or an elevated prompt. Without either, add
"copy instead of linking" to the end of any prompt.

### Scenario 4: GitHub Copilot CLI

Use this to install the skills, the nightshift hook, and the models block for GitHub
Copilot CLI. Copilot CLI does not read `~/.claude`, so this scenario is separate from
scenarios 1 to 3. Open a Copilot CLI session in any folder.

- **Prompt** — copy into Copilot CLI:

  ```text
  Install the python-code-standards for GitHub Copilot CLI from https://github.com/CarlosSolrac/python-code-standards.
  Clone it to ~/src/python-code-standards. If that folder holds a clone already, use it and run git pull.
  Do the steps in the "Copilot CLI install" section of docs/manual-setup.md, in order.
  At each step that says "stop", stop and ask me. Do not continue until I answer.
  Do not change ~/.claude.
  Finish with the Verify step of that section and show me all of its output.
  ```

## Set up a new Python project

After [installing](#install), open Claude Code in the project's folder, set the
model and effort from the table below, and paste the prompt.

- **Prompt** — copy into Claude Code:

  ```text
  Configure this repository to follow the python-code-standards.
  ```

Claude loads the skill, tells you what its `setup-standards.sh` will change, and runs it once
you approve. The script writes `pyproject.toml`, `.pre-commit-config.yaml`, `.gitattributes`,
`.gitignore`, `.github/workflows/ci.yml`, and `tools/check_declarations.py`, pins Python
3.13, syncs the environment, installs the pre-commit hook, stages every file in the
repository, and checks every file once: Ruff, formatting, the declaration checker, Pyright,
and MyPy. The check is read-only — problems in code you already have are reported, not
fixed, so nothing you wrote changes without your review. It does not run tests or coverage;
those run in CI and whenever you run `uv run pytest`. Claude asks before committing the
result.

The project needs `git` and `uv` on `PATH`, `bash` (Git Bash or WSL on Windows), and a git
repository — in an empty folder, run `git init` first.

Recommended model and effort:

| Project | Model | Effort | Why this model |
| --- | --- | --- | --- |
| New, empty | Sonnet 5.5 (`/model sonnet`) | medium (`/effort medium`) | The script makes every decision, so the session only runs it and reads the output — a faster, cheaper model loses nothing. |
| Existing code | Opus 5.5 (`/model opus`) | high (`/effort high`) | Merging an existing `pyproject.toml` and fixing the violations the first check reports are judgment calls, where the stronger model makes fewer wrong edits. |

To run the script by hand, see [Manual setup](docs/manual-setup.md#set-up-a-project-yourself).

## Upgrade a project set up earlier

When these standards change, for example a new template or a fixed checker, bring a project
that already uses them up to date.

- **Prompt** — copy into Claude Code, opened in the project's folder:

  ```text
  Upgrade this repository to the current python-code-standards.
  ```

- **By hand:** see [Manual setup](docs/manual-setup.md#upgrade-a-project-yourself).
- **What it replaces:** only files and settings the script wrote earlier that nobody has
  edited since. Files you edited are kept and listed. See
  [Upgrade a repository set up earlier](python-code-standards/skill/references/setup.md#upgrade-a-repository-set-up-earlier).
- **Replace files you edited too:** this discards your changes, so ask for it explicitly. See
  [Replace files the user edited](python-code-standards/skill/references/setup.md#replace-files-the-user-edited).
- **Model:** Sonnet 5.5 (`/model sonnet`), medium effort. The script decides what to replace.

## Reformat and fix existing code

Setup only reports problems in code you already have. When you want them fixed, do it as a
separate change, starting from a clean working tree so the result is one reviewable diff.

Ruff fixes two kinds of problem automatically: formatting, and safe lint fixes such as
sorting imports or removing unused ones. Its *unsafe* fixes can change behaviour, so they are
previewed, never applied in bulk. Declaration, Pyright, and MyPy problems have no automatic
fix; each needs a code change.

| Task | Model | Effort | Why this model |
| --- | --- | --- | --- |
| Reformat and safe fixes only | Sonnet 5.5 (`/model sonnet`) | medium (`/effort medium`) | Ruff makes every edit; the session runs it, runs the tests, and summarises the diff. |
| Also fix what Ruff cannot | Opus 5.5 (`/model opus`) | high (`/effort high`) | Annotating variables and resolving type errors across existing code means reading intent, where the stronger model makes fewer wrong edits. |

- **Prompt** — copy into Claude Code:

  ```text
  Reformat this repository and apply the python-code-standards fixes. First check that the
  working tree is clean, and stop if it is not. Run Ruff's safe fixes and the formatter over
  the whole repository, run the tests, and show me a summary of the diff. List any unsafe
  fixes Ruff suggests without applying them, and list the declaration, Pyright, and MyPy
  problems that remain. Do not fix those, and do not commit, until I approve.
  ```

To do it by hand, see [Manual setup](docs/manual-setup.md#reformat-and-fix-existing-code-yourself).

Removing an unused import can change behaviour when importing the module has side effects,
so read the diff rather than skimming it. Commit the reformat on its own, so later
`git blame` and reviews can tell it apart from real changes.

## Design or document a system

The `design-spec` skill, in `design-spec/skill/`, produces a sized, diagrammed design spec
in `docs/design.md`. Claude loads it when a request designs a new system or documents an
existing one; see [design-spec/skill/SKILL.md](design-spec/skill/SKILL.md).

- **Two modes.** *Design mode*, for a new system or a restructure, models the domain first,
  writes the spec, and stops for your approval before writing any code. *Document mode*,
  for an existing project, derives the spec from the code, marks what it inferred, lists
  deviations from the skill's design rules as findings, and changes no code. Ask for one
  ("Design a pipeline that ...") or the other ("Document the design of this repository",
  "Resync the design").
- **Size gate.** The first line of the answer states the mode and a size class, and the
  class decides how much gets written:

  | Size | When | What is written |
  | --- | --- | --- |
  | Small | At most two layers and under ~150 lines, or (design mode only) an existing ADR already forces the answer | Design mode: no spec, code written directly. Document mode: a five-line summary and the component flowchart. |
  | Standard | Three or more layers, or over ~150 lines, in one process | The full spec; a context view (a flowchart with the system boundary as a subgraph) only when the process touches two or more external systems. |
  | Large | Multiple processes or services | The full spec with context and container views. |

- **Templates.** For a Standard data pipeline, the default pattern comes from the project
  templates listed in
  [template-0-summaries](https://github.com/CarlosSolrac/template-0-summaries); each
  template's `docs/design.md` is the worked example. A project that already has a pattern
  keeps it and records the difference in an ADR.
- **Diagram checker.** Before showing a spec, the skill checks every Mermaid diagram in it
  with Mermaid's own parser, using
  [design-spec/skill/tools/validate_mermaid.mjs](design-spec/skill/tools/validate_mermaid.mjs).
  The checker needs Node 22.22.2+ or 24.15+, with `npm`, on `PATH`. Its first run installs
  pinned `mermaid` and `jsdom` into `~/.cache/design-spec-mermaid`, which needs network once;
  the project gains no npm files. To run it yourself (exit 0 means every diagram parses):

  ```bash
  node ~/.claude/skills/design-spec/tools/validate_mermaid.mjs docs/design.md
  ```

- **Diagram viewer.** The spec keeps its Mermaid blocks. The skill also writes one HTML page
  per spec, `docs/design_images/design.html`, with an anchor for each diagram. It adds an
  "Open diagram in browser" link after each block, using
  [design-spec/skill/tools/render_diagrams.mjs](design-spec/skill/tools/render_diagrams.mjs).
  `--check` exits 1 when the page or a link is stale. The page loads a pinned Mermaid from a
  CDN, so it needs network. github.com shows HTML as source, so open the page from a local
  copy.
## Work through the backlog overnight

The `nightshift` skill, in `nightshift/`, works unattended through the current project's
TODO and plan files overnight — `TODO.md`, `docs/plans/`, `PLAN.md`, `ROADMAP.md`, and open
GitHub issues assigned to you — one task at a time, each on its own branch and worktree,
ending in one draft PR per task. See [nightshift/SKILL.md](nightshift/SKILL.md).

- **Preparing for it.** Type `/prep-nightshift` while you are awake: it checks that the
  night can run unattended, confirms tonight's scope with you, commits the inputs the tasks
  need as a plan file once you approve, and lists the steps left for the morning. See
  [prep-nightshift/SKILL.md](prep-nightshift/SKILL.md).
- **Starting it.** Only you start it, by typing `/nightshift`; Claude never invokes it on its
  own. `/nightshift adversarial=thorough` fixes every defect the adversarial review finds
  and repeats that review until it approves, up to three rounds, instead of running it once
  per task. Run it in a session whose permission mode will not stop for prompts (auto mode,
  or an allowlist covering `git`, `gh`, the project's tools and file edits), and leave the
  session open: a watchdog scheduled in it restarts the work if a turn ends early, and dies
  with the session.
- **Permission prompts.** Some prompts appear in any mode, such as a hook's `ask`, and one
  unanswered prompt would stall the night. Install `nightshift/hooks/deny-unattended.sh`
  as a user hook (see [Nightshift's permission hook](docs/manual-setup.md#nightshifts-permission-hook)): it denies every prompt in the nightshift session
  and its subagents while the night runs, so the call ends as a blocker for the morning.
  Other sessions, even in the same repository, keep their prompts.
- **What it may do alone.** Create task branches and worktrees, commit, push those branches,
  open draft PRs, and delete or move files and write schema migrations on a task branch. Everything it does is undone by
  closing a PR and deleting a branch. It never pushes to or merges into the default branch,
  merges a PR, force-pushes, deploys, or acts outside the repository, and it never changes
  dependencies, CI, hooks, or build configuration: a task that needs one ends blocked, with
  the exact change listed for you.
- **Reviews.** Codex reviews every unit and every finished task, then challenges each task's
  approach in an adversarial review. This needs the Codex plugin for Claude Code; while
  Codex is unavailable the work goes on and the reviews wait, listed as pending; meanwhile
  Claude's built-in `/code-review` checks each unit, without replacing the missed Codex
  review.
- **Needs.** A git repository; `gh` logged in to push and open PRs, or the branches stay
  local.
- **In the morning.** Open `.nightshift/LOG-<date>.md` in the repository root and read
  *Morning summary* and *Needs you* first. The log records every decision it made alone,
  with the options, the pros and cons of each, and how to reverse it, and every blocker with
  what it needs from you. Then close the nightshift session and start a fresh one for
  daytime work.

### In GitHub Copilot CLI

`copilot/nightshift/` and `copilot/prep-nightshift/` reach the same goals in Copilot CLI,
with the same authority, log and morning deliverable. They differ in how the host runs the
night:

- **Starting it.** Start the session with
  `copilot --autopilot --allow-all --max-autopilot-continues 200`, then type `/nightshift`.
  Autopilot denies any call that would still prompt, so the call ends as a blocker.
- **Keeping it going.** `copilot/nightshift/hooks/nightshift-hook.ps1`, installed as
  `~/.copilot/hooks/nightshift.json` (see
  [Copilot CLI nightshift](docs/manual-setup.md#copilot-cli-nightshift)), blocks the
  session's `agentStop` while its log is open, so a turn that ends early starts again, and
  logs any permission prompt. It needs PowerShell (5.1 or 7) and git.
- **Reviews.** Every review runs on the Copilot review model from the `## Models (Copilot)`
  block (default GPT-6 Astra), never the Codex plugin. `adversarial=thorough` runs a deep
  review with GPT-6 Astra, gpt-6.1-sol, gpt-5.3-codex, gemini-4-argon, grok-4.7 and
  mai-code-2, consolidated, up to three rounds.
- **Limits.** Copilot ends a turn after eight consecutive `agentStop` blocks, and MCP input
  or consent requests wait for an answer even in autopilot, so prep checks the MCP servers.
  `--allow-all` replaces the Claude hook's deny-all: the authority boundary is kept by the
  skill, not enforced by the host.

## Switching between local Qwen and Anthropic

`bin/ai.sh` and `bin/ai.ps1` launch Claude Code against either the local Qwen model or
Anthropic, from the same clone.

```bash
bin/ai.sh qwen              # local Qwen, served by Ollama
bin/ai.sh claude --resume   # Anthropic; extra arguments pass straight through
```

```powershell
bin\ai.ps1 qwen
bin\ai.ps1 claude --resume
```

Anthropic mode is the plain `claude` command with no environment overrides, so it keeps
whatever authentication the account already has. Qwen mode applies
[.claude/profiles/qwen.json](.claude/profiles/qwen.json) with `--settings`, which outranks
both the user and the project settings files. The launcher checks that Ollama is answering
before starting a session, so a stopped container fails immediately instead of at the first
prompt.

### Choosing the scope

Three places can decide which model a session uses. Claude Code applies them in this order,
highest first, merging `env` one key at a time:

| Scope | Where the choice lives | Command |
| --- | --- | --- |
| One session | `--settings`, which the launcher passes | `bin/ai.sh qwen` |
| One repository | `.claude/settings.json` in the repository | `bin/set-model.sh qwen repo` |
| One repository, this machine only | `.claude/settings.local.json`, ignored by git | `bin/set-model.sh qwen local` |
| Every repository on this machine | `~/.claude/settings.json` | `bin/set-model.sh qwen global` |

The launcher uses the first and leaves the others neutral, so plain `claude` reaches
Anthropic everywhere and choosing Qwen means typing `bin/ai.sh qwen` each time.

`bin/set-model.sh` (`bin\set-model.ps1` on Windows) makes the other three automatic: it
writes the `env` block from the profile into the chosen file, and `claude` in place of
`qwen` removes exactly those keys again. Every other key in the file — `model`, `theme`,
`enabledPlugins` — is left as it was; unpinning a file that held nothing else deletes it
rather than leaving an empty stub; and the global file is copied to `settings.json.bak`
before each write. Both scripts embed the same Python, so the two platforms write
byte-identical JSON. Only the launcher checks that Ollama is up — a pinned scope fails at
the first prompt if it is not.

```bash
bin/set-model.sh qwen global     # every repository on this machine
bin/set-model.sh claude global   # back to Anthropic
```

```powershell
bin\set-model.ps1 qwen repo
bin\set-model.ps1 claude repo
```

### Keep the user settings file neutral

`~/.claude/settings.json` must not set any `ANTHROPIC_*` variable. Claude Code merges `env`
one key at a time, and a lower-precedence file cannot unset a key a higher one defined —
setting it to `""` breaks the request rather than clearing it. A base URL or auth token
pinned there therefore leaks into Anthropic mode, and no profile or project file can remove
it. Change that file only through `bin/set-model.sh`, which can undo exactly what it did.

That asymmetry is why a pinned file cannot be overridden from below. Once a base URL and
auth token are set in it, reaching Anthropic by overriding would need a profile that
supplies its own `ANTHROPIC_AUTH_TOKEN`, and an auth token takes precedence over the
`claude.ai` login — a metered API key rather than an account subscription. The launcher
never pins anything beyond a single session, and `bin/set-model.sh claude` reverses a pin
by editing the file instead.

### Prerequisites

Ollama must serve the model named in the profile; it answers the Anthropic Messages API at
`/v1/messages` directly, so no gateway or proxy sits in between. Anthropic mode needs the
machine to be logged in once — run `claude` and `/login` if it reports `Not logged in`. A
WSL install is a separate machine for this purpose and has its own credentials.

The profile sets `CLAUDE_CODE_MAX_CONTEXT_TOKENS` so Claude Code knows the real context
window; without it, it assumes 200k and says so on every launch. Keep the value equal to
the `context_length` that `GET /api/ps` on Ollama reports while the model is loaded — that
is what Ollama enforces, not the larger window the model file advertises. Two shorter
notices remain in Qwen mode and are harmless: a `[claude-code:unrecognized_model]` line,
because the model is not in Claude Code's catalog, and a note that claude.ai connectors
are disabled while an auth token is set.

## Credits

`CLAUDE.md` is based on
https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md.

MIT licence; see [LICENSE](LICENSE).
