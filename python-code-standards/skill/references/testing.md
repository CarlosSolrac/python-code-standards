# Testing

Standard pytest practice is assumed. What follows is what shapes the outcome.

## Test-first, top-down

1. **Start at the top.** Write a unit test for the public entry point. Inject its collaborators as fakes with the interface you want them to have; the test fixes that interface before any helper exists.
2. **Red.** Run the single test (`uv run pytest <test_file>::<test_name> -q`) and confirm it fails for the expected reason — a missing function or a wrong result, not an import typo or a broken fixture.
3. **Green.** Write the least production code that passes: the entry point, calling helpers by the interface the fakes defined.
4. **Refactor** with the suite green, then commit the step if the repository's workflow asks for it.
5. **Descend.** Each helper the entry point needed becomes the next unit: write its failing test, make it pass, repeat until every leaf is real. Stubs never survive to the finished change.

Unit tests isolate one unit. Collaborators arrive through parameters or constructor injection, so a test swaps them without patching. I/O, time, randomness, and the network stay at the edges, behind injected protocols, and out of unit tests; a few integration tests cover the real wiring.

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
