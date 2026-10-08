Research these topics for useful features:

https://github.com/trailofbits

https://github.com/HypothesisWorks/hypothesis/blob/master/.claude/commands/hypothesis.md

https://github.com/trailofbits/skills/tree/main/plugins/modern-python

https://xygeni.io/pricing/

---

Comparing the Best 6 Semgrep Alternatives
To help you compare the alternatives above, the table below summarizes each tool's strengths, limitations and ideal use cases.

Tool	Coverage	Strengths	Limitations	Ideal For
Aikido Security	✅ SAST
✅ DAST
✅ SCA
✅ IaC	AI-driven SAST, low noise, modular coverage, AI-powered remediation	✅ None	Teams seeking a solution that scales and manages all their application security needs
Fortify Static Code Analyzer	✅ SAST
❌ DAST
❌ SCA
❌ IaC	Deep analysis, wide language support	Legacy technology, less developer-friendly, can be slow	Large organizations needing deep compliance
GitHub Advanced Security	✅ SAST
❌ DAST
✅ SCA
⚠️ IaC	Native GitHub integration	Limited to the GitHub ecosystem; less granular control and flexibility than dedicated tools	Teams building fully on GitHub
SonarQube	✅ SAST
❌ DAST
❌ SCA
❌ IaC	Dev-friendly UI, clean code focus	Primarily a code-quality tool; limited security coverage, can be resource intensive	Teams wanting quality + basic security
Snyk	✅ SAST
✅ DAST
✅ SCA
✅ IaC	Open-source security, AI-powered analysis	Steep pricing model, file size limits, alert fatigue	Companies with heavy open-source usage
Opengrep	✅ SAST
❌ DAST
❌ SCA
❌ IaC	Open source, broad language support	No built-in vulnerability mapping, less robust than commercial platforms	Teams seeking an open-source SAST engine

---

https://sentry.io/pricing

https://www.aikido.dev/pricing

---

Research-code specifics
Research code has quality concerns that ordinary application metrics can miss:

Scientific validity: Tests should compare numerical results to analytic solutions, benchmarks, reference datasets, invariants, conservation laws, or previously published results—not merely test that functions run.

Data and environment provenance: Record data versions/checksums, random seeds, operating system/runtime, package lock files, and the command that regenerates each result.

Numerical robustness: Add tests for tolerances, extreme values, missing data, floating-point stability, and randomized/property-based cases. hypothesis can help generate edge cases.

Notebook reproducibility: Use nbval or pytest --nbval where suitable, execute notebooks from a fresh kernel in CI, and consider notebook-specific analyzers such as Julynter, NBLyzer, or Pynblint. These tools target hidden state, execution order, dependencies, and notebook coding practices.

Executable packaging: A pyproject.toml, pinned or locked dependencies, tests, and a CI workflow often improve practical reproducibility more than another lint metric. Large-scale research-code studies have found that successful re-execution is a meaningful indicator, though not a complete guarantee, of computational reproducibility.

---

