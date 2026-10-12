"""Tests for the statskit descriptive statistics helpers."""

import pytest

from statskit import mean


def test_mean_of_values() -> None:
    assert mean([1.0, 2.0, 6.0]) == pytest.approx(3.0)


def test_mean_of_empty_sequence_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        mean([])
