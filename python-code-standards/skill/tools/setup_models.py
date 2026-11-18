"""Ask which models the standards' workflow uses on each coding host, and record the answers in that host's home.

Two hosts are known: Claude Code (``~/.claude``) and Copilot (``~/.copilot``, or
``COPILOT_HOME`` when the environment sets it). Setup first asks which hosts to
configure, offering the hosts already configured, else those whose home directory
exists, else Claude Code; ``--yes`` takes that answer unasked.

Three choices per host: the coordinator model (the main session's default; it runs
the tests), the coding model (agents that write code), and the adversarial
code-review model, asked as a provider (Codex or Claude on Claude Code; Copilot or
none on Copilot) and then a model. Model names are free text; the suggestions are
only aliases or picker names.

The answers live in a block of the host's instruction file (``CLAUDE.md``,
``copilot-instructions.md``) between two marker comments, and every other byte of
that file is kept. On Claude Code the coordinator is also written to ``model`` in
``~/.claude/settings.json``, keeping its other keys; an existing ``model`` is
replaced only on an interactive re-run whose coordinator answer differs from the
stored one. Copilot gets no settings file: its model is picked in the picker or with
``--model``. Every write of every host is listed and confirmed once; ``--yes``
assumes the confirmation, writes each host's defaults (Claude Code: coordinator
``sonnet``, coding ``opus``, the alias for the latest Opus, review ``codex``
``gpt-5.4``; Copilot: ``Claude Sonnet 5.5``, ``Claude Opus 5.5``, review ``copilot``
``GPT-6 Astra``), and keeps an existing block untouched. The block ends with a coder
guard: one line telling the host not to open the other agents' instruction files.

With ``--modules``, each chosen host's skills directory (``skills`` in its folder)
gets the coding skill, and the review skill when the host reviews its own code
(provider ``claude`` on Claude Code, ``copilot`` on Copilot). A provider ``codex``
puts the review skill in ``~/.agents/skills`` instead, and the reviewer guard in a
review scope block of ``$CODEX_HOME/AGENTS.md`` (else ``~/.codex/AGENTS.md``), with
markers of its own. Setup marks each skill directory it installs with
``.managed-by`` and writes only a missing or marked directory; a link or an unmarked
directory is reported and left as it is, and a marked one no longer wanted is listed,
never removed. With ``--installer``, the setup script is copied to
``~/.local/share/python-code-standards/setup-standards.sh``. The summary ends with how
well each reviewer is kept from the coding skill and the overlaps that remain.

A host is refused, and the run exits 1, when its instruction file cannot be read,
its markers do not form exactly one closed block (a START without a later END, an
END before its START, or a repeated marker), or its settings file is not a JSON
object; nothing of that host is written, and the other hosts go ahead. A file to
write that resolves, through a symbolic link, outside the home directory needs its
own confirmation; ``--yes`` skips it and exits 1. Each file is written to a
temporary name beside it and then replaced, and a host whose write fails is
reported without stopping the others; the run then exits 1.

The setup script runs this module before the project environment exists, so it
uses the standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

START: str = "<!-- python-code-standards:models -->"
END: str = "<!-- /python-code-standards:models -->"

SUGGESTED: dict[str, tuple[str, ...]] = {"codex": ("gpt-5.4", "gpt-5.4-mini"), "claude": ("opus", "sonnet", "haiku")}
"""Model aliases offered for each Claude Code review provider; the first is that provider's default."""

PICKER: tuple[str, ...] = (
    "Claude Opus 5.5",
    "GPT-6 Astra",
    "Claude Sonnet 5.5",
    "MAI Code 2 Flash",
    "MAI Code 2",
    "GPT-6.1 Sol",
    "GPT-6 Luna",
    "Gemini 4 Carbon",
    "GPT-6.1 Terra",
    "Gemini 4 Hydrogen",
    "GPT-6.2 Astra",
    "GPT-6.2 Sol",
    "Claude Sonnet 5",
    "Claude Haiku 5.5",
    "GPT-6 Sol",
    "GPT-5.6 Sol",
    "GPT-5.6 Luna",
    "GPT-5.3-Codex",
    "MAI-Code-1.1-Flash",
    "Gemini 4 Argon",
    "Gemini 3.8 Flash",
    "Grok 4.7",
    "Grok 4.6",
)
"""The model names Copilot's picker shows, in its order."""


@dataclass(frozen=True)
class ModelChoices:
    """The models the workflow uses."""

    coordinator: str
    coding: str
    reviewer_provider: str
    reviewer_model: str


DEFAULTS: ModelChoices = ModelChoices(coordinator="sonnet", coding="opus", reviewer_provider="codex", reviewer_model=SUGGESTED["codex"][0])

LABELS: dict[str, str] = {
    "coordinator": "Coordinator model (main session default; runs the tests)",
    "coding": "Coding model (agents that write code)",
    "reviewer_provider": "Adversarial code-review provider",
    "reviewer_model": "Adversarial code-review model",
}
"""The line label of each field in the block, which is also how it is read back."""


