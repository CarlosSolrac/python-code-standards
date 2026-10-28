## Copilot Review Rule

When using Copilot to implement, refactor, or fix code, spawn a sub-agent for review and
specify `GPT-Astra` as its model. Request high effort when the sub-agent tool supports it.
Do not run a Codex review for that Copilot task. If `GPT-Astra` is
unavailable or the tool cannot accept the model selection, report that limitation and do not
silently substitute Codex.
