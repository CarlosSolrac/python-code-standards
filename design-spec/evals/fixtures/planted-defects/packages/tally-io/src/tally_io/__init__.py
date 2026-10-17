"""CSV adapters: read orders, write the daily revenue report."""

import csv
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from tally_common import Order, TallyError

_HEADER: list[str] = ["order_id", "day", "amount"]
# Whole cents below a trillion: a day total then needs more than 10**14 orders to outgrow the 28 digits of the default decimal context.
_MAX_AMOUNT: Decimal = Decimal(10) ** 12
_CENT: Decimal = Decimal("0.01")


class CsvOrders:
    """Reads orders from a CSV file with the header ``order_id,day,amount``."""

    def read(self, path: Path) -> list[Order]:
        """Return every order in ``path``, in file order.

        Raises:
            TallyError: The file cannot be read, is not well-formed CSV (for example a field over the csv module's size limit), or lacks
                the header, or a row lacks a column, has a day that is not an ISO date, or an amount that is not a non-negative number
                of whole cents below 10**12.
        """
        handle: TextIO
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader: csv.DictReader[str] = csv.DictReader(handle)
                try:
                    if reader.fieldnames != _HEADER:
                        header: str = f"line 1: expected the header {','.join(_HEADER)}, found {reader.fieldnames}"
                        raise TallyError(header)
                    # line_num is the physical line the reader has reached, so a quoted line break does not shift the reported line.
                    return [_parse(row, reader.line_num) for row in reader]
                except csv.Error as error:
                    # The reader raises before it counts the record it was parsing, so line_num + 1 is the line that record starts on.
                    malformed: str = f"line {reader.line_num + 1}: {error}"
                    raise TallyError(malformed) from error
        except (OSError, UnicodeDecodeError) as error:
            unreadable: str = f"cannot read {path}: {error}"
            raise TallyError(unreadable) from error


def _parse(row: dict[str, str], line: int) -> Order:
    """Turn one CSV row into an order, refusing anything that breaks the order invariants."""
    if len(row) != len(_HEADER):  # csv.DictReader files surplus fields under one extra key
        surplus: str = f"line {line}: more than {len(_HEADER)} fields"
        raise TallyError(surplus)
    try:
        order_id: str = row["order_id"]
        day: date = date.fromisoformat(row["day"])
        amount: Decimal = Decimal(row["amount"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        message: str = f"line {line}: {error!r}"
        raise TallyError(message) from error
    if not amount.is_finite() or amount < 0 or amount >= _MAX_AMOUNT or amount != amount.quantize(_CENT):
        refused: str = f"line {line}: amount {amount} is not a non-negative number of whole cents below {_MAX_AMOUNT}"
        raise TallyError(refused)
    return Order(order_id=order_id, day=day, amount=amount)


def write_report(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    """Write the daily revenue rows to ``path`` as CSV with the header ``day,revenue``.

    Raises:
        TallyError: ``path`` cannot be written.
    """
    handle: TextIO
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer: csv.DictWriter[str] = csv.DictWriter(handle, fieldnames=["day", "revenue"])
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        unwritable: str = f"cannot write {path}: {error.strerror}"
        raise TallyError(unwritable) from error