@dataclass(frozen=True)
class Target:
    """A place setup writes to: its name in the summary, its folder in the home directory or where an environment variable moves it, and the note the summary adds once it is configured."""

    name: str
    home_dir: str
    home_env: str | None
    gate_note: str


@dataclass(frozen=True)
class Host(Target):
    """A coding host's facts: where its files live, how its block reads, and what it offers.

    ``suggestions`` maps each reviewer provider to the models offered for it, the first
    being that provider's default, and ``"models"`` to those offered for the coordinator
    and coding questions. ``settings_model_key`` is None for a host whose settings file
    setup never writes. ``guard`` is the coder guard, the block's last line, and
    ``own_reviewer`` the provider that reviews from the host's own skills directory.
    """

    instructions_name: str
    settings_model_key: str | None
    heading: str
    defaults: ModelChoices
    providers: tuple[str, ...]
    suggestions: Mapping[str, tuple[str, ...]]
    guard: str
    own_reviewer: str


@dataclass(frozen=True)
class ReviewTarget(Target):
    """A reviewer that writes no code: its instruction file holds only the reviewer guard, and the review skill goes to ``skills_dir`` in the home directory."""

    instructions_name: str
    override_name: str
    heading: str
    guard: str
    skills_dir: str


@dataclass(frozen=True)
class Markers:
    """The comment pair that delimits one kind of block setup keeps in an instruction file."""

    start: str
    end: str
    kind: str


MODELS: Markers = Markers(START, END, "models")
REVIEW: Markers = Markers("<!-- python-code-standards:review -->", "<!-- /python-code-standards:review -->", "review scope")
"""Distinct from ``MODELS``, so a file holding both blocks never merges one into the other."""

CODING_SKILL: str = "python-code-standards"
REVIEW_SKILL: str = "review-standards"
MANAGED_BY: str = ".managed-by"
MANAGED_TEXT: str = "python-code-standards setup\n"
"""The marker file of a skill directory setup installed; only such a directory, or a missing one, is written."""


CLAUDE_CODE: Host = Host(
    name="claude-code",
    home_dir=".claude",
    home_env=None,
    instructions_name="CLAUDE.md",
    settings_model_key="model",
    heading="## Models",
    defaults=DEFAULTS,
    providers=tuple(SUGGESTED),
    suggestions={"models": SUGGESTED["claude"], **SUGGESTED},
    gate_note="The repository's stop gate in `.claude/settings.json` runs the checks when a Claude Code session ends.",
    guard="Other agents' instruction files (`AGENTS.md`, `.github/copilot-instructions.md`) are not for you; do not open them unless a change touches them.",
    own_reviewer="claude",
)

COPILOT: Host = Host(
    name="copilot",
    home_dir=".copilot",
    home_env="COPILOT_HOME",
    instructions_name="copilot-instructions.md",
    settings_model_key=None,
    heading="## Models (Copilot)",
    defaults=ModelChoices(coordinator="Claude Sonnet 5.5", coding="Claude Opus 5.5", reviewer_provider="copilot", reviewer_model="GPT-6 Astra"),
    providers=("copilot", "none"),
    # The default reviewer leads its list, since the first suggestion is a provider's default.
    suggestions={"models": PICKER, "copilot": ("GPT-6 Astra", *(name for name in PICKER if name != "GPT-6 Astra")), "none": ("none",)},
    gate_note="\n".join(
        [
            "Configured, not verified.",
            "Stop gate configured for Claude Code only. Copilot's mapping of the repo's `.claude/settings.json` hooks is unverified"
            " and Copilot already reads that file. To check by hand run the gates in `docs/quality-gates.md`.",
            "Pick the model in the picker or with `--model`; setup writes no Copilot model setting.",
            "Check by hand, once per surface:",
            "- [ ] VS Code agent mode: open a session, ask which models it was told to use, confirm each hook fires.",
            "- [ ] Copilot CLI: open a session, ask which models it was told to use, confirm each hook fires.",
        ]
    ),
    guard="Other agents' instruction files (`CLAUDE.md`, `.claude/`, `AGENTS.md`) are not for you; do not open them unless a change touches them.",
    own_reviewer="copilot",
)

HOSTS: tuple[Host, ...] = (CLAUDE_CODE, COPILOT)
"""Every host setup can configure, in the order they are asked and reported."""

CODEX: ReviewTarget = ReviewTarget(
    name="codex",
    home_dir=".codex",
    home_env="CODEX_HOME",
    gate_note="Codex reviews with the `review-standards` skill; the guard narrows what it opens, it does not forbid it.",
    instructions_name="AGENTS.md",
    override_name="AGENTS.override.md",
    heading="## Review scope",
    guard="You are a reviewer. Do not load the `python-code-standards` or `design-spec` skills and do not open `CLAUDE.md`, `.github/copilot-instructions.md` or `.claude/`. Use the `review-standards` skill.",
    skills_dir=".agents/skills",
)
"""Planned whenever a chosen host's review provider is ``codex``, its name."""

