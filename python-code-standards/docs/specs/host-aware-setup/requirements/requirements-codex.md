# Host-Aware Setup Requirements

## Goal and users

Provide one setup experience for a developer who uses Claude Code and Codex on a personal machine and GitHub Copilot Enterprise in both VS Code agent mode and Copilot CLI on a separate work machine. The setup must preserve the same Python quality gates in shared repositories while configuring only the agent hosts available on the current machine, with all host- and environment-specific choices stored outside the repository.

## Functional requirements

R1. The setup shall let the user identify every agent host to configure on the current machine and shall support, at minimum, Claude Code, Codex, GitHub Copilot in VS Code, and GitHub Copilot CLI; an acceptance test shall exercise each supported host choice independently and the personal and work combinations.

R2. Before any configuration write, the setup shall show the selected host or surface, the exact destination path, and the proposed content or change, then require confirmation unless the user explicitly selected an existing non-interactive confirmation mode.

R3. The setup shall keep coordinator, coding, and adversarial-review role choices separately for each configured host when that host supports such choices; it shall not translate a model name from one provider or host into another without an explicit user choice.

R4. On an interactive re-run, the setup shall read prior machine-local choices for the selected host and offer them as defaults without overwriting unrelated configuration.

R5. In non-interactive mode, the setup shall preserve existing machine-local host choices and shall create defaults only when no choices for that host exist; the resulting behavior shall be deterministic and documented in the command output.

R6. If a requested role, model-selection scope, instruction mechanism, hook event, or hook enforcement behavior is unsupported or cannot be verified for the selected host and surface, the setup shall report that capability as unsupported or unknown and shall not claim or silently emulate it.

R7. The setup shall install or configure host instructions only through locations and formats verified by the current official reference for that host and surface, and an automated test shall verify that no host-specific instruction or model choice is written into the target repository.

R8. The setup shall configure hooks only from a documented contract for the selected host and surface, including event name, input JSON, output JSON, exit behavior, timeout behavior, and command execution environment; contract tests shall use host-shaped fixtures and assert exact output and exit status.

R9. The setup shall treat VS Code Copilot and Copilot CLI as distinct surfaces for capability checks and end-to-end verification even where an official reference states that they share a harness or format. VS Code currently documents that its Copilot harness is shared with Copilot CLI, while also warning that provider implementations and managed settings can differ ([VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)).

R10. The same repository-level gates installed today—pre-commit, pytest with coverage, diff-cover, and the applicable completion/Stop gate—shall enforce equivalent quality outcomes on every supported host; host-specific limitations shall be reported rather than weakening the underlying gate criteria.

R11. The setup shall verify each configured host with a local smoke test that proves its instructions are discoverable and each enabled hook receives the expected event and produces the expected decision or failure; synthetic fixture tests alone shall not count as host verification.

R12. When organization policy, missing software, unavailable models, unsupported hooks, or insufficient permissions prevent configuration or verification, the setup shall leave existing configuration intact, identify the affected host and capability, and provide a non-success result for that host without misreporting other hosts.

R13. A setup run shall produce a machine-local summary of hosts selected, capabilities configured, files changed, verification performed, and unresolved capabilities, without recording secrets, prompts, source content, personal identifiers, or absolute repository paths in the shared repository.

R14. Existing Claude-only installations shall remain readable and re-runnable without losing their stored model choices or unrelated `~/.claude` settings.

## Non-functional requirements and constraints

