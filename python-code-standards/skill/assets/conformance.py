"""Example module demonstrating the house Python style.

Loads rows from DuckDB and summarizes them, exercising the declaration rule
against every syntactic form the standards care about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import duckdb

logger: logging.Logger = logging.getLogger(__name__)

SELECT_EVENTS: str = """
SELECT
    event_id
  , event_name
  , event_count
FROM events
WHERE event_name = ?
"""


class EventCounter:
    """Mutable accumulator, declared in the class body rather than in ``__init__``.

    A plain class is deliberate here: a dataclass would satisfy the attribute rule
    by construction, so this demonstrates the rule where it actually costs
    something.
    """

    total: int
    seen: set[str]

    def __init__(self) -> None:
        """Start empty."""
        self.total = 0
        self.seen = set()

    def add(self, name: str, count: int) -> None:
        """Record one event.

        Args:
            name: Event name.
            count: Occurrences to add.
        """
        self.total += count
        self.seen.add(name)


def classify(payload: object) -> str:
    """Describe a payload using structural pattern matching.

    Match captures are bindings, so each is declared before the statement.

    Args:
        payload: Any decoded value.

    Returns:
        A short description of the payload's shape.
    """
    head: object
    rest: list[object]
    name: str
    other: object
    match payload:
        case [head, *rest]:
            return f"sequence of {len(rest) + 1} starting with {head!r}"
        case {"name": name}:
            return f"mapping for {name}"
        case other:
            return f"scalar {type(other).__name__}"


@dataclass(frozen=True)
class EventSummary:
    """Aggregated counts for a single named event."""

    name: str
    total: int


def summarize(conn: duckdb.DuckDBPyConnection, name: str) -> EventSummary:
    """Return the aggregate count for a named event.

    Args:
        conn: Open DuckDB connection.
        name: Event name to filter on, bound as a parameter.

    Returns:
        The aggregated summary for the requested event.
    """
    rows: list[tuple[int, str, int]] = conn.execute(SELECT_EVENTS, [name]).fetchall()

    total: int = 0
    row: tuple[int, str, int]
    for row in rows:
        total += row[2]

    logger.debug("summarized event=%s rows=%d", name, len(rows))
    return EventSummary(name=name, total=total)


def write_report(path: Path, summaries: dict[str, int]) -> None:
    """Write one summary per line to the given path.

    Args:
        path: Destination file.
        summaries: Mapping of event name to total count.
    """
    handle: TextIO
    with path.open("w", encoding="utf-8") as handle:
        key: str
        value: int
        for key, value in summaries.items():
            handle.write(f"{key}={value}\n")