INSTALLER: Target = Target(
    name="installer",
    home_dir=".local/share/python-code-standards",
    home_env=None,
    gate_note="An installed skill that is not a link into a clone runs setup from this copy.",
)
INSTALLER_NAME: str = "setup-standards.sh"

GUARANTEES: dict[str, str] = {
    "codex": "structural: the coding skill is in no directory Codex scans (~/.agents/skills, a repository's .agents/skills); the guard in AGENTS.md is advisory.",
    "claude": "advisory: review-standards shares ~/.claude/skills with the coding skill, so only the guard keeps the reviewer from it.",
    "copilot": "advisory: review-standards shares Copilot's skills directory with the coding skill, so only the guard keeps the reviewer from it.",
    "none": "no reviewer, so no review skill is installed.",
}
"""How well each review provider is kept from the coding skill (design section 6A): structurally only for Codex."""


@dataclass(frozen=True)
class InvalidBlock:
    """An instruction text whose markers do not form exactly one closed block, and what is wrong with them."""

    reason: str


@dataclass(frozen=True)
class Invalid:
    """A host or review target setup refuses to touch, because one of its files cannot be read or merged into."""

    host: Target
    path: Path
    reason: str


@dataclass(frozen=True)
class Settings:
    """A host's parsed settings file and the key that holds its default model."""

    path: Path
    key: str
    values: dict[str, Any]


@dataclass(frozen=True)
class HostFiles:
    """What planning read for one host: its folder, its instruction text and the block it records, and its settings."""

    host: Host
    folder: Path
    memory: str
    stored: ModelChoices | None
    settings: Settings | None
    notes: tuple[str, ...]

    @property
    def instructions(self) -> Path:
        """Return the host's instruction file."""
        return self.folder / self.host.instructions_name


@dataclass(frozen=True)
class Change:
    """A file in a host's home to write, with the part of it the user is shown; nothing but its path when ``shown`` is empty."""

    path: Path
    text: str
    shown: str


@dataclass(frozen=True)
class Plan:
    """One target's writes, the links it will not write through, what the summary should say about it, and, for a host, the models it records."""

    host: Target
    folder: Path
    changes: tuple[Change, ...]
    notes: tuple[str, ...] = ()
    skipped: tuple[Path, ...] = ()
    choices: ModelChoices | None = None


@dataclass(frozen=True)
class Module:
    """A skill setup installs: its directory name and the exact text of each file, keyed by its POSIX path inside."""

    name: str
    files: Mapping[str, str]


type Writes = tuple[tuple[Change, ...], tuple[str, ...]]
"""Changes to plan and notes for the summary."""


class Status(StrEnum):
    """What happened to a host, as the summary names it."""

    WRITTEN = "written"
    UNCHANGED = "nothing to change"
    DECLINED = "not written (declined)"
    INVALID = "skipped (invalid)"
    FAILED = "failed"
    DESELECTED = "still configured; delete the block to remove it"


@dataclass(frozen=True)
class Outcome:
    """A target's result: its status, the files written and skipped, notes, and whether the run must fail."""

    host: Target
    status: Status
    failed: bool = False
    written: tuple[Path, ...] = ()
    skipped: tuple[Path, ...] = ()
    notes: tuple[str, ...] = ()


def main(
    argv: list[str] | None = None,
    ask: Callable[[str], str] = input,
    home: Callable[[], Path] = Path.home,
    resolve: Callable[[Path], Path] = Path.resolve,
    environ: Mapping[str, str] = os.environ,
) -> int:
    """Ask for the hosts and their models, or take the defaults, and record them in each host's home.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.
        ask: Prompts the user and returns the reply; raises ``EOFError`` without one.
        home: Returns the home directory holding each host's folder.
        resolve: Returns where a path really leads, following symbolic links.
        environ: The environment, read for ``COPILOT_HOME`` and ``CODEX_HOME``.

    Returns:
        1 when a host or Codex's file was refused as invalid or failed to write, or
        when ``--yes`` skipped a file that links outside the home directory; otherwise 0.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="never ask; write the defaults only for hosts with no models recorded yet")
    parser.add_argument("--modules", type=Path, help="a folder holding one subfolder per skill to install")
    parser.add_argument("--installer", type=Path, help=f"the setup script to keep a copy of in ~/{INSTALLER.home_dir}")
    parser.add_argument("--repo", type=Path, help="the target repository's root, only read to check what Codex scans there; default: the current directory, as the setup script runs from it")
    args: argparse.Namespace = parser.parse_args(argv)

    root: Path = home()
    modules: dict[str, Module] = load_modules(args.modules)
    loaded: list[HostFiles | Invalid] = [load(host, root, environ) for host in HOSTS]
    default: tuple[Host, ...] = selected_hosts(configured_hosts(loaded), detected_hosts(root, environ))
    chosen: tuple[Host, ...] = default if args.yes else ask_hosts(default, ask)
    plans: list[Plan | Invalid] = [inside_home(plan_host(files, assume_yes=args.yes, ask=ask, modules=modules, resolve=resolve), root, resolve, assume_yes=args.yes, ask=ask) for files in loaded if files.host in chosen]
    report: list[str] = isolation(plans, root, args.repo or Path.cwd())
    shared: list[Plan | Invalid | None] = [plan_review_target(root, environ, plans, modules, resolve), plan_installer(args.installer, root)]
    plans.extend(inside_home(plan, root, resolve, assume_yes=args.yes, ask=ask) for plan in shared if plan is not None)
    outcomes: list[Outcome] = [*apply(plans, assume_yes=args.yes, ask=ask), *deselected(loaded, chosen)]
    print(summarize(outcomes, report))
    return 1 if any(outcome.failed for outcome in outcomes) else 0


def read(path: Path) -> str:
    """Return a file's exact text, line endings included, or "" when it does not exist."""
    return path.read_text(encoding="utf-8", newline="") if path.is_file() else ""


