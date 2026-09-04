# Conditional domains

Read the relevant section when the work touches it.

## Domain modeling and configuration

- The boundary between the two: Pydantic where input is untrusted or structurally variable and runtime validation earns its cost; dataclasses everywhere else. Reaching for Pydantic on internal types buys validation nobody needs and a dependency in the hot path.
- Prefer frozen dataclasses for validated values, `slots=True` where measurement justifies it, and mutable ones only where mutation is the type's explicit responsibility.
- Design types so invalid states are hard to construct: discriminated unions with `Literal` over one model of conditionally valid optional fields, `NewType` or a value object for identifiers sharing a runtime representation, `Protocol` where behavior matters more than inheritance.
- Read environment variables once at the composition root, parse into a typed settings object, validate at startup, inject it. No environment reads, settings construction, or process exit at import time.
- Require explicit values for credentials, signing keys, and production endpoints; defaults only for non-sensitive settings. Document every variable: required, type, default, sensitivity.
- Never embed credentials, tokens, or environment-specific paths. Verify TLS by default. `DTZ` requires timezone-aware datetimes; `T20` keeps `print` out of library code.

## Pydantic

Applies when the project already uses it, or runtime validation at a boundary justifies it.

- Use it at untrusted or structurally variable boundaries: API payloads, configuration, external files, messages, ORM conversion. Not as a replacement for dataclasses or internal types needing no validation.
- Keep boundary models separate from domain models when invariants, mutability, or lifecycle differ. Separate request, update, persistence, and response models rather than one permissive model reused across unrelated operations.
- Decide explicitly whether each boundary permits coercion; prefer strict where it could hide malformed input, precision loss, or identifier confusion. Test every supported coercion and every value that must be rejected.
- Prefer `Annotated` and `Field` constraints over validators; use validators only for normalization, cross-field invariants, or rules the schema can't express, and keep them free of I/O and hidden mutation.
- Treat serialization as an external contract. Secret-aware types don't guarantee exclusion from every path — exclude sensitive fields explicitly from responses, logs, error details, and debug output. Test aliases, strictness, defaults, discriminators, and custom serializers wherever they're part of the contract.
- Prefer `pydantic-settings` where Pydantic is already present. A major-version migration is a behavioral change, not a rename: test accepted input, rejected input, coercion, validator ordering, aliases, ORM conversion, and serialized output. Keep it localized unless a project-wide migration was requested.

## Concurrency and performance

Applies when async execution, threads, processes, or a measured performance requirement is in play.

- Introduce concurrency only when the workload justifies it, and reuse the repository's model. Converting sync to async, or async to threads, is never an incidental refactor.
- A function doesn't become async merely because it performs I/O. Threads are for blocking I/O that can't use the project's async interfaces; they don't speed up CPU-bound Python. Processes need serialization cost, startup overhead, and testability accounted for first. (`ASYNC` catches blocking calls inside async functions.)
- Bound concurrency explicitly — never fan out unbounded from untrusted or variable-sized input. Prefer structured concurrency so child tasks can't outlive their caller.
- Define whether an operation is fail-fast, best-effort, or partially successful. `return_exceptions=True` only where exceptions are deliberately typed, inspected, and reported. Preserve input-to-result correspondence when completion order differs from submission order.
- Apply timeouts where the maximum acceptable duration is known, and distinguish timeout from cancellation from underlying failure. Task groups, clients, streams, and executors close on success, error, timeout, *and* cancellation.
- Optimize only against a measured problem, recording workload, baseline, metric, and method. Keep correctness tests around optimized code and benchmarks isolated from them.

## Packaging and dependency security

- Follow the repository's existing build backend, layout, metadata, and release process. New reusable packages: prefer `src` layout so tests verify the installed package; keep `__all__` intentional and `__init__.py` free of expensive imports, config reads, and connections.
- Run the dependency vulnerability audit in CI or before release, and secret detection where the repository handles credentials, production data, publishing, or deployment. Audit CI changes touching those.
- `uv.lock` changes and automated dependency updates go through the same verification as any other change.
- Never suppress a confirmed vulnerable dependency, leaked secret, or unsafe workflow finding without authorization and a documented risk decision.
