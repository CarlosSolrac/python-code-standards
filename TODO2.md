Not for nightshift: every item edits Claude memory under ~/.claude/projects/, outside this repository. Suggested 2026-10-16; apply each only after the user agrees.

python-code-standards, quality-gates-project-state.md: remove the "Next: production trial in a new session" paragraph and its "Offered but not run: leave-one-out mutation analysis" sentence, and the "next: production trial" part of its MEMORY.md line, unless the production trial is still planned.

python-code-standards, ignore-research-md.md: it calls RESEARCH.md "untracked", but the file is tracked. Fix that word, or delete the memory now that RESEARCH.md itself starts with a PAUSED line.

ParquetToXL, parquet-to-xl-no-enums.md: it calls enums "a gap in the tool the user may want to close one day"; the standards repo closed it (PRs #5–#7 exempt enum members). Update the memory once ParquetToXL runs setup-standards.sh --update; until then it is still true there.

~/.claude (home project), claude-code-model-switching.md: it describes claude-local behind a LiteLLM proxy and says Ollama cannot serve Claude Code directly. This repo's README now says Ollama answers /v1/messages itself, launched with bin/ai.sh and pinned with bin/set-model. Rewrite the memory to match, or delete it.

Keep as they are: ParquetToXL design-seams-preference, excel-validation-scope, gate-untracked-files, ollama-docker-host; xVault backup-not-encrypted and anythingllm-workspace-policy.
