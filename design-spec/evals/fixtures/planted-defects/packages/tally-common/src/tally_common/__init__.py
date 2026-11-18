"""Shared types for tally: the order record, the order source port, and the error family."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Order:
    """One order as read from the source.

    Attributes:
        order_id: The source's identifier; a later row with the same id replaces an earlier one.
        day: The day the order was placed.
        amount: The order total in the store currency: whole cents, never negative, below 10**12.
    """

    order_id: str
    day: date
    amount: Decimal


class OrderSource(Protocol):
    """Anything that can read the orders stored at a path."""

    def read(self, path: Path) -> list[Order]:
        """Return every order stored at ``path``, in source order."""
        ...


class TallyError(Exception):
    """A refused input, such as a malformed row. The CLI catches it once per run."""
