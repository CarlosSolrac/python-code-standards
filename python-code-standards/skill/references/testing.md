# Testing

Standard pytest practice is assumed. What follows is what shapes the outcome.

- Cover every new code path and changed behavior: normal operation, meaningful boundaries, expected failures. For a bug fix, add a test that fails before and passes after — write it first and watch it fail for the expected reason.
- Test observable behavior, not internals, unless a private unit holds independently complex logic.
- For security, authorization, financial, destructive, and data-integrity behavior, cover every known outcome, denial path, and failure mode. A coverage percentage does not substitute for scenario coverage.
- Assert exception *contracts* — type plus any stable message, code, or attribute callers rely on — not incidental wording.
- Parametrize when one behavior must hold across several inputs, with readable case IDs. Use separate tests when the behaviors genuinely differ. (`PT` enforces the mechanics; this is the judgment call it can't make.)
- Prefer fakes, in-memory implementations, and injected protocols over deep mocking. When mocking, use `autospec=True`/`spec_set` so a test cannot rely on attributes the real dependency lacks, and patch where the code under test looks the symbol up.
- Keep fixtures narrow in scope and named for the state they provide; no catch-all fixture. Anything touching global state, env vars, working directory, or registries restores it via `yield` teardown.
- `skip`/`skipif`/`xfail` need a documented reason and a tracking reference. Never use them to hide a regression from the current change.
- Register every custom marker; `--strict-markers` makes an unregistered one fail.
- Reuse the repository's async plugin and loop mode; do not change either as an unrelated edit.
- Run the narrowest relevant test first, then the affected module, then whatever detects regressions in consumers. Add `pytest-xdist` only where the repository already supports it.

Coverage on changed code: **90% statement, 85% branch**, both reported.

```toml
[tool.coverage.run]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true
```
