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

| Scope | Where the choice lives | How it is set |
| --- | --- | --- |
| One session | `--settings`, which the launcher passes | typed per launch |
| One repository | `.claude/settings.json` in the repository | edit a file, once |
| Every repository | `~/.claude/settings.json` | edit a file, once |

The launcher uses the first and leaves the other two neutral, so plain `claude` reaches
Anthropic everywhere and choosing Qwen means typing `bin/ai.sh qwen`. That is the only
arrangement in which both directions stay free.

To make one repository use Qwen without typing anything, copy the `env` block from
[.claude/profiles/qwen.json](.claude/profiles/qwen.json) into a `.claude/settings.json`
beside it — or into `.claude/settings.local.json`, which is ignored by git and so keeps the
choice on one machine. To do the same for every repository, copy that block into
`~/.claude/settings.json` instead. Both are sticky rather than reversible, for the reason
below.

### Keep the user settings file neutral

`~/.claude/settings.json` must not set any `ANTHROPIC_*` variable. Claude Code merges `env`
one key at a time, and a lower-precedence file cannot unset a key a higher one defined —
setting it to `""` breaks the request rather than clearing it. A base URL or auth token
pinned there therefore leaks into Anthropic mode, and no profile or project file can remove
it. Pin the local model in the profile, never in the user settings.

That asymmetry is what makes the two file-based scopes one-way. Once a base URL and auth
token are pinned, reaching Anthropic again needs a profile that supplies its own
`ANTHROPIC_AUTH_TOKEN`, and an auth token takes precedence over the `claude.ai` login — so
it means a metered API key rather than an account subscription. The launcher avoids this by
never pinning anything beyond a single session.

### Prerequisites

Ollama must serve the model named in the profile; it answers the Anthropic Messages API at
`/v1/messages` directly, so no gateway or proxy sits in between. Anthropic mode needs the
machine to be logged in once — run `claude` and `/login` if it reports `Not logged in`. A
WSL install is a separate machine for this purpose and has its own credentials.

Claude Code warns that the Qwen model `isn't described by this version's model catalog` and
assumes a 200k context window. The session still works. Setting
`CLAUDE_CODE_MAX_CONTEXT_TOKENS` in the profile silences it, but the correct value is
whatever `num_ctx` Ollama actually serves, not the window the model advertises.

## Credits

`CLAUDE.md` is based on
https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md.

MIT licence; see [LICENSE](LICENSE).
