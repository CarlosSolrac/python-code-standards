"""Loading stage: the step between the CLI and the order source."""

from pathlib import Path

from tally_common import Order, OrderSource


def load_orders(source: OrderSource, path: Path) -> list[Order]:
    """Load the orders the run will total."""
    return source.read(path)
