# Host instruction-loading verification, 2026-11-17

Sources are official docs only, all retrieved 2026-11-17. developers.openai.com/codex/* pages
308-redirect to learn.chatgpt.com/docs/*; the redirect target is cited. Quotes are as returned by
the fetch tool; a few long sentences were truncated by it (marked "...").

## 1. Codex CLI instruction files

| Claim | Status | Quote | URL |
|---|---|---|---|
| Loads `AGENTS.md` automatically | verified | "Codex reads `AGENTS.md` files before doing any work." | https://learn.chatgpt.com/docs/agent-configuration/agents-md |
| Global file in Codex home, override first | verified | "In your Codex home directory (defaults to `~/.codex`, unless you set `CODEX_HOME`), Codex reads ..." then "Codex reads `AGENTS.override.md` if it exists. Otherwise, Codex reads `AGENTS.md`." | same |
| Project hierarchy root to cwd | verified | "Starting at the project root (typically the Git root), Codex walks down to your current working directory." / "In each directory along the path, it checks for `AGENTS.override.md`, then `AGENTS.md`, then any fallback names" / "Codex includes at most one file per directory." | same |
| Closer files win by order | verified | "Codex concatenates files from the root down, joining them with blank lines." / "Files closer to your current directory override earlier guidance because they appear later in the combined prompt." | same |
| Size limit | verified | "Codex skips empty files and stops adding files once the combined size reaches the limit defined by `project_doc_max_bytes` (32 KiB by default)" | same |
| Built once per run | verified | "when it starts (once per run; in the TUI this usually means once per launched session)" | same |
| Other filenames only via fallback list | verified | "Filenames not on this list are ignored for instruction discovery." Example: `project_doc_fallback_filenames = ["TEAM_GUIDE.md", ".agents.md"]` | same |
| Loads `CLAUDE.md`, `.claude/`, `.github/copilot-instructions.md` | not found | Page mentions none of them; by the rule above they are ignored unless added to `project_doc_fallback_filenames`. | same |
| Home dir `~/.codex`, moved by `CODEX_HOME` | verified | "defaults to `~/.codex`, unless you set `CODEX_HOME`" | same |

## 2. Codex skills and custom prompts

| Claim | Status | Quote | URL |
|---|---|---|---|
| Skill locations | verified | Lists `$CWD/.agents/skills`, `$CWD/../.agents/skills`, `$REPO_ROOT/.agents/skills`, `$HOME/.agents/skills`, `/etc/codex/skills`, bundled system skills. `~/.codex/skills` is not listed. | https://learn.chatgpt.com/docs/build-skills |
| Discovery | verified | "scans `.agents/skills` in every directory from your current working directory up to the repository root." | same |
| Body loaded on demand | verified | Codex "start[s] with each skill's name and description" and "load[s] the full `SKILL.md` instructions when they decide to use that skill." Initial list budget: 2% of context window by default. | same |
| Invocation | verified | Explicit (named in prompt) or implicit (task matches `description`). | same |
| Custom prompts deprecated | verified | "Custom prompts are deprecated. Use skills for reusable instructions that Codex can invoke explicitly or implicitly." | https://learn.chatgpt.com/docs/custom-prompts |
| Custom prompt location and loading | verified | Prompts "live in your local Codex home directory (for example, `~/.codex`)", files in `~/.codex/prompts/` (top level only), invoked as `/prompts:<name>`; read when a session starts. | same |
| Prompts removed in a specific CLI version | not found (official docs) | Only GitHub issues (openai/codex #15941) report removal in 0.117.0; not documented. | https://github.com/openai/codex/issues/15941 |

## 3. GitHub Copilot (VS Code agent mode, Copilot CLI)

| Claim | Status | Quote | URL |
|---|---|---|---|
| Path-scoped instructions, CLI | verified | "Path-specific instructions are included only when their `applyTo` value matches a file that Copilot CLI is working with." Location `.github/instructions/**/*.instructions.md`. | https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions |
| Path-scoped instructions, VS Code | verified | "An `.instructions.md` file uses `applyTo`, or a Claude rules file uses `paths`, to match files the agent works with." | https://code.visualstudio.com/docs/copilot/customization/custom-instructions |
| User-level instruction folder, CLI | verified | "`$HOME/.copilot/copilot-instructions.md`" and "`$HOME/.copilot/instructions/**/*.instructions.md`"; `COPILOT_HOME` replaces `$HOME/.copilot`. | CLI URL above |
| User-level instruction folder, VS Code | verified (Copilot harness) | "`~/.copilot/copilot-instructions.md` for general guidance; `~/.copilot/instructions/**/*.instructions.md` for modular instructions" | https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference |
| CLI reads `AGENTS.md`, `CLAUDE.md` | verified | Lists `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` as agent instruction files; "Copilot CLI also uses `.claude/CLAUDE.md`." | CLI URL above |
| VS Code reads `CLAUDE.md` | partly | Per harness: Copilot harness reads `.github/copilot-instructions.md` or `AGENTS.md`; Local harness also reads `CLAUDE.md` (setting `chat.useClaudeMdFile`: "Include Claude instruction files"). "The harness determines which instruction files it reads." | VS Code reference URL above |
| `copilot-instructions.md` applied to every request | partly | Listed as project instructions file; docs say "Inclusion means its contents become part of a request" but not "every request" verbatim. | same |
| Skills supported, surfaces | verified | Lists "GitHub Copilot CLI.", "Copilot cloud agent and Copilot code review on GitHub.com.", "Agent mode in Visual Studio Code, Visual Studio, and JetBrains IDEs." | https://docs.github.com/en/copilot/concepts/agents/about-agent-skills |
| Skill directories | verified | Project: "`.github/skills`, `.claude/skills`, or `.agents/skills`"; personal: "`~/.copilot/skills` or `~/.agents/skills`". `~/.claude/skills` not listed for CLI. | https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills |
| VS Code skill directories | verified | Copilot `.github/skills/` + `~/.copilot/skills/`; Claude `.claude/skills/` + `~/.claude/skills/`; Codex `.agents/skills/` + `~/.agents/skills/`; table is "not every directory it recognizes". | https://code.visualstudio.com/docs/copilot/customization/agent-skills |
| Skill bodies on demand | verified | CLI: "When Copilot chooses to use a skill, the `SKILL.md` file will be injected in the agent's context." VS Code: "Skills load content progressively to keep your context efficient." (name/description first) | CLI and VS Code skill URLs above |

## 4. Claude Code

| Claim | Status | Quote | URL |
|---|---|---|---|
| `~/.claude/CLAUDE.md` and repo `CLAUDE.md` load at start | verified | "Claude reads them at the start of every session." / "CLAUDE.md and CLAUDE.local.md files in the directory hierarchy above the working directory are loaded at launch. Files in subdirectories load on demand." User file row: "`~/.claude/CLAUDE.md`". | https://code.claude.com/docs/en/memory |
| Size | verified | "target under 200 lines per CLAUDE.md file." / "Claude Code skips a file over 4 MiB". Path-scoped `.claude/rules/` with `paths:` load only for matching files. | same |
| Skills: name and description only until invoked | verified | "skill descriptions are loaded into context so Claude knows what's available, but full skill content only loads when invoked." | https://code.claude.com/docs/en/skills |
| Skill locations | verified | `~/.claude/skills/`, `.claude/skills/`, nested, `--add-dir`, plugin, managed. `.agents/skills` not mentioned. | same |
| Reads `AGENTS.md` natively | verified (v2.1.277+) | "Claude Code can read `AGENTS.md` as your project instructions" / "By default, Claude reads `AGENTS.md` only when you have no `CLAUDE.md` in your working directory or above it." `~/.claude/CLAUDE.md` does not count for that check. | https://code.claude.com/docs/en/memory |
| `@AGENTS.md` import still needed when | verified | Needed when the project also has a `CLAUDE.md`, Project instructions = `claude-md`, or sessions that cannot load it; "Keeping the import never makes Claude read `AGENTS.md` twice". Windows: use the import, not a symlink. | same |

## Implications for splitting knowledge into modules per host

1. `AGENTS.md` is the only always-loaded file all three hosts read (Codex natively; Copilot CLI and
   VS Code Copilot harness natively; Claude Code natively only without a `CLAUDE.md`, else via
   `@AGENTS.md`). Keep the shared always-on core there, short (Codex caps the chain at 32 KiB).
2. This repo has a root `CLAUDE.md` and no `AGENTS.md`, so if one is added Claude Code needs `@AGENTS.md` in it to see shared content.
3. Codex ignores `CLAUDE.md`, `.claude/` and `.github/copilot-instructions.md`; anything only
   there is invisible to Codex.
4. Skills are the portable on-demand unit: bodies load only when chosen on all three hosts.
   Directory overlap: `.agents/skills` (Codex, Copilot CLI/VS Code), `.claude/skills` (Claude Code,
   Copilot CLI/VS Code). No single directory is documented for all three; `.agents/skills` is not
   documented for Claude Code. User level: `~/.agents/skills` (Codex, Copilot), `~/.claude/skills`
   (Claude Code).
5. Path-scoped always-on rules exist only on Copilot (`applyTo`) and Claude Code (`paths:` in
   `.claude/rules/`); Codex has no documented equivalent beyond nested `AGENTS.md` per directory.
6. Do not use Codex custom prompts (`~/.codex/prompts`); deprecated in favour of skills.
7. User-level homes are movable: `CODEX_HOME` (default `~/.codex`), `COPILOT_HOME` (default
   `~/.copilot`); setup must resolve them, not hard-code paths.
