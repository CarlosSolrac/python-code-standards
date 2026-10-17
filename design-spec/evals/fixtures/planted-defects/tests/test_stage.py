from datetime import date
from decimal import Decimal
from pathlib import Path

from tally_common import Order
from tally_stage import load_orders


class _FakeSource:
    def __init__(self, orders: list[Order]) -> None:
        self.orders: list[Order] = orders
        self.paths: list[Path] = []

    def read(self, path: Path) -> list[Order]:
        self.paths.append(path)
        return self.orders


def test_load_orders_reads_the_given_path_from_the_source() -> None:
    orders: list[Order] = [Order("A", date(2026, 10, 1), Decimal(1))]
    source: _FakeSource = _FakeSource(orders)
    assert load_orders(source, Path("orders.csv")) == orders
    assert source.paths == [Path("orders.csv")]
