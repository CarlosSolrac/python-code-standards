# Testing

Standard pytest practice is assumed. What follows is what shapes the outcome.

## Test-first, outside-in

1. **Types first.** Name the domain states the unit moves data through and declare each as a type (frozen dataclass, Pydantic model, or `Literal`-tagged record), so each function maps one state to the next. Parse input once, at the edge, into a type that carries its invariant.
2. **Outer loop.** Write one failing acceptance test per use case, through the composition root, with in-memory adapters (DuckDB `:memory:`, a fake HTTP client) behind the ports. It stays red until the use case works end to end.
3. **Red.** Write one failing test against the unit's public API and run it alone (`uv run pytest <test_file>::<test_name> -q`); confirm it fails for the expected reason — a missing function or a wrong result, not an import typo or a broken fixture.
4. **Green.** Write the least production code that passes.
5. **Refactor** with the suite green. Helpers are extracted here, each named for the decision it owns, and are tested through the public API; give one its own tests only when it holds independently complex logic. Commit the step if the repository's workflow asks for it.
6. **Ascend.** Look at each new helper from its caller: change an interface that no longer fits, and merge any function that only forwards its arguments (`check_passthrough.py` finds them). Repeat from step 3 until the acceptance test passes.

Ports — I/O, time, randomness, the network — arrive through parameters or constructor injection as protocols, so a test swaps them without patching; unit tests replace them with fakes and nothing else. In-process collaborators are real. The acceptance tests cover the real wiring.

## Coverage

100% statement and branch coverage on changed code is the floor, not the goal — it follows from test-first, since no line exists without a test that demanded it. A line no test can reach is unreachable: delete it rather than suppress it. `# pragma: no cover` still needs explicit authorization.

## Practice

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