Metrics researchers commonly report
Quality dimension	Typical metrics	Why it matters
Style and likely defects	Lint warnings/errors, rule violations per 1,000 LOC, lint score	Finds suspicious code, unused variables/imports, bad exception patterns, naming/style problems, and some bug-prone constructs
Complexity	Cyclomatic complexity; cognitive complexity; number/size of functions	High-complexity code is harder to test, review, reproduce, and modify
Maintainability	Maintainability Index, code smells, duplication, lines of code, comment/docstring density	A proxy for how costly future understanding and changes will be
Correctness	Test pass rate, failures, branch/line coverage, mutation score	Static checks cannot establish that scientific results are computed correctly
Type safety	Number of type-checker errors; percentage of typed public APIs	Catches interface and data-shape mistakes before runtime
Security	Security findings by severity; dependency vulnerabilities; secrets detected	Particularly relevant if code handles credentials, files, deserialization, shell commands, or external data
Reproducibility	Clean-environment run success, pinned dependencies, rerun time, deterministic outputs	Central to research software; successful execution is a useful—though insufficient—reproducibility signal
Notebook quality	Out-of-order execution problems, hidden state, undeclared dependencies, oversized cells	Jupyter notebooks need checks beyond ordinary .py source analysis
Core Python tools
Tool	Primary role	Measures or detects	Good use in a research paper?
Ruff	Fast linter and formatter	Style, imports, many correctness rules, bugbear-style issues, selected code smells	Yes—excellent default for a modern project, but report the exact rule set and version
Pylint	Deep linting and design checks	Errors, code smells, conventions, refactoring suggestions; can emit a score	Yes—very commonly recognized in empirical studies; do not treat its single score as your whole quality result
Flake8	Plugin-based linting	pycodestyle, pyflakes, McCabe complexity, extensions	Yes—common in legacy or highly configurable workflows; the rules/plugins must be disclosed
Radon	Complexity and maintainability metrics	Cyclomatic complexity, Maintainability Index, raw metrics, Halstead metrics	Yes—one of the clearest choices for numerical complexity/maintainability reporting
Lizard	Complexity reporting	Cyclomatic complexity and function-level metrics across languages	Useful if comparing Python with other languages or repositories
SonarQube / SonarCloud	Dashboard and quality gates	Bugs, vulnerabilities, code smells, duplication, coverage imports, security hotspots	Useful for larger multi-developer projects and longitudinal tracking; document the quality profile
mypy	Static type checking	Type errors and missing/incompatible annotations	Strong addition when scientific code uses typed APIs, arrays, tabular data, or complex data models
Pyright	Static type checking	Type errors; fast editor/CI integration	A strong alternative to mypy, especially where VS Code/Pylance is already used
pytest	Testing framework	Test pass/fail; basis for regression and scientific-validation tests	Essential for functional correctness, and commonly included in published evaluation pipelines
coverage.py / pytest-cov	Test coverage	Line and branch coverage	Report alongside tests, but do not equate high coverage with scientific validity
mutmut / Cosmic Ray	Mutation testing	Mutation score—whether tests detect intentional small code faults	Valuable for a stronger test-suite study; more meaningful than coverage alone
Bandit	Python security static analysis	Common security weaknesses, e.g. unsafe subprocess use, insecure temp files, unsafe YAML patterns	Widely used in research comparisons and CI quality stacks
pip-audit / Safety	Dependency vulnerability checking	Known vulnerabilities in installed/pinned packages	Useful for distributable research software, especially web-facing or shared tools
Gitleaks	Secret scanning	Committed API keys, tokens, credentials	Useful for public repositories; notebook outputs can accidentally expose secrets
pytest-benchmark / asv	Performance regression testing	Execution time and benchmark changes	Appropriate when runtime or scalability is a scientific/software claim
cProfile, Scalene, py-spy	Profiling	CPU time, memory behavior, hotspots	Use when performance is part of the research question, not as a generic “quality” metric

---

What is most defensible in a paper

For an ordinary scientific Python package—not a study whose subject is software engineering—I would report a small, interpretable set rather than every available analyzer output:

Static quality: Ruff or Pylint findings, normalized as findings per 1,000 logical lines of code.

Complexity: Radon’s function-level cyclomatic complexity, reporting median, upper quantiles, and count/share of functions above a predefined threshold.

Maintainability: Radon Maintainability Index and duplicate-code rate, if duplication is relevant.

Correctness: number of tests, test pass rate, and branch coverage; add mutation score for stronger claims about test effectiveness.

Typing: mypy or Pyright error count, and optionally typed-API coverage.

Security: Bandit findings by severity and pip-audit results.

Reproducibility: whether a clean environment can install dependencies and regenerate the principal outputs from raw or archived data.

For example, a concise methods statement could be:

