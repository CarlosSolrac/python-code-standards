"""Tests for the statskit descriptive statistics helpers."""

import pytest

from statskit import mean, variance


def test_mean_of_values() -> None:
    assert mean([1.0, 2.0, 6.0]) == pytest.approx(3.0)


def test_mean_of_empty_sequence_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        mean([])


def test_variance_of_values() -> None:
    assert variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == pytest.approx(4.0)


def test_variance_of_empty_sequence_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        variance([])