def holds(path: Path, text: str) -> bool:
    """Return whether the file ``path`` already holds exactly ``text``; an unreadable file does not."""
    try:
        return path.is_file() and path.read_bytes() == text.encode()
    except OSError:
        return False


def load_modules(folder: Path | None) -> dict[str, Module]:
    """Return each skill in ``folder``, one per subfolder, by name; none without a folder."""
    if folder is None:
        return {}
    return {skill.name: Module(skill.name, {path.relative_to(skill).as_posix(): read(path) for path in sorted(skill.rglob("*")) if path.is_file()}) for skill in sorted(folder.iterdir()) if skill.is_dir()}


def host_folder(host: Target, home: Path, environ: Mapping[str, str]) -> Path:
    """Return the folder holding the target's files: the one its environment variable names when set, else its folder in ``home``."""
    moved: str = environ.get(host.home_env, "") if host.home_env else ""
    return Path(moved) if moved else home / host.home_dir


def detected_hosts(home: Path, environ: Mapping[str, str]) -> tuple[Host, ...]:
    """Return the hosts whose home directory exists, in its usual place or where the environment moves it; no file is read."""
    return tuple(host for host in HOSTS if (home / host.home_dir).is_dir() or host_folder(host, home, environ).is_dir())


def configured_hosts(loaded: Iterable[HostFiles | Invalid]) -> tuple[Host, ...]:
    """Return the hosts whose instruction file holds exactly one closed block."""
    return tuple(files.host for files in loaded if isinstance(files, HostFiles) and files.stored is not None)


def selected_hosts(configured: tuple[Host, ...], detected: tuple[Host, ...]) -> tuple[Host, ...]:
    """Return the hosts to configure unasked: those configured, else those detected, else Claude Code."""
    return configured or detected or (CLAUDE_CODE,)


def ask_hosts(default: tuple[Host, ...], ask: Callable[[str], str]) -> tuple[Host, ...]:
    """Return the hosts the user names, asking again until every name is known; no names at all take ``default``."""
    names: str = ", ".join(host.name for host in HOSTS)
    while True:
        try:
            reply: str = ask(f"Hosts to configure ({names}) [{', '.join(host.name for host in default)}]: ")
        except EOFError:
            return default
        wanted: set[str] = {name for name in re.split(r"[\s,]+", reply.strip()) if name}
        unknown: list[str] = sorted(wanted - {host.name for host in HOSTS})
        if unknown:
            print(f"Unknown host {', '.join(unknown)}; answer one or more of {names}.")
        elif wanted:
            return tuple(host for host in HOSTS if host.name in wanted)
        else:
            return default


def load(host: Host, home: Path, environ: Mapping[str, str]) -> HostFiles | Invalid:
    """Read and parse every file setup may change for the host, or say which one it must not touch and why."""
    folder: Path = host_folder(host, home, environ)
    path: Path = folder / host.instructions_name
    try:
        memory: str = read(path)
    except (OSError, UnicodeDecodeError) as error:
        return Invalid(host, path, f"cannot be read ({error})")
    stored: ModelChoices | InvalidBlock | None = stored_choices(memory, host)
    if isinstance(stored, InvalidBlock):
        return Invalid(host, path, stored.reason)
    settings: Settings | Invalid | None = load_settings(host, folder)
    if isinstance(settings, Invalid):
        return settings
    usual: Path = home / host.home_dir / host.instructions_name
    # VS Code may not honour the variable (documented for Copilot CLI only), so a moved file is worth a warning.
    notes: tuple[str, ...] = () if path == usual else (f"{host.home_env} moves the file to {path}; {usual} is not written, and a surface that ignores {host.home_env}, such as VS Code, may read it instead.",)
    return HostFiles(host, folder, memory, stored, settings, notes)


