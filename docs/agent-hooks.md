# Agent Skills and Hooks Across Hosts

Research snapshot: 2026-10-20. Star counts are approximate values shown by GitHub during this review; they change over time. Repository search used GitHub's star-sorted `agent skills hooks` and `claude code skills hooks` queries. This is a focused sample of relevant projects, not a census of every repository.

## Findings

| Repository | Stars, approximately | Relevant evidence |
|---|---:|---|
| [anthropics/skills](https://github.com/anthropics/skills) | 182.5k | Skill folders, `SKILL.md`, optional scripts/references/assets, and skill evaluation guidance. The repository documents Claude's implementation; the [Agent Skills specification](https://agentskills.io/specification) defines the portable format. |
| [mksglu/context-mode](https://github.com/mksglu/context-mode) | 31.3k | Multiple host adapters, explicit capability differences, per-adapter payload/response tests, and integration tests that exercise real stdin/stdout behavior. |
| [diet103/claude-code-infrastructure-showcase](https://github.com/diet103/claude-code-infrastructure-showcase) | 10.0k | Skill activation separated into suggestions and enforcement; hook registration, troubleshooting, and false-positive checks are documented. Its stateful two-attempt guard is a project-specific design, not a default to copy. |
| [ChrisWiles/claude-code-showcase](https://github.com/ChrisWiles/claude-code-showcase) | 6.1k | Human-readable hook configuration docs and prompt/path-based skill evaluation. Treat its Claude-specific examples as examples, not a cross-host API. |
| [WorldFlowAI/everything-claude-code](https://github.com/WorldFlowAI/everything-claude-code) | 5.1k | Skills, hooks, agents, and tests are organized separately; Node.js improves Windows/macOS/Linux portability, while the hook configuration and paths remain Claude-specific. |

The common lesson is that **operating-system portability is not agent portability**. A hook can run on Windows and Linux while still depending on one host's event names, configuration locations, JSON fields, output schema, and failure rules.

## Host Contracts

| Host | Event/config distinction | Pre-tool input and decision | Failure detail |
|---|---|---|---|
| Claude Code | PascalCase events in Claude settings/plugin/skill frontmatter. | `tool_name` and `tool_input`; decision is nested in `hookSpecificOutput` with `hookEventName: "PreToolUse"`. `ask` requests user confirmation. | Exit 2 blocks. Other failures normally continue unless configured otherwise; timeout behavior is event- and configuration-dependent. |
| VS Code Copilot harness | Provider harness. Use GitHub's Copilot reference; supported events and behavior depend on the selected session target. | The PascalCase compatibility payload uses snake_case fields. `PreToolUse` decisions are root-level, such as `{"permissionDecision":"ask"}`. | Copilot command-hook errors and timeout behavior differ from Claude; consult the selected surface's reference. |
| VS Code Local harness | PascalCase events and Local hook schema. Copilot-shaped hook files can be mapped to this format, but the running payload remains Local's. | `tool_name`, object `tool_input`, and `tool_use_id`; decisions use `hookSpecificOutput`. | Exit 2 is a blocking error. Other nonzero codes are warnings and continue. |
| GitHub Copilot CLI | Version 1 hook JSON; event names may be lower camelCase or PascalCase. Cross-tool Claude settings can also be read. | Lower camelCase uses `toolName`/`toolArgs`; PascalCase uses `tool_name`/`tool_input` and Claude-compatible tool names. `PreToolUse` decisions are root-level. `ask` is not interactive in autopilot/cloud contexts and is treated as deny. | Command `preToolUse` fails closed for non-timeout errors; timeout is fail-open. Cloud agent has no interactive permission prompt. |
| Codex CLI | Separate hook registration and runtime contract. | Use Codex's own event, tool, and response schema; do not infer it from Claude-compatible skill text. | Verify against the selected Codex version and its current hook docs. |

Primary references: [VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks), [VS Code Local hooks reference](https://code.visualstudio.com/docs/agents/reference/hooks-reference), [GitHub Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [Claude Code hooks](https://code.claude.com/docs/en/hooks), and [Codex hooks](https://developers.openai.com/codex/hooks/).

The VS Code docs explicitly say to select the harness and compare event names, tool schemas, output decisions, command working directory, and accessible files before migrating a hook. A shared file location or config mapping is not a guarantee of shared runtime semantics. Transcript formats are not stable cross-harness APIs; use documented event fields and inspect agent debug logs only to discover current tool schemas.

## Reusable Design

- Keep skill guidance about domain workflows separate from hook adapters that enforce machine-checkable policy.
- Keep each `SKILL.md` focused. Use the standard `name` and `description` frontmatter, move detailed material into referenced files, and treat nonstandard frontmatter fields such as hooks or allowed-tool declarations as implementation-specific unless the target host documents them.
- Model hooks as small host adapters around the same policy decision. Make the input schema, output schema, event registration, and failure policy explicit for each host; do not infer these from the language used by the hook script.
- Test the pure policy separately from each host's stdin/stdout adapter. Adapter tests should include host-shaped positive, pass-through, malformed, nested, and uninspectable events, plus the exact decision envelope and exit status.
- Use sanitized captured events as fixtures when available. Keep synthetic compatibility fixtures labeled as synthetic, and never treat transcript JSON as the hook API.
- A recognized mutating tool with an uninspectable target should not silently bypass a quality gate. An unknown, unrelated tool should remain unaffected.
- Keep hooks fast and deterministic. Use suggestions for guidance and reserve blocking for explicit, testable policy; avoid adding session state or AI calls to a hook unless the requirement justifies their cost and failure modes.

## This Project

The setup script installs Claude Code hooks. The guard also recognizes the documented PascalCase Copilot provider input signature used by Copilot CLI and the VS Code Copilot harness, and emits that host's root-level PreToolUse decision while retaining the Claude/VS Code Local nested response. The host discriminator is the Copilot PascalCase combination of a string `timestamp` and no `tool_use_id`; Local includes `tool_use_id`.

Copilot CLI on Windows runs a hook's `command` in PowerShell unless the entry has its own `powershell` field, so a POSIX-quoted `"$CLAUDE_PROJECT_DIR"` expands to an empty string there. Each installed hook therefore carries a `powershell` launch line that reads `$env:CLAUDE_PROJECT_DIR` and falls back to `git rev-parse --show-toplevel`.

`tests/fixtures/hook_events.json` contains sanitized Claude tool-call records extracted from the permitted project logs. Their original edit text, write content, descriptions, absolute checkout paths, and session metadata are not retained. The raw `apply_patch` and Copilot-format cases are compatibility tests, not captured Copilot events. The tests validate the adapter contract but do not replace a live hook smoke test in each host.
