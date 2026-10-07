# python-code-standards

A global `CLAUDE.md` and a Python skill for [Claude Code](https://claude.com/claude-code),
installed once into `~/.claude` and active in every project.

- `CLAUDE.md` — language-agnostic working rules: think first, minimal diffs, verify by
  running, stop-and-ask gates. Loaded in every session.
- `python-code-standards/skill/` — the `python-code-standards` skill: strict typing, a
  variable-declaration rule with its own checker, `uv`, Ruff, Pyright, MyPy, and pytest
  coverage. Loaded when Python work triggers it. See
  [python-code-standards/README.md](python-code-standards/README.md).

Each rule lives in exactly one of the two files, so they can be installed together without
conflict.

## Ask Claude to install

Claude Code can install these standards for you:

1. Open a Claude Code session in any folder.
2. Set the model and effort for your scenario from the table below.
3. Copy the **prompt** for your scenario and paste it into the session.

Each prompt clones this repository to `~/src/python-code-standards`; edit that path in the
prompt if you keep code elsewhere.

| Scenario | Model | Effort | Why this model |
| --- | --- | --- | --- |
| Brand-new install, or replace | Sonnet 5.5 (`/model sonnet`) | medium (`/effort medium`) | Cloning, backing up, and linking follow the README step by step, so the faster, cheaper model is enough. |
| Merge | Opus 5.5 (`/model opus`) | high (`/effort high`) | Telling a real conflict from two wordings of the same rule, and merging without dropping either side's intent, is judgment the stronger model handles more reliably. |

### Scenario 1: brand-new install

Use this when you have no `~/.claude/CLAUDE.md` yet.

- **Prompt** — copy into Claude Code:

  ```text
  Install the python-code-standards from https://github.com/CarlosSolrac/python-code-standards.
  Clone it to ~/src/python-code-standards, then follow its README's Manual Install section to link
  CLAUDE.md into ~/.claude and the skill into ~/.claude/skills/python-code-standards. If
  ~/.claude/CLAUDE.md or that skill folder already exists, stop and ask me. Finish by running
  the README's Verify step and showing me the output.
  ```

### Scenario 2: replace your current CLAUDE.md

Use this to switch to this repository's rules, keeping a backup of yours.

- **Prompt** — copy into Claude Code:

  ```text
  Install the python-code-standards from https://github.com/CarlosSolrac/python-code-standards,
  replacing my current global CLAUDE.md. Clone it to ~/src/python-code-standards. Before
  changing anything, copy ~/.claude/CLAUDE.md to ~/.claude/CLAUDE.md.bak-<today's date> and
  show me that the backup exists. Then delete the original ~/.claude/CLAUDE.md, because a
  link cannot be created over an existing file. Follow the README's Manual Install section to link
  CLAUDE.md and the skill, run the README's Verify step, and show me the output.
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
  a regular file, not a link, and link only the skill. Finish by running the README's Verify
  step and showing me the output.
  ```

A merged `CLAUDE.md` is your own file, so later changes to this repository's `CLAUDE.md` do
not reach it; pull them in by running the merge prompt again. The skill stays linked either
way.

Claude Code asks permission before changing anything in `~/.claude`, even when it is set to
accept edits automatically. Approve those prompts; the install waits on them rather than
stalling.

On Windows, links need Developer Mode or an elevated prompt. Without either, add
"copy instead of linking" to the end of any prompt.

## Set up a new Python project

After [installing](#ask-claude-to-install), open Claude Code in the project's folder, set the
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

To run the script yourself:

- **Commands for each shell:** see
  [Configuring a repository](python-code-standards/README.md#configuring-a-repository-to-follow-the-standards).
- **Options:** see
  [Set up a new repository](python-code-standards/skill/references/setup.md#set-up-a-new-repository).

## Upgrade a project set up earlier

When these standards change, for example a new template or a fixed checker, bring a project
that already uses them up to date.

- **Prompt** — copy into Claude Code, opened in the project's folder:

  ```text
  Upgrade this repository to the current python-code-standards.
  ```

- **Run it yourself:** from the project's folder,

  ```bash
  ~/.claude/skills/python-code-standards/assets/setup-standards.sh -y --update
  ```

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

To do it yourself, from the repository root:

```bash
git status                                  # must be clean
uv run ruff check --fix                     # safe lint fixes
uv run ruff format                          # formatting
uv run ruff check --unsafe-fixes --diff     # preview only; apply a fix once you understand it
git diff                                    # review every change
uv run pytest                               # nothing broke
uv run pre-commit run --all-files           # declarations, Pyright, MyPy: fix what remains by hand
```

Removing an unused import can change behaviour when importing the module has side effects,
so read the diff rather than skimming it. Commit the reformat on its own, so later
`git blame` and reviews can tell it apart from real changes.

## Manual Install

Clone, then link both into `~/.claude`. A symlink keeps one source of truth and picks up
edits immediately.

Linux and macOS:

```bash
git clone https://github.com/CarlosSolrac/python-code-standards.git
cd python-code-standards
mkdir -p ~/.claude/skills
ln -s "$PWD/CLAUDE.md" ~/.claude/CLAUDE.md
ln -s "$PWD/python-code-standards/skill" ~/.claude/skills/python-code-standards
```

Windows, in either shell, needs Developer Mode enabled or an elevated prompt.

PowerShell:

```powershell
git clone https://github.com/CarlosSolrac/python-code-standards.git
Set-Location python-code-standards
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Target "$PWD\CLAUDE.md"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\python-code-standards" -Target "$PWD\python-code-standards\skill"
```

`cmd`:

```cmd
git clone https://github.com/CarlosSolrac/python-code-standards.git
cd /d python-code-standards
mkdir "%USERPROFILE%\.claude\skills"
mklink "%USERPROFILE%\.claude\CLAUDE.md" "%CD%\CLAUDE.md"
mklink /D "%USERPROFILE%\.claude\skills\python-code-standards" "%CD%\python-code-standards\skill"
```

Both Windows forms name the link first and the target second — the reverse of `ln -s`. In
`cmd`, use `cd /d` when the clone is on another drive; plain `cd` does not change drives,
while `Set-Location` handles them. Link the skill *inside* `skills\`; linking `skills\`
itself hides every other skill and stops this one loading, because Claude Code scans
subdirectories for `SKILL.md`.

### Copy instead of link

A copy is pinned and survives this repository moving, but must be refreshed after edits.

```bash
cp CLAUDE.md ~/.claude/CLAUDE.md
cp -r python-code-standards/skill ~/.claude/skills/python-code-standards
```

```powershell
Copy-Item CLAUDE.md "$env:USERPROFILE\.claude\CLAUDE.md"
Copy-Item -Recurse python-code-standards\skill "$env:USERPROFILE\.claude\skills\python-code-standards"
```

```cmd
copy CLAUDE.md "%USERPROFILE%\.claude\CLAUDE.md"
xcopy /E /I python-code-standards\skill "%USERPROFILE%\.claude\skills\python-code-standards"
```

Do not install the skill both personally and per project under the same name; resolution
order between the two scopes is not something to rely on.

### Verify

```bash
ls -l ~/.claude/CLAUDE.md ~/.claude/skills/python-code-standards/SKILL.md
```

```powershell
Get-Item "$env:USERPROFILE\.claude\CLAUDE.md", "$env:USERPROFILE\.claude\skills\python-code-standards\SKILL.md"
```

```cmd
dir "%USERPROFILE%\.claude\CLAUDE.md" "%USERPROFILE%\.claude\skills\python-code-standards\SKILL.md"
```

In a Claude Code session, `/python-code-standards` appears in the skill list.

### Uninstall

Removing a link removes the link, not this repository.

```bash
rm ~/.claude/CLAUDE.md ~/.claude/skills/python-code-standards
```

```powershell
Remove-Item "$env:USERPROFILE\.claude\CLAUDE.md"
Remove-Item "$env:USERPROFILE\.claude\skills\python-code-standards"
```

```cmd
del "%USERPROFILE%\.claude\CLAUDE.md"
rmdir "%USERPROFILE%\.claude\skills\python-code-standards"
```

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