def load_settings(host: Host, folder: Path) -> Settings | Invalid | None:
    """Return the host's parsed ``settings.json`` (empty when absent); None for a host whose settings setup never writes."""
    if host.settings_model_key is None:
        return None
    path: Path = folder / "settings.json"
    try:
        values: object = json.loads(read(path) or "{}")
    except (OSError, ValueError) as error:  # ValueError covers both invalid JSON and invalid UTF-8.
        return Invalid(host, path, f"cannot be parsed ({error})")
    if not isinstance(values, dict):
        return Invalid(host, path, "is not a JSON object")
    parsed: dict[str, Any] = values
    return Settings(path, host.settings_model_key, parsed)


def block_span(text: str, markers: Markers = MODELS) -> tuple[int, int] | InvalidBlock | None:
    """Return where the one closed block of the given markers starts and ends, markers included.

    Returns:
        None when the text holds neither marker; an ``InvalidBlock`` when its markers form
        anything but one start followed by one end, since merging into such a text could
        span, and replace, the user's own lines.
    """
    starts: int = text.count(markers.start)
    ends: int = text.count(markers.end)
    if starts > 1 or ends > 1:
        return InvalidBlock(f"{starts} start and {ends} end markers; it may hold one {markers.kind} block only")
    start: int = text.find(markers.start)
    end: int = text.find(markers.end)
    if start < 0 and end < 0:
        return None
    if start < 0:
        return InvalidBlock(f"{markers.end} has no {markers.start} before it")
    if end < 0:
        return InvalidBlock(f"{markers.start} has no {markers.end} after it")
    if end < start:
        return InvalidBlock(f"{markers.end} comes before {markers.start}")
    return (start, end + len(markers.end))


def render_block(choices: ModelChoices, host: Host = CLAUDE_CODE) -> str:
    """Return the host's models block, markers included, with no trailing newline; the host's coder guard is its last line."""
    lines: list[str] = [f"- {LABELS[field.name]}: `{getattr(choices, field.name)}`" for field in fields(choices)]
    return "\n".join([START, host.heading, "", *lines, "", host.guard, END])


def stored_choices(text: str, host: Host = CLAUDE_CODE) -> ModelChoices | InvalidBlock | None:
    """Return the choices an instruction text records, a missing line taking the host's default; None without a block, ``InvalidBlock`` for bad markers."""
    span: tuple[int, int] | InvalidBlock | None = block_span(text)
    if span is None or isinstance(span, InvalidBlock):
        return span
    block: str = text[span[0] : span[1]]
    found: dict[str, str] = {}
    name: str
    label: str
    for name, label in LABELS.items():
        match: re.Match[str] | None = re.search(rf"^- {re.escape(label)}: `([^`]*)`", block, re.MULTILINE)
        if match:
            found[name] = match.group(1)
    return replace(host.defaults, **found)


def merge_block(text: str, block: str, markers: Markers = MODELS) -> str:
    """Return the text with its block of the given markers replaced by ``block``, or with ``block`` appended when it has none.

    Raises:
        ValueError: The text's markers are invalid; ``load`` and ``review_scope`` refuse such a file before any merge, so this guards only against a new caller.
    """
    span: tuple[int, int] | InvalidBlock | None = block_span(text, markers)
    start: int
    end: int
    match span:
        case InvalidBlock():
            raise ValueError(span.reason)
        case (start, end):
            return text[:start] + block + text[end:]
        case _:  # no block yet
            if not text:
                return block + "\n"
            return text + ("\n" if text.endswith("\n") else "\n\n") + block + "\n"


def merge_model(settings: Mapping[str, Any], model: str, *, overwrite: bool, key: str = "model") -> dict[str, Any]:
    """Return the settings with ``model`` under ``key``, keeping an existing one unless ``overwrite``."""
    if key in settings and not overwrite:
        return dict(settings)
    return {**settings, key: model}


def ask_choices(defaults: ModelChoices, ask: Callable[[str], str], host: Host = CLAUDE_CODE) -> ModelChoices:
    """Ask each of the host's questions, offering ``defaults``; the review model's default follows a changed provider."""
    print(f"\nModels for {host.name}:")
    coordinator: str = answer("Coordinator model, the main session's default; it runs the tests", host.suggestions["models"], defaults.coordinator, ask)
    coding: str = answer("Coding model, for agents that write code", host.suggestions["models"], defaults.coding, ask)
    provider: str = ask_provider(defaults.reviewer_provider, ask, host)
    model_default: str = defaults.reviewer_model if provider == defaults.reviewer_provider else host.suggestions[provider][0]
    reviewer: str = answer(f"Adversarial code-review model ({provider})", host.suggestions[provider], model_default, ask)
    return ModelChoices(coordinator=coordinator, coding=coding, reviewer_provider=provider, reviewer_model=reviewer)


def answer(question: str, suggestions: tuple[str, ...], default: str, ask: Callable[[str], str]) -> str:
    """Return the user's reply, or ``default`` for an empty reply or none at all."""
    try:
        reply: str = ask(f"{question} (e.g. {', '.join(suggestions)}) [{default}]: ").strip()
    except EOFError:
        return default
    return reply or default


