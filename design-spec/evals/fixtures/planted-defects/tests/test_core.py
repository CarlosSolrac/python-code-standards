from datetime import date
from decimal import Decimal

from tally_common import Order
from tally_core import daily_revenue


def test_daily_revenue_totals_each_day_earliest_first() -> None:
    orders: list[Order] = [Order("B", date(2026, 10, 2), Decimal(4)), Order("A", date(2026, 10, 1), Decimal("1.5")), Order("C", date(2026, 10, 1), Decimal(2))]
    assert daily_revenue(orders) == [{"day": "2026-10-01", "revenue": "3.5"}, {"day": "2026-10-02", "revenue": "4"}]


def test_daily_revenue_counts_a_repeated_order_id_once_using_the_later_row() -> None:
    orders: list[Order] = [Order("A", date(2026, 10, 1), Decimal(5)), Order("A", date(2026, 10, 1), Decimal(7))]
    assert daily_revenue(orders) == [{"day": "2026-10-01", "revenue": "7"}]


def test_daily_revenue_of_no_orders_is_empty() -> None:
    assert daily_revenue([]) == []
