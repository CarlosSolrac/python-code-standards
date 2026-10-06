# Equivalent mutants

Surviving mutants that change no observable behaviour, so no test can kill them.
Each is listed by mutmut's name with the reason. The list was reviewed when it was
written, and any survivor not on it is a gap in the tests. mutmut renumbers the
mutants in a function when that function's source changes, so re-check a
function's entries whenever it is edited.

## `skill/tools/changes.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x_added_lines__mutmut_46` | `number = 0` → `None` | A unified diff always has an `@@` hunk header, which resets `number`, before its first added line. |
| `x_added_lines__mutmut_47` | `number = 0` → `1` | Same: the initial value is overwritten before it is read. |

## `skill/tools/hooks/stop_gate.py`

mutmut runs on Linux, where the locale encoding is UTF-8. On Windows the
explicit encoding matters, and `test_run_command_decodes_output_as_utf8` fails
there without it.

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x_run_command__mutmut_4` | `encoding="utf-8"` → `None` | Under a UTF-8 locale, text mode already decodes UTF-8. |
| `x_run_command__mutmut_9` | `encoding=` removed | Same. |
| `x_run_command__mutmut_14` | `"utf-8"` → `"UTF-8"` | Codec names are case-insensitive. |
| `x_run_command__mutmut_6` | `check=False` → `None` | `None` is falsy, the same as `False`. |
| `x_run_command__mutmut_11` | `check=` removed | `False` is the default. |
| `x_read_coverage_xml__mutmut_1` | `encoding="utf-8"` → `None` | Under a UTF-8 locale, the default encoding is UTF-8. |
| `x_read_coverage_xml__mutmut_3` | `"utf-8"` → `"UTF-8"` | Codec names are case-insensitive. |

## `skill/tools/hooks/guard_protected.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x_main__mutmut_4`, `_8`, `_9` | `cast("dict[str, object]", …)` type string changed | `typing.cast` returns its value unchanged at run time; the string only informs type checkers. |
| `x_main__mutmut_23`, `_25`, `_28` | `tool_name` default `""` → `None`, none, `"XXXX"` | Any default that is not a tool name gives the same result: the event matches no tool, so the hook stays silent. |
| `x_protected_reason__mutmut_9` | `file_path` default `""` → `"XXXX"` | Neither names a protected file. |
| `x_protected_reason__mutmut_19` | `command` default `""` → `"XXXX"` | Neither matches a dependency or write pattern. |

## `skill/tools/check_suppressions.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x_load_allowed__mutmut_7`, `x_read_file__mutmut_1` | `encoding="utf-8"` → `None` | Under a UTF-8 locale, which mutmut uses on Linux, the default is UTF-8. |
| `x_load_allowed__mutmut_9`, `x_read_file__mutmut_4` | `"utf-8"` → `"UTF-8"` | Codec names are case-insensitive. |
| `x_main__mutmut_9` | `default=None` removed from `--base` | `None` is argparse's own default. |
| `x_unapproved__mutmut_32` | no-comment fallback `""` → `"XXXX"` | Neither text contains a directive. |

## `skill/tools/check_declarations.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x__sub_patterns__mutmut_1` | a bare capture (`case x:`) gets `[None]` as sub-patterns instead of `[]` | `_bind_pattern(None)` finds no sub-patterns and no target, so it binds nothing either way. |
| `x_check_source__mutmut_6`, `_7` | `ast.parse` `filename` dropped or `"None"` | The filename only sets `SyntaxError.filename`, which `main` never prints; it reports its own path. |
| `x_read_source__mutmut_2`, `_4`; `x_load_enum_bases__mutmut_16`, `_18` | `encoding="utf-8"` → `None`, `"UTF-8"` | UTF-8 locale on Linux; codec names are case-insensitive. |
| `x__cell_code__mutmut_11` | always `"".join(lines)` | Joining a string's characters returns the same string, and `source` is a list or a string. |
| `xǁScopeCheckerǁ__init____mutmut_10` | `in_enum_body` default `False` → `None` | It is only tested for truth, and both are falsy. |

## `evals/grade.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x__run__mutmut_6`, `_11` | `check=False` → `None` or removed | `None` is falsy and `False` is the default. |
| `x_count_ruff__mutmut_7`, `_9`, `_10`, `_12`, `_14`; `x_third_party_imports__mutmut_12`, `_14`; `x_grade__mutmut_11`, `_13`; `x_main__mutmut_68`, `_70`, `_78` | `encoding="utf-8"` → `None`, removed, or `"UTF-8"` | UTF-8 locale on Linux; codec names are case-insensitive. |
| `x_count_ruff__mutmut_48`, `_52`, `_53`; `x_count_pyright__mutmut_40`, `_44`, `_45`, `_56`, `_60`, `_61` | `cast(...)` type string changed | `typing.cast` returns its value unchanged at run time. |
| `x_count_pyright__mutmut_37`, `_39` | `summary` default `{}` → `None` or none | A missing summary fails the following `isinstance(summary, dict)` check either way and scores -1. |
| `x_count_pyright__mutmut_53`, `_55` | `errorCount` default `-1` → `None` or none | A missing count fails the following `isinstance(count, int)` check either way and scores -1. |
| `x_grade__mutmut_10` | files joined with `"XX\nXX"` instead of `"\n"` | The joined text is only searched for `pip install` and `python -m venv`; neither separator can complete a phrase across a file boundary. |
| `x_main__mutmut_38` | `--json` `default=None` removed | `None` is argparse's own default. |

## Timeouts

`evals.grade.x__payload__mutmut_5`, `_6`, `_7`, `_10`, `_12`, `_14` and `_16` turn the
retry loop in `_payload` into one that never ends. The tests hang and mutmut stops
them, so these mutants are caught, not survivors.

## `skill/tools/review_brief.py`

| Mutant | Change | Why it is equivalent |
|---|---|---|
| `x_read_text__mutmut_1`, `_3`, `_7` | `encoding="utf-8"` → `None`, removed, `"UTF-8"` | UTF-8 locale on Linux; codec names are case-insensitive. |
| `x_suppressions_section__mutmut_3`, `_9`, `_10` | allow-list label changed | The label only appears in a `ValueError` message, which the brief catches and never shows. |
| `x_added_suppressions__mutmut_20` | no-comment fallback `""` → `"XXXX"` | Neither text contains a directive. |
| `x_mutation_section__mutmut_17` | `partition(".xǁ")` → `rpartition` | A mangled method name holds exactly one `.xǁ`. |
| `x_mutation_section__mutmut_24` | separator test → tail test | With no `.xǁ` both are empty; with one, both are non-empty. |
