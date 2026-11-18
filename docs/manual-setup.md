# Manual setup

Install and set up the standards by hand. The recommended way is to ask an LLM coding agent
to do it; see [Install](../README.md#install) in the README. Use this page when you cannot,
or want to see exactly what each step does.

## Install

Clone, then link `CLAUDE.md` and the four skills into `~/.claude`. A symlink keeps one
source of truth and picks up edits immediately.

Linux and macOS:

```bash
git clone https://github.com/CarlosSolrac/python-code-standards.git
cd python-code-standards
mkdir -p ~/.claude/skills
ln -s "$PWD/CLAUDE.md" ~/.claude/CLAUDE.md
ln -s "$PWD/python-code-standards/skill" ~/.claude/skills/python-code-standards
ln -s "$PWD/design-spec/skill" ~/.claude/skills/design-spec
ln -s "$PWD/nightshift" ~/.claude/skills/nightshift
ln -s "$PWD/prep-nightshift" ~/.claude/skills/prep-nightshift
```

Windows, in either shell, needs Developer Mode enabled or an elevated prompt.

PowerShell:

```powershell
git clone https://github.com/CarlosSolrac/python-code-standards.git
Set-Location python-code-standards
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Target "$PWD\CLAUDE.md"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\python-code-standards" -Target "$PWD\python-code-standards\skill"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\design-spec" -Target "$PWD\design-spec\skill"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\nightshift" -Target "$PWD\nightshift"
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\prep-nightshift" -Target "$PWD\prep-nightshift"
```

`cmd`:

```cmd
git clone https://github.com/CarlosSolrac/python-code-standards.git
cd /d python-code-standards
mkdir "%USERPROFILE%\.claude\skills"
mklink "%USERPROFILE%\.claude\CLAUDE.md" "%CD%\CLAUDE.md"
mklink /D "%USERPROFILE%\.claude\skills\python-code-standards" "%CD%\python-code-standards\skill"
mklink /D "%USERPROFILE%\.claude\skills\design-spec" "%CD%\design-spec\skill"
mklink /D "%USERPROFILE%\.claude\skills\nightshift" "%CD%\nightshift"
mklink /D "%USERPROFILE%\.claude\skills\prep-nightshift" "%CD%\prep-nightshift"
```

Both Windows forms name the link first and the target second — the reverse of `ln -s`. In
`cmd`, use `cd /d` when the clone is on another drive; plain `cd` does not change drives,
while `Set-Location` handles them. Link each skill *inside* `skills\`; linking `skills\`
itself hides every other skill and stops these loading, because Claude Code scans
subdirectories for `SKILL.md`.

## Nightshift's permission hook

Merge this into `~/.claude/settings.json`, keeping any hooks already there. It needs
`bash` and `git`, and is untested on Windows.

```json
{
  "hooks": {
    "PermissionRequest": [
      {"hooks": [{"type": "command", "command": "bash ~/.claude/skills/nightshift/hooks/deny-unattended.sh"}]}
    ],
    "Notification": [
      {"matcher": "permission_prompt",
       "hooks": [{"type": "command", "command": "bash ~/.claude/skills/nightshift/hooks/deny-unattended.sh"}]}
    ]
  }
}
```

It does nothing outside a running nightshift session, so it can stay installed.

## Copilot CLI nightshift

Copilot CLI reads skills from `~/.copilot/skills` and hooks from `~/.copilot/hooks`, not
from `~/.claude`. Link the Copilot versions of the two nightshift skills, from the
repository root, and install the hook:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.copilot\skills", "$env:USERPROFILE\.copilot\hooks" | Out-Null
New-Item -ItemType Junction -Path "$env:USERPROFILE\.copilot\skills\nightshift" -Target "$PWD\copilot\nightshift"
New-Item -ItemType Junction -Path "$env:USERPROFILE\.copilot\skills\prep-nightshift" -Target "$PWD\copilot\prep-nightshift"
Copy-Item copilot\nightshift\hooks\nightshift.json "$env:USERPROFILE\.copilot\hooks\nightshift.json"
```

```bash
mkdir -p ~/.copilot/skills ~/.copilot/hooks
ln -s "$PWD/copilot/nightshift" ~/.copilot/skills/nightshift
ln -s "$PWD/copilot/prep-nightshift" ~/.copilot/skills/prep-nightshift
cp copilot/nightshift/hooks/nightshift.json ~/.copilot/hooks/
```

On macOS and Linux the hook runs through `pwsh`, so install PowerShell 7. Append the
`## Models (Copilot)` block from `copilot/copilot-instructions.md` to
`~/.copilot/copilot-instructions.md` to choose other models. Like the Claude hook, it does
nothing outside a running nightshift session. Check the tests with
`pwsh -NoProfile -File copilot/nightshift/hooks/test-nightshift-hook.ps1`.

## Copy instead of link

A copy is pinned and survives this repository moving, but must be refreshed after edits.

```bash
cp CLAUDE.md ~/.claude/CLAUDE.md
cp -r python-code-standards/skill ~/.claude/skills/python-code-standards
cp -r design-spec/skill ~/.claude/skills/design-spec
cp -r nightshift ~/.claude/skills/nightshift
cp -r prep-nightshift ~/.claude/skills/prep-nightshift
```

```powershell
Copy-Item CLAUDE.md "$env:USERPROFILE\.claude\CLAUDE.md"
Copy-Item -Recurse python-code-standards\skill "$env:USERPROFILE\.claude\skills\python-code-standards"
Copy-Item -Recurse design-spec\skill "$env:USERPROFILE\.claude\skills\design-spec"
Copy-Item -Recurse nightshift "$env:USERPROFILE\.claude\skills\nightshift"
Copy-Item -Recurse prep-nightshift "$env:USERPROFILE\.claude\skills\prep-nightshift"
```

```cmd
copy CLAUDE.md "%USERPROFILE%\.claude\CLAUDE.md"
xcopy /E /I python-code-standards\skill "%USERPROFILE%\.claude\skills\python-code-standards"
xcopy /E /I design-spec\skill "%USERPROFILE%\.claude\skills\design-spec"
xcopy /E /I nightshift "%USERPROFILE%\.claude\skills\nightshift"
xcopy /E /I prep-nightshift "%USERPROFILE%\.claude\skills\prep-nightshift"
```

Do not install the skill both personally and per project under the same name; resolution
order between the two scopes is not something to rely on.

## Verify

```bash
ls -l ~/.claude/CLAUDE.md ~/.claude/skills/python-code-standards/SKILL.md ~/.claude/skills/design-spec/SKILL.md ~/.claude/skills/nightshift/SKILL.md ~/.claude/skills/prep-nightshift/SKILL.md
```

```powershell
Get-Item "$env:USERPROFILE\.claude\CLAUDE.md", "$env:USERPROFILE\.claude\skills\python-code-standards\SKILL.md", "$env:USERPROFILE\.claude\skills\design-spec\SKILL.md", "$env:USERPROFILE\.claude\skills\nightshift\SKILL.md", "$env:USERPROFILE\.claude\skills\prep-nightshift\SKILL.md"
```

```cmd
dir "%USERPROFILE%\.claude\CLAUDE.md" "%USERPROFILE%\.claude\skills\python-code-standards\SKILL.md" "%USERPROFILE%\.claude\skills\design-spec\SKILL.md" "%USERPROFILE%\.claude\skills\nightshift\SKILL.md" "%USERPROFILE%\.claude\skills\prep-nightshift\SKILL.md"
```

In a Claude Code session, `/python-code-standards`, `/design-spec`, `/nightshift` and
`/prep-nightshift` appear in the skill list.

## Uninstall

Removing a link removes the link, not this repository.

```bash
rm ~/.claude/CLAUDE.md ~/.claude/skills/python-code-standards
rm ~/.claude/skills/design-spec ~/.claude/skills/nightshift ~/.claude/skills/prep-nightshift
```

```powershell
Remove-Item "$env:USERPROFILE\.claude\CLAUDE.md"
Remove-Item "$env:USERPROFILE\.claude\skills\python-code-standards"
Remove-Item "$env:USERPROFILE\.claude\skills\design-spec"
Remove-Item "$env:USERPROFILE\.claude\skills\nightshift"
Remove-Item "$env:USERPROFILE\.claude\skills\prep-nightshift"
```

```cmd
del "%USERPROFILE%\.claude\CLAUDE.md"
rmdir "%USERPROFILE%\.claude\skills\python-code-standards"
rmdir "%USERPROFILE%\.claude\skills\design-spec"
rmdir "%USERPROFILE%\.claude\skills\nightshift"
rmdir "%USERPROFILE%\.claude\skills\prep-nightshift"
```

## Set up a project yourself

- **Commands for each shell:** see
  [Configuring a repository](../python-code-standards/README.md#configuring-a-repository-to-follow-the-standards).
- **Options:** see
  [Set up a new repository](../python-code-standards/skill/references/setup.md#set-up-a-new-repository).

## Upgrade a project yourself

From the project's folder:

```bash
~/src/python-code-standards/python-code-standards/setup/setup-standards.sh -y --update
```

## Reformat and fix existing code yourself

From the repository root:

```bash
git status                                  # must be clean
uv run ruff check --fix                     # safe lint fixes
uv run ruff format                          # formatting
uv run ruff check --unsafe-fixes --diff     # preview only; apply a fix once you understand it
git diff                                    # review every change
uv run pytest                               # nothing broke
uv run pre-commit run --all-files           # declarations, Pyright, MyPy: fix what remains by hand
```