def ask_provider(default: str, ask: Callable[[str], str], host: Host) -> str:
    """Return the review provider, asking again until the reply names one the host offers."""
    while True:
        provider: str = answer("Adversarial code-review provider", host.providers, default, ask).lower()
        if provider in host.providers:
            return provider
        print(f"Answer {' or '.join(host.providers)}.")


def plan_host(files: HostFiles | Invalid, *, assume_yes: bool, ask: Callable[[str], str], modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Plan | Invalid:
    """Return the host's writes: none for an invalid host; else a settings repair only under ``assume_yes`` with a recorded block, or those recording the answers, and its skills.

    ``assume_yes`` answers with the host's defaults; otherwise the questions are asked,
    offering the recorded answers.
    """
    if isinstance(files, Invalid):
        return files
    choices: ModelChoices
    plan: Plan
    if assume_yes and files.stored is not None:
        # The block stays as it is; only a settings file missing its model is filled in from it.
        choices = files.stored
        plan = pending_changes(files, choices, overwrite=False, keep_block=True)
    else:
        choices = files.host.defaults if assume_yes else ask_choices(files.stored or files.host.defaults, ask, files.host)
        # Only a re-run whose user picked another coordinator replaces a settings model.
        overwrite: bool = files.stored is not None and choices.coordinator != files.stored.coordinator
        plan = pending_changes(files, choices, overwrite=overwrite, keep_block=False)
    changes: tuple[Change, ...]
    notes: tuple[str, ...]
    changes, notes = host_skills(files.host, files.folder / "skills", choices, modules, resolve)
    return replace(plan, changes=(*plan.changes, *changes), notes=(*plan.notes, *notes))


def host_skills(host: Host, skills: Path, choices: ModelChoices, modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Writes:
    """Return the writes installing the host's skills in ``skills``: the coding skill always, the review skill when the host reviews its own code, else a note on a copy no longer wanted."""
    coding: Writes = install(modules.get(CODING_SKILL), skills, resolve)
    review: Writes = install(modules.get(REVIEW_SKILL), skills, resolve) if choices.reviewer_provider == host.own_reviewer else ((), unwanted(skills / REVIEW_SKILL))
    return (*coding[0], *review[0]), (*coding[1], *review[1])


def install(module: Module | None, skills: Path, resolve: Callable[[Path], Path]) -> Writes:
    """Return the writes installing ``module`` as a directory in ``skills``, or why that directory is left as it is.

    Only a missing directory, or one holding ``.managed-by``, is written, and the marker is
    its first file, so an interrupted install is still setup's to finish. A directory that
    is a link, or that setup did not install, is reported and never changed. Files already
    up to date are left out; files the module no longer holds are left in place.
    """
    if module is None:
        return (), ()
    folder: Path = skills / module.name
    real: Path = resolve(folder)
    if real != resolve(skills) / module.name:
        return (), (f"{folder} is a link to {real}; not managed by setup; left as is.",)
    if folder.exists() and not (folder / MANAGED_BY).is_file():
        return (), (f"{folder} is not managed by setup; left as is.",)
    wanted: dict[str, str] = {MANAGED_BY: MANAGED_TEXT, **module.files}
    return tuple(Change(folder / name, text, "") for name, text in wanted.items() if not holds(folder / name, text)), ()


def unwanted(folder: Path) -> tuple[str, ...]:
    """Return a note when ``folder`` is a skill setup installed that no chosen host wants there any more; it is never removed."""
    return (f"{folder} was installed by setup and is no longer wanted; delete it to remove it.",) if (folder / MANAGED_BY).is_file() else ()


def plan_review_target(home: Path, environ: Mapping[str, str], plans: Iterable[Plan | Invalid], modules: Mapping[str, Module], resolve: Callable[[Path], Path]) -> Plan | Invalid | None:
    """Return Codex's writes when a chosen host reviews with it, Codex's name being that provider; otherwise None.

    The writes are the reviewer guard block in its instruction file and the review skill in
    its skills directory. An override file beside the instruction file, which the reviewer
    reads instead, is reported.
    """
    target: ReviewTarget = CODEX
    if not any(isinstance(plan, Plan) and plan.choices is not None and plan.choices.reviewer_provider == target.name for plan in plans):
        return None
    folder: Path = host_folder(target, home, environ)
    scope: tuple[Change, ...] | Invalid = review_scope(target, folder)
    if isinstance(scope, Invalid):
        return scope
    changes: tuple[Change, ...]
    notes: tuple[str, ...]
    changes, notes = install(modules.get(REVIEW_SKILL), home / target.skills_dir, resolve)
    override: Path = folder / target.override_name
    if override.exists():
        notes = (f"{override} exists, and Codex reads it instead of {folder / target.instructions_name}, so the review scope block will be ignored.", *notes)
    return Plan(target, folder, (*scope, *changes), notes)


def review_scope(target: ReviewTarget, folder: Path) -> tuple[Change, ...] | Invalid:
    """Return the write putting the reviewer guard block in the target's instruction file, none when it is already there, or why the file is refused."""
    path: Path = folder / target.instructions_name
    try:
        text: str = read(path)
    except (OSError, UnicodeDecodeError) as error:
        return Invalid(target, path, f"cannot be read ({error})")
    span: tuple[int, int] | InvalidBlock | None = block_span(text, REVIEW)
    if isinstance(span, InvalidBlock):
        return Invalid(target, path, span.reason)
    block: str = "\n".join([REVIEW.start, target.heading, "", target.guard, REVIEW.end])
    merged: str = merge_block(text, block, REVIEW)
    return () if merged == text else (Change(path, merged, block),)


def plan_installer(source: Path | None, home: Path) -> Plan | None:
    """Return the write keeping a copy of the setup script where an installed skill finds it; None when no script was named."""
    if source is None:
        return None
    folder: Path = home / INSTALLER.home_dir
    path: Path = folder / INSTALLER_NAME
    text: str = read(source)
    return Plan(INSTALLER, folder, () if holds(path, text) else (Change(path, text, ""),))


def isolation(plans: Iterable[Plan | Invalid], home: Path, repo: Path) -> list[str]:
    """Return how well each chosen host's reviewer is kept from the coding skill, then what design section 6A leaves overlapping for the chosen hosts.

    The Codex guarantee is checked rather than assumed: a coding skill already in a
    directory Codex scans, ``.agents/skills`` in the home directory or in the target
    repository ``repo``, breaks it. With no Codex reviewer, a review skill setup once put
    in the home one is listed, never removed.
    """
    providers: dict[str, str] = {plan.host.name: plan.choices.reviewer_provider for plan in plans if isinstance(plan, Plan) and plan.choices is not None}
    lines: list[str] = [f"{name}, reviewer {provider}: {GUARANTEES.get(provider, 'unknown provider, so no review skill is installed.')}" for name, provider in providers.items()]
    skills: Path = home / CODEX.skills_dir
    codex: bool = CODEX.name in providers.values()
    if not codex:
        lines.extend(unwanted(skills / REVIEW_SKILL))
    else:
        scanned: tuple[Path, ...] = (skills / CODING_SKILL, repo / CODEX.skills_dir / CODING_SKILL)
        lines.extend(f"not structural while {visible} exists: Codex scans that directory and setup does not manage it; remove it by hand." for visible in scanned if visible.is_symlink() or visible.exists())
    if codex and COPILOT.name in providers:
        lines.append("overlap: Copilot (CLI and VS Code) also scans ~/.agents/skills, so it sees review-standards.")
    if {CLAUDE_CODE.name, COPILOT.name} <= providers.keys():
        lines.append("overlap: VS Code's Copilot also reads ~/.claude/skills, so it sees the Claude Code copy of python-code-standards.")
    return lines


def pending_changes(files: HostFiles, choices: ModelChoices, *, overwrite: bool, keep_block: bool) -> Plan:
    """Return the plan recording ``choices``, leaving out a file it would not change and, with ``keep_block``, the instruction file."""
    changes: list[Change] = []
    notes: list[str] = list(files.notes)
    if keep_block:
        notes.append(f"Kept the models in {files.instructions}; re-run setup without -y to change them.")
    else:
        block: str = render_block(choices, files.host)
        merged: str = merge_block(files.memory, block)
        if merged != files.memory:
            changes.append(Change(files.instructions, merged, block))
    settings: Settings | None = files.settings
    if settings is not None:
        updated: dict[str, Any] = merge_model(settings.values, choices.coordinator, overwrite=overwrite, key=settings.key)
        if updated != settings.values:
            changes.append(Change(settings.path, json.dumps(updated, indent=2) + "\n", f'"{settings.key}": "{choices.coordinator}"'))
        elif settings.values[settings.key] != choices.coordinator:
            notes.append(f'{settings.path} keeps "{settings.key}": "{settings.values[settings.key]}"; edit it by hand to use {choices.coordinator}.')
    return Plan(files.host, files.folder, tuple(changes), tuple(notes), choices=choices)


def inside_home(plan: Plan | Invalid, home: Path, resolve: Callable[[Path], Path], *, assume_yes: bool, ask: Callable[[str], str]) -> Plan | Invalid:
    """Return the plan keeping each change whose path resolves inside ``home`` or a folder the environment named, and each through an outside link the user confirmed.

    A file linked out of the home directory, such as a ``CLAUDE.md`` kept in a repository,
    is never written unasked: ``assume_yes`` skips it, and otherwise it needs its own yes.
    A host folder moved out of ``home`` by its environment variable counts as inside; the
    usual folder does not, since it may itself be a link into a repository.
    """
    if isinstance(plan, Invalid):
        return plan
    boundary: Path = resolve(home)
    moved: bool = plan.folder != home / plan.host.home_dir
    boundaries: tuple[Path, ...] = (boundary, resolve(plan.folder)) if moved else (boundary,)
    allowed: list[Change] = []
    skipped: list[Path] = []
    change: Change
    for change in plan.changes:
        target: Path = resolve(change.path)
        if any(target.is_relative_to(inside) for inside in boundaries):
            allowed.append(change)
        elif assume_yes:
            print(f"\n{change.path} is a link to {target}, outside {boundary}; -y never writes through it. Skipped; re-run setup without -y to confirm it.", file=sys.stderr)
            skipped.append(change.path)
        elif confirmed(f"\n{change.path} is a link to {target}, outside {boundary}.\nWrite through the link to {target}? [y/N] ", ask):
            allowed.append(change)
        else:
            print(f"  skip     {change.path}")
            skipped.append(change.path)
    return replace(plan, changes=tuple(allowed), skipped=tuple(skipped))


def apply(plans: list[Plan | Invalid], *, assume_yes: bool, ask: Callable[[str], str]) -> list[Outcome]:
    """Show every host's changes, then write them host by host once confirmed; ``assume_yes`` confirms unasked.

    A host whose write fails is reported and the others are still written; hosts
    already written are not rolled back.
    """
    plan: Plan | Invalid
    change: Change
    for plan in plans:
        if isinstance(plan, Invalid):
            print(f"\n{plan.path}: {plan.reason}. Nothing written for {plan.host.name}; repair the file, then re-run setup.", file=sys.stderr)
            continue
        for change in plan.changes:
            print(f"\n  write    {change.path}\n{change.shown}" if change.shown else f"  write    {change.path}")
    waiting: bool = any(isinstance(plan, Plan) and plan.changes for plan in plans)
    if not waiting:
        print("\nModels: nothing to change.")
    write: bool = waiting and (assume_yes or confirmed("\nWrite the changes above? [y/N] ", ask))
    if waiting and not write:
        print("Not written; re-run setup to choose the models again.")
    return [settle(plan, write=write, assume_yes=assume_yes) for plan in plans]


def settle(plan: Plan | Invalid, *, write: bool, assume_yes: bool) -> Outcome:
    """Write one host's changes when ``write`` holds, and return what became of the host.

    A link skipped under ``assume_yes`` fails the run, since the user was never asked.
    """
    if isinstance(plan, Invalid):
        return Outcome(plan.host, Status.INVALID, failed=True, notes=(f"{plan.path}: {plan.reason}",))
    refused: bool = assume_yes and bool(plan.skipped)
    if not plan.changes:
        return Outcome(plan.host, Status.UNCHANGED, failed=refused, skipped=plan.skipped, notes=plan.notes)
    if not write:
        return Outcome(plan.host, Status.DECLINED, skipped=plan.skipped, notes=plan.notes)
    written: list[Path] = []
    change: Change
    for change in plan.changes:
        try:
            replace_file(change.path, change.text)
        except OSError as error:
            print(f"\n{change.path}: not written ({error}).", file=sys.stderr)
            return Outcome(plan.host, Status.FAILED, failed=True, written=tuple(written), skipped=plan.skipped, notes=(*plan.notes, f"{change.path}: {error}"))
        written.append(change.path)
    return Outcome(plan.host, Status.WRITTEN, failed=refused, written=tuple(written), skipped=plan.skipped, notes=plan.notes)


def replace_file(path: Path, text: str) -> None:
    """Write ``text`` to the file ``path`` leads to, through a temporary file beside it, so an interruption leaves the old file or the new one.

    The temporary file takes the old file's permission bits and is removed when the replace fails.
    """
    target: Path = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle: int
    temporary: str
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    stream: TextIO
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        if target.is_file():
            shutil.copymode(target, temporary)
        Path(temporary).replace(target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def deselected(loaded: Iterable[HostFiles | Invalid], chosen: tuple[Host, ...]) -> list[Outcome]:
    """Return an outcome for each configured host the user did not choose, whose block is left as it is."""
    return [Outcome(files.host, Status.DESELECTED, notes=(str(files.instructions),)) for files in loaded if isinstance(files, HostFiles) and files.stored is not None and files.host not in chosen]


def summarize(outcomes: list[Outcome], report: Sequence[str] = ()) -> str:
    """Return the per-target summary (status, files written and skipped, notes, and, once configured, its gate note), then the review isolation ``report``."""
    lines: list[str] = ["\nModels summary:"]
    outcome: Outcome
    for outcome in outcomes:
        lines.append(f"{outcome.host.name}: {outcome.status}")
        lines.extend(f"  wrote    {path}" for path in outcome.written)
        lines.extend(f"  skipped  {path} (link outside home)" for path in outcome.skipped)
        lines.extend(f"  {note}" for note in outcome.notes)
        if outcome.status in {Status.WRITTEN, Status.UNCHANGED}:
            lines.extend(f"  {line}" for line in outcome.host.gate_note.splitlines())
    if report:
        lines.append("Review isolation (instructions narrow what a model loads; they do not forbid it):")
        lines.extend(f"  {line}" for line in report)
    return "\n".join(lines)


def confirmed(question: str, ask: Callable[[str], str]) -> bool:
    """Return whether the user answered yes; no answer at all means no."""
    try:
        reply: str = ask(question)
    except EOFError:
        return False
    return reply.strip().lower() in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
