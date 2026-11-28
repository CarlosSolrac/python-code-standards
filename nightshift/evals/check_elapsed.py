"""Check the start, finish and elapsed times of a nightshift log.

A log's header line carries ``Started``, ``Last update`` and ``Finished``; its Morning summary
carries ``Started``, ``Completed`` and ``Elapsed``. This module checks that the summary copies the
header's times and that ``Elapsed`` equals ``Finished`` minus ``Started`` with UTC offsets applied,
following the *Log format* section of ``nightshift/SKILL.md``.

Run as ``python check_elapsed.py <log-path>``: prints one problem per line and exits 1 when any
problem is found, otherwise prints nothing and exits 0.
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

IN_PROGRESS: str = "—"
WAITING: str = "— (waiting for Codex)"
APPROX: str = " (approx.)"
SO_FAR: str = " (so far)"
HEADER: re.Pattern[str] = re.compile(r"^Started: (.*) · Last update: .* · Finished: (.*)$", re.MULTILINE)
SUMMARY: re.Pattern[str] = re.compile(r"^Started: (.*) · Completed: (.*) · Elapsed: (.*)$", re.MULTILINE)
STAMP: re.Pattern[str] = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: ([+-])(\d{2}):?(\d{2}))?")
ELAPSED: re.Pattern[str] = re.compile(r"(\d+)h ([0-5]\d)m")


@dataclass(frozen=True)
class Stamp:
    """A log timestamp: local wall-clock time and its UTC offset, which a legacy ``Started`` lacks."""

    local: datetime
    offset: timedelta | None

    def utc(self, fallback: timedelta) -> datetime:
        """Return the stamp as naive UTC, reading it at ``fallback`` when it carries no offset."""
        offset: timedelta
        offset = fallback if self.offset is None else self.offset
        return self.local - offset


@dataclass(frozen=True)
class Night:
    """A night's times as the header records them.

    ``elapsed`` is ``None`` while the night is in progress; ``legacy`` marks a ``Started`` without offset.
    """

    started: str
    finished: str
    elapsed: timedelta | None
    legacy: bool


def _parse_stamp(text: str) -> Stamp | None:
    """Return the timestamp in ``text``, or ``None`` when it is not ``YYYY-MM-DD HH:MM [±HHMM|±HH:MM]``."""
    match: re.Match[str] | None
    match = STAMP.fullmatch(text)
    if match is None:
        return None
    local: datetime
    try:
        local = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    if match.group(2) is None:
        return Stamp(local, None)
    offset: timedelta
    offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
    return Stamp(local, -offset if match.group(2) == "-" else offset)


def _read_header(text: str) -> Night | list[str]:
    """Return the header's times, or the ``header:`` problems that prevent reading them."""
    match: re.Match[str] | None
    match = HEADER.search(text)
    if match is None:
        return ["header: Started · Last update · Finished line missing"]
    started_text: str
    finished_text: str
    started_text, finished_text = match.group(1).strip(), match.group(2).strip()
    problems: list[str]
    problems = []
    started: Stamp | None
    started = _parse_stamp(started_text)
    if started is None:
        problems.append(f"header: Started {started_text!r} is not a YYYY-MM-DD HH:MM ±HHMM timestamp")
    if finished_text == IN_PROGRESS:
        return problems or Night(started_text, finished_text, None, started is not None and started.offset is None)
    finished: Stamp | None
    finished = _parse_stamp(finished_text)
    if finished is None:
        problems.append(f"header: Finished {finished_text!r} is not a YYYY-MM-DD HH:MM ±HHMM timestamp")
    elif finished.offset is None:
        problems.append(f"header: Finished {finished_text!r} has no UTC offset")
    if problems or started is None or finished is None or finished.offset is None:
        return problems
    elapsed: timedelta
    elapsed = finished.utc(finished.offset) - started.utc(finished.offset)
    if elapsed < timedelta(0):
        return [f"header: Finished {finished_text!r} is earlier than Started {started_text!r}"]
    return Night(started_text, finished_text, elapsed, started.offset is None)


def _format_elapsed(elapsed: timedelta) -> str:
    """Return ``elapsed`` as ``Xh YYm``."""
    minutes: int
    minutes = int(elapsed.total_seconds()) // 60
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _check_elapsed(value: str, elapsed: timedelta, legacy: bool) -> list[str]:
    """Return the ``summary:`` problems with a finished night's Elapsed value; a legacy one must end ``(approx.)``."""
    problems: list[str]
    problems = []
    if legacy:
        if not value.endswith(APPROX):
            problems.append(f"summary: Elapsed {value!r} must end with {APPROX.strip()!r} because Started has no UTC offset")
        value = value.removesuffix(APPROX)
    expected: str
    expected = _format_elapsed(elapsed)
    if ELAPSED.fullmatch(value) is None:
        problems.append(f"summary: Elapsed {value!r} is not in Xh YYm form")
    elif value != expected:
        problems.append(f"summary: Elapsed is {value!r}, expected {expected!r}")
    return problems


def _check_summary(text: str, night: Night) -> list[str]:
    """Return the ``summary:`` problems of the Morning summary's times line against the header."""
    match: re.Match[str] | None
    match = SUMMARY.search(text)
    if match is None:
        return ["summary: Started · Completed · Elapsed line missing"]
    started: str
    completed: str
    elapsed: str
    started, completed, elapsed = (group.strip() for group in match.groups())
    problems: list[str]
    problems = []
    if started != night.started:
        problems.append(f"summary: Started {started!r} differs from the header's {night.started!r}")
    if night.elapsed is None:
        if completed != WAITING:
            problems.append(f"summary: Completed {completed!r} must be {WAITING!r} while Finished is {IN_PROGRESS!r}")
        if not elapsed.endswith(SO_FAR):
            problems.append(f"summary: Elapsed {elapsed!r} must end with {SO_FAR.strip()!r} while the night is in progress")
        return problems
    if completed != night.finished:
        problems.append(f"summary: Completed {completed!r} differs from the header's Finished {night.finished!r}")
    return problems + _check_elapsed(elapsed, night.elapsed, night.legacy)


def check_log(text: str) -> list[str]:
    """Return the timing problems found in a nightshift log.

    Args:
        text: The whole log file's contents.

    Returns:
        One message per problem, each starting with ``header:`` or ``summary:``; empty when the
        log's times are consistent. Header problems are reported alone, since the summary is
        checked against the header.
    """
    night: Night | list[str]
    night = _read_header(text)
    if isinstance(night, list):
        return night
    return _check_summary(text, night)


def main(argv: list[str] | None = None) -> int:
    """Check the log file named by the single argument and print its problems.

    Args:
        argv: The command-line arguments after the program name, holding exactly one log path;
            ``None`` reads them from ``sys.argv``.

    Returns:
        0 when the log has no problems, 1 when it has any.
    """
    path: str
    (path,) = sys.argv[1:] if argv is None else argv
    problems: list[str]
    problems = check_log(Path(path).read_text(encoding="utf-8"))
    problem: str
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
