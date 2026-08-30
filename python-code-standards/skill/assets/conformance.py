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
