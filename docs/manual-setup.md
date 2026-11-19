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

The `review-standards` skill is for the code reviewer, not for the agent that writes code.
`setup-standards.sh` installs it in the folder of the review provider that you select. See
[Installed skills](../python-code-standards/skill/references/setup.md#installed-skills).

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

## Copilot CLI install

Use this section to install the standards for GitHub Copilot CLI. The steps are for an LLM
agent to execute. Do the steps in order, from the root of the clone. When a step says
"stop", stop and ask the user. Do not continue until the user answers.

Copilot CLI does not read `~/.claude`. It reads these items from its own folder:

| Item | Path in the Copilot folder |
| --- | --- |
| Skills | `skills/<name>/SKILL.md` |
| Hooks | `hooks/*.json` |
| Personal instructions | `copilot-instructions.md` |

The Copilot folder is `$COPILOT_HOME` when that variable has a value. Otherwise it is
`~/.copilot`.

Prerequisites:

- `git`.
- Windows: PowerShell 5.1 or 7. macOS and Linux: `bash`, and PowerShell 7 (`pwsh`) for the
  nightshift hook.
- Node 22.22.2+ or 24.15+, with `npm` on `PATH`, for the `design-spec` diagram tools.
- `uv`, for the projects that use the `python-code-standards` skill.

### 1. Find the Copilot folder

PowerShell (Windows):

```powershell
$CopilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { "$env:USERPROFILE\.copilot" }
```

bash (macOS and Linux):

```bash
COPILOT_DIR="${COPILOT_HOME:-$HOME/.copilot}"
```

Use the same shell for all steps. A new shell does not keep the variable.

### 2. Find existing skills

Install these five skills. Each one is a link from the Copilot folder to a folder in the
clone.

| Skill | Folder in the clone |
| --- | --- |
| `python-code-standards` | `python-code-standards/skill` |
| `design-spec` | `design-spec/skill` |
| `review-standards` | `review-standards` |
| `nightshift` | `copilot/nightshift` |
| `prep-nightshift` | `copilot/prep-nightshift` |

The two nightshift skills come from `copilot/`. Do not use the Claude Code versions in the
root `nightshift/` and `prep-nightshift/` folders.

For each skill, examine `skills/<skill>` in the Copilot folder:

- The path does not exist. Continue.
- The path is a link to the folder in the table. Continue. Step 3 does not change it.
- The path is a different link, a folder, or a file. Stop. Show the user the path and its
  target or contents. Ask the user to keep it or to replace it.

### 3. Link the skills

On Windows, a junction needs no Developer Mode and no administrator rights. The commands
do not change a path that exists.

PowerShell (Windows):

```powershell
$Skills = [ordered]@{
    'python-code-standards' = 'python-code-standards\skill'
    'design-spec'           = 'design-spec\skill'
    'review-standards'      = 'review-standards'
    'nightshift'            = 'copilot\nightshift'
    'prep-nightshift'       = 'copilot\prep-nightshift'
}
New-Item -ItemType Directory -Force "$CopilotHome\skills" | Out-Null
foreach ($Name in $Skills.Keys) {
    if (-not (Test-Path "$CopilotHome\skills\$Name")) {
        New-Item -ItemType Junction -Path "$CopilotHome\skills\$Name" -Target "$PWD\$($Skills[$Name])" | Out-Null
    }
}
```

bash (macOS and Linux):

```bash
mkdir -p "$COPILOT_DIR/skills"
for pair in python-code-standards:python-code-standards/skill design-spec:design-spec/skill \
    review-standards:review-standards nightshift:copilot/nightshift prep-nightshift:copilot/prep-nightshift; do
    name="${pair%%:*}"
    [ -e "$COPILOT_DIR/skills/$name" ] || ln -s "$PWD/${pair#*:}" "$COPILOT_DIR/skills/$name"
done
```

### 4. Install the nightshift hook

Compare `hooks/nightshift.json` in the Copilot folder with
`copilot/nightshift/hooks/nightshift.json` in the clone:

- The file does not exist, or the two files are equal. Copy the file with the commands
  below.
- The two files are different. Stop. Show the user the difference. Ask the user to keep the
  installed file or to replace it.

PowerShell (Windows):

```powershell
New-Item -ItemType Directory -Force "$CopilotHome\hooks" | Out-Null
Copy-Item copilot\nightshift\hooks\nightshift.json "$CopilotHome\hooks\nightshift.json"
```

bash (macOS and Linux):

```bash
mkdir -p "$COPILOT_DIR/hooks"
cp copilot/nightshift/hooks/nightshift.json "$COPILOT_DIR/hooks/nightshift.json"
```

### 5. Add the models block

The models block tells Copilot which model to use for each role. In
`copilot/copilot-instructions.md`, the block starts at the line
`<!-- python-code-standards:models -->`. It ends at the line
`<!-- /python-code-standards:models -->`. The block includes the two marker lines. Do not
copy the `# Copilot instructions` heading above the block.

Read `copilot-instructions.md` in the Copilot folder. Then do the first row that applies:

| The installed file | Action |
| --- | --- |
| Does not exist | Create the file. Write the block as its only content. |
| Has a start marker without one end marker after it, or has two or more blocks | Stop. Tell the user that the markers are not valid. Do not change the file. |
| Has no start marker | Add one empty line and the block at the end of the file. Do not change the other text. |
| Has a block that is equal to the block in the clone | Make no change. |
| Has a different block | Stop. Show the user the two blocks. Ask which model lines to keep. Write the block that the user approves. |

The last line before the end marker is the guard line. The guard line tells Copilot not to
open the instruction files of other agents. Keep the guard line in every block that you
write.

### 6. Verify

Run these commands. Show the user all of the output.

```bash
copilot skill list
copilot instruction list
```

Make sure that the output agrees with these statements:

- `copilot skill list` shows the five skills under "Personal skills".
- `copilot instruction list` shows `copilot-instructions.md` from the Copilot folder under
  "Personal instructions".

Then run the hook tests from the root of the clone:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File copilot\nightshift\hooks\test-nightshift-hook.ps1
```

```bash
pwsh -NoProfile -File copilot/nightshift/hooks/test-nightshift-hook.ps1
```

The last line of the output is `all passed`.

### Uninstall

Do these steps only when the user asks you to uninstall. They are not part of the install.

Remove only the links that point to the clone, and the hook only when it is equal to the
hook in the clone. Removing a link does not remove the clone. Run the commands from the root
of the clone, in the shell from step 1.

PowerShell (Windows). `Directory.Delete` without recursion removes the junction only:

```powershell
$Clone = (Get-Location).Path
foreach ($Name in 'python-code-standards', 'design-spec', 'review-standards', 'nightshift', 'prep-nightshift') {
    $Link = Get-Item "$CopilotHome\skills\$Name" -Force -ErrorAction SilentlyContinue
    if ($Link.LinkType -and "$($Link.Target)".StartsWith("$Clone\", [StringComparison]::OrdinalIgnoreCase)) {
        [System.IO.Directory]::Delete($Link.FullName)
    }
}
$Hook = "$CopilotHome\hooks\nightshift.json"
if ((Test-Path $Hook) -and (Get-FileHash $Hook).Hash -eq (Get-FileHash copilot\nightshift\hooks\nightshift.json).Hash) {
    Remove-Item $Hook
}
```

bash (macOS and Linux):

```bash
for name in python-code-standards design-spec review-standards nightshift prep-nightshift; do
    case "$(readlink "$COPILOT_DIR/skills/$name")" in
        "$PWD"/*) rm "$COPILOT_DIR/skills/$name" ;;
    esac
done
if cmp -s copilot/nightshift/hooks/nightshift.json "$COPILOT_DIR/hooks/nightshift.json"; then
    rm "$COPILOT_DIR/hooks/nightshift.json"
fi
```

Then remove the models block from `copilot-instructions.md` in the Copilot folder. Remove
the lines from the start marker to the end marker. Do not change the other text.

### Copilot CLI nightshift

Steps 3 and 4 install the two nightshift skills and their hook. The hook does nothing
outside a running nightshift session. On macOS and Linux, the hook runs through `pwsh`. To
use a different model for a role, edit that line in the installed models block. See
[In GitHub Copilot CLI](../README.md#in-github-copilot-cli) for how a night runs.

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
