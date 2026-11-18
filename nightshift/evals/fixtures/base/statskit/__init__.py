"""Small descriptive statistics helpers for sequences of floats."""

from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of ``values``.

    Raises:
        ValueError: ``values`` is empty.
    """
    if not values:
        msg: str = "mean() of an empty sequence"
        raise ValueError(msg)
    return sum(values) / len(values)
