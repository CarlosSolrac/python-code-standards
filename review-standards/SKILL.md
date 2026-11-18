---
name: review-standards
description: Use when reviewing a code change adversarially. Defines what counts as a defect, the project invariants a reviewer checks, and how to read the computed review brief. Does not teach how to write code.
---

# Review standards

You review a change; you do not write it. Report only defects you can show.

## What counts as a defect

- A behaviour that is wrong for some input you can name: a failing case, not a feeling.
- Data loss, a security hole, or an unchecked boundary (user input, file paths, SQL, shell).
- Changed behaviour with no test that would fail without the change.
- A new failure path nothing catches, or a swallowed error.
- A comment, docstring or spec that now describes code that changed.

Skip anything Ruff, pyright, mypy or the repository's tests already report. Skip style and naming.

## Project invariants to check

These are claims to verify, not rules to apply to your own writing.

1. Every changed line is covered by a test that fails without it (statement and branch).
2. No new suppression (`noqa`, `type: ignore`, `pragma: no cover`, per-file ignore, lowered threshold, warning filter) without the change saying who approved it.
3. No change to CI, hooks, or build configuration that the change does not state a reason for.
4. No dependency added, removed or upgraded without a stated reason.
5. A bug fix includes a regression test for that bug.

## Reading the review brief

The brief is computed, not judged: change size, gate files touched, dependency changes, added suppressions, the most complex changed functions, changed modules no test imports, surviving mutants. Look first where it points. A brief of "none"s means nothing needs a closer look; it does not mean the change is correct.

## Reporting

For each finding: file and line, the input or state that breaks it, what happens, and the smallest fix direction. Reproduce before reporting; if you cannot reproduce, say so and do not report it as a defect. Rank by impact. If you find nothing, say so plainly.
