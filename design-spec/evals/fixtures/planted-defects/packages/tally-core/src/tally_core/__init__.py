"""Revenue arithmetic: pure functions, no I/O."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from tally_common import Order


def daily_revenue(orders: list[Order]) -> list[dict[str, object]]:
    """Total each day's orders, earliest day first, counting each order id once.

    A later order with the same id replaces the earlier one, so a corrected order is not counted twice.
    Each row has the keys ``day`` (an ISO date) and ``revenue`` (a decimal string).
    """
    latest: dict[str, Order] = {order.order_id: order for order in orders}
    totals: defaultdict[date, Decimal] = defaultdict(Decimal)
    order: Order
    for order in latest.values():
        totals[order.day] += order.amount
    return [{"day": day.isoformat(), "revenue": str(total)} for day, total in sorted(totals.items())]
