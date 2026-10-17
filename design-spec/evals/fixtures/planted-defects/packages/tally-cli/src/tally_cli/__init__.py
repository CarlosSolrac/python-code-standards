"""Command line entry point: ``tally <orders.csv> <report.csv>``."""

import sys
from pathlib import Path

from tally_common import Order, TallyError
from tally_core import daily_revenue
from tally_io import CsvOrders, write_report
from tally_stage import load_orders

_USAGE: str = "usage: tally <orders.csv> <report.csv>\n"
_PATHS: int = 2


def main(argv: list[str] | None = None) -> int:
    """Total daily revenue from an orders CSV into a report CSV.

    Returns:
        0 when the report is written, 1 when the input is refused, 2 on a usage error.
    """
    args: list[str] = sys.argv[1:] if argv is None else argv
    if len(args) != _PATHS:
        sys.stderr.write(_USAGE)
        return 2
    try:
        orders: list[Order] = load_orders(CsvOrders(), Path(args[0]))
        write_report(daily_revenue(orders), Path(args[1]))
    except TallyError as error:
        sys.stderr.write(f"refused: {error}\n")
        return 1
    return 0
