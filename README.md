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

## Install

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
