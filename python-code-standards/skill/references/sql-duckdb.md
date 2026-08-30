# SQL and DuckDB

Applies whenever Python constructs, executes, or embeds SQL.

- **Never interpolate values into SQL.** Bind them: `conn.execute(sql, [param])` or named parameters. Ruff `S608` flags f-string and `%` composition, and that flag is never suppressed.
- Identifiers cannot be bound. When a table or column name must be dynamic, validate it against an explicit allowlist before composition.
- Keep SQL in module-level constants or `.sql` files, not inline at call sites, so statements are reviewable and testable alone.
- A builder returns SQL and parameters; a separate function executes it. Query construction and business logic do not share a function.
- Format multi-line SQL with uppercase keywords, one clause per line, leading commas in select lists. The 220-character limit applies to the Python line, not to SQL readability.
- Prefer the relational API or a bound query for programmatic composition; reserve string SQL for static statements.

DuckDB specifics:

- It ships `py.typed`, so no stubs. Annotate `duckdb.DuckDBPyConnection` and `duckdb.DuckDBPyRelation`.
- Manage connections with a context manager or explicit `close()`; do not rely on interpreter shutdown.
- Convert result sets to `TypedDict`, dataclasses, or a DataFrame with declared dtypes at the boundary. Raw tuples do not enter business logic.
- Tests use `duckdb.connect(":memory:")` with fixture data. No test touches a shared or networked database.
