from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from tally_common import Order, TallyError
from tally_io import CsvOrders, write_report


def _csv(tmp_path: Path, text: str) -> Path:
    path: Path = tmp_path / "orders.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_read_returns_orders_in_file_order(tmp_path: Path) -> None:
    path: Path = _csv(tmp_path, "order_id,day,amount\nA,2026-10-01,10.50\nB,2026-10-02,4\n")
    assert CsvOrders().read(path) == [Order("A", date(2026, 10, 1), Decimal("10.50")), Order("B", date(2026, 10, 2), Decimal(4))]


@pytest.mark.parametrize(
    "body",
    ["A,2026-13-01,1\n", "A,2026-10-01,ten\n", "A,2026-10-01,-1\n", "A,2026-10-01\n", "A,2026-10-01,NaN\n", "A,2026-10-01,Infinity\n", "A,2026-10-01,2,000\n", "A,2026-10-01,1000000000000\n", "A,2026-10-01,0.001\n"],
    ids=["bad-day", "bad-amount", "negative", "missing-column", "nan", "infinite", "extra-field", "too-large", "below-a-cent"],
)
def test_read_refuses_a_bad_row_with_its_line(tmp_path: Path, body: str) -> None:
    path: Path = _csv(tmp_path, "order_id,day,amount\n" + body)
    with pytest.raises(TallyError, match="line 2"):
        CsvOrders().read(path)


def test_read_names_the_physical_line_after_a_quoted_line_break(tmp_path: Path) -> None:
    path: Path = _csv(tmp_path, 'order_id,day,amount\n"A\nB",2026-10-01,2\nC,2026-10-01,x\n')
    with pytest.raises(TallyError, match="line 4"):
        CsvOrders().read(path)


@pytest.mark.parametrize("text", ["A,2026-10-01,5\n", ""], ids=["no-header", "empty"])
def test_read_refuses_a_file_without_the_header(tmp_path: Path, text: str) -> None:
    path: Path = _csv(tmp_path, text)
    with pytest.raises(TallyError, match="line 1: expected the header order_id,day,amount"):
        CsvOrders().read(path)


def test_read_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TallyError, match="cannot read"):
        CsvOrders().read(tmp_path / "missing.csv")


def test_read_refuses_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path: Path = tmp_path / "orders.csv"
    path.write_bytes(b"order_id,day,amount\nA,2026-10-01,\xff\n")
    with pytest.raises(TallyError, match="cannot read"):
        CsvOrders().read(path)


def test_write_report_refuses_an_unwritable_path(tmp_path: Path) -> None:
    with pytest.raises(TallyError, match="cannot write"):
        write_report([], tmp_path / "no-such-folder" / "report.csv")


def test_write_report_writes_header_and_rows(tmp_path: Path) -> None:
    path: Path = tmp_path / "report.csv"
    write_report([{"day": "2026-10-01", "revenue": "10.50"}], path)
    assert path.read_text(encoding="utf-8").splitlines() == ["day,revenue", "2026-10-01,10.50"]