We evaluated software quality using Ruff for lint and style violations, Radon for cyclomatic complexity and Maintainability Index, mypy for static type errors, Bandit for security findings, and pytest with branch coverage for functional validation. All tools were executed in continuous integration using pinned versions; results were normalized by logical lines of code and reported by severity or distribution rather than as a single composite score.

That is more scientifically transparent than saying “the repository has a Pylint score of 9.8.” A high lint score can coexist with incorrect numerical methods, weak tests, irreproducible environments, or unvalidated assumptions.

Research-code specifics
Research code has quality concerns that ordinary application metrics can miss:

Scientific validity: Tests should compare numerical results to analytic solutions, benchmarks, reference datasets, invariants, conservation laws, or previously published results—not merely test that functions run.

Data and environment provenance: Record data versions/checksums, random seeds, operating system/runtime, package lock files, and the command that regenerates each result.

Numerical robustness: Add tests for tolerances, extreme values, missing data, floating-point stability, and randomized/property-based cases. hypothesis can help generate edge cases.

Notebook reproducibility: Use nbval or pytest --nbval where suitable, execute notebooks from a fresh kernel in CI, and consider notebook-specific analyzers such as Julynter, NBLyzer, or Pynblint. These tools target hidden state, execution order, dependencies, and notebook coding practices.

Executable packaging: A pyproject.toml, pinned or locked dependencies, tests, and a CI workflow often improve practical reproducibility more than another lint metric. Large-scale research-code studies have found that successful re-execution is a meaningful indicator, though not a complete guarantee, of computational reproducibility.

---

https://github.com/trailofbits/skills/tree/main/plugins/variant-analysis

https://github.com/trailofbits/skills/tree/main/plugins/trailmark

https://appsec.guide/
https://github.com/trailofbits/skills/tree/main/plugins/testing-handbook-skills

https://github.com/trailofbits/skills/tree/main/plugins/supply-chain-risk-auditor

https://github.com/trailofbits/skills/tree/main/plugins/static-analysis

https://github.com/trailofbits/skills/tree/main/plugins/spec-to-code-compliance

https://github.com/trailofbits/skills/tree/main/plugins/sharp-edges

https://github.com/trailofbits/skills/tree/main/plugins/semgrep-rule-variant-creator

https://github.com/trailofbits/skills/tree/main/plugins/semgrep-rule-creator

https://github.com/trailofbits/skills/tree/main/plugins/review-walkthrough

https://github.com/trailofbits/skills/tree/main/plugins/property-based-testing

https://github.com/trailofbits/skills/tree/main/plugins/open-sourcing

https://github.com/trailofbits/skills/tree/main/plugins/mutation-testing

https://github.com/trailofbits/skills/tree/main/plugins/modern-python

https://github.com/trailofbits/skills/tree/main/plugins/insecure-defaults

https://github.com/trailofbits/skills/tree/main/plugins/goal-prompt

https://github.com/trailofbits/skills/tree/main/plugins/github-triage

https://github.com/trailofbits/skills/tree/main/plugins/git-cleanup

https://github.com/trailofbits/skills/tree/main/plugins/gh-cli

https://github.com/trailofbits/skills/tree/main/plugins/fp-check

https://github.com/trailofbits/skills/tree/main/plugins/dimensional-analysis

https://github.com/trailofbits/skills/tree/main/plugins/differential-review

https://github.com/trailofbits/skills/tree/main/plugins/devcontainer-setup

https://github.com/trailofbits/skills/tree/main/plugins/code-improver

https://github.com/trailofbits/skills/tree/main/plugins/claude-in-chrome-troubleshooting

https://github.com/trailofbits/skills/tree/main/plugins/audit-context-building

https://github.com/trailofbits/skills/tree/main/plugins/agentic-actions-auditor

https://github.com/mattpocock/skills

https://github.com/REMvisual/claude-handoff

https://github.com/gastownhall/beads

https://github.com/volcengine/OpenViking

https://github.com/iamneilroberts/claude-skills

https://github.com/thenguyenvn90/claude-session-handoff