- NFR1 Privacy: no personal data, credentials, prompts, source content, model entitlement details, or captured raw hook events shall leave the machine. Tests and diagnostics shall use synthetic or sanitized data.
- NFR2 Repository neutrality: no machine-, account-, employer-, subscription-, provider-, host-, surface-, or model-specific value shall be stored in the target repository. Shared gate code and host-neutral project instructions may remain repository content.
- NFR3 External-write safety: every write outside the target repository shall be previewed with its exact path and confirmed before execution, except when the user explicitly invokes the documented non-interactive mode; existing unrelated bytes and settings shall be preserved.
- NFR4 Platform support: configuration discovery, path handling, previews, writes, and verification shall work with native Windows home directories and WSL/Linux home directories, including spaces and non-ASCII characters in paths.
- NFR5 Idempotence: repeating setup with unchanged answers shall make no file changes and shall produce the same capability result.
- NFR6 Failure isolation: failure to configure one host or surface shall not corrupt or partially rewrite another host's configuration.
- NFR7 Auditability: every claimed host capability shall be traceable to a dated official reference and a passing contract or smoke test. GitHub documents Copilot hooks and their surface-specific behavior in its [hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference).
- NFR8 Maintainability: host-contract changes shall be independently testable so an update for one host does not require changing shared gate policy.
- NFR9 Enterprise compatibility: the setup shall detect or report applicable organization restrictions rather than attempt to bypass them. VS Code documents that organizations may restrict hooks and that enterprise-managed settings can disable harnesses ([VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)).

## Explicit non-goals

- Switching profiles between personal and work environments on one machine or synchronizing configuration between machines.
- Storing personal or work model choices in a shared repository.
- Using a Copilot Enterprise entitlement to run or configure Claude Code, Codex, or another provider.
- Creating one universal hook schema, assuming Claude-compatible names imply compatible behavior, or making undocumented host behavior a supported contract.
- Selecting, purchasing, enabling, or administering models or organization policies on the user's behalf.
- Replacing pre-commit, pytest, coverage, or diff-cover with host-specific equivalents.
- Supporting Copilot cloud agents, GitHub.com chat, Copilot code review, IDEs other than VS Code, or other agent hosts unless separately scoped.
- Designing the host-adapter architecture, configuration file layout, discovery strategy, migration algorithm, or user interface in this document.

## Open questions and unverified facts

### Questions only the user can answer

1. Does the work organization's Copilot policy allow user-level hooks and custom instructions in both VS Code and Copilot CLI, or must setup operate without one or both capabilities?
2. Should an unavailable preferred work model block setup, prompt for another allowed model, or leave model selection to Copilot's `Auto` option? GitHub documents surface-level model selection and changing availability, but this is a workflow preference ([Copilot model selection](https://docs.github.com/en/copilot/how-tos/use-ai-models/change-the-chat-model), [Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)).
3. On the personal machine, must Codex receive the same coordinator/coding/reviewer role semantics as Claude Code, or is configuring Codex only for the roles it natively supports acceptable?

### Facts not verified

- Unknown: which models and model aliases the work organization currently enables, and whether those differ between VS Code and Copilot CLI.
- Unknown: whether the work organization permits user hook files, hook execution, custom instructions, plugins, and local smoke tests on both surfaces.
- Unknown: whether either Copilot surface exposes durable, machine-level defaults for all three workflow roles; official documentation verifies model selection, not the required three-role mapping.
- Unknown: the current Codex instruction, model-selection, hook, and failure contracts to use for this feature; they require a separate review of the current official Codex reference and an on-host smoke test.
- Unknown: whether an equivalent to Claude Code's Stop-hook completion gate exists on each selected Copilot and Codex surface. No equivalence shall be assumed from similarly named lifecycle events.

## Risks

- Copilot hooks are documented as preview functionality and may change, invalidating configuration or fixtures ([VS Code agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)).
- Enterprise policy may expose models while prohibiting the hooks or instruction mechanisms needed for equivalent enforcement.
- A hook that accepts more than one host-shaped payload could misidentify the host and emit an invalid or unsafe decision envelope.
- Different timeout and failure semantics can make a gate fail open on one surface and fail closed on another.
- VS Code, Copilot CLI, WSL, and native Windows may resolve different homes, shells, working directories, and executable paths, causing configuration to be written or executed in the wrong environment.
- Model catalogs, aliases, and entitlements change over time; persisted choices can become unavailable or acquire different meanings.
- Host-specific data can leak into a shared repository through generated settings, logs, backups, fixtures, or diagnostics unless repository-neutrality tests cover all outputs.
- Partial configuration across multiple hosts can give the user false confidence that every surface enforces the same gates.
