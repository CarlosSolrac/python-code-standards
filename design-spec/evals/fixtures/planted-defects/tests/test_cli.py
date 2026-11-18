from pathlib import Path

import pytest
from tally_cli import main


def test_main_writes_the_report(tmp_path: Path) -> None:
    orders: Path = tmp_path / "orders.csv"
    report: Path = tmp_path / "report.csv"
    orders.write_text("order_id,day,amount\nA,2026-10-01,2\nB,2026-10-01,3\n", encoding="utf-8")
    assert main([str(orders), str(report)]) == 0
    assert report.read_text(encoding="utf-8").splitlines() == ["day,revenue", "2026-10-01,5"]


def test_main_refuses_a_bad_file_with_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    orders: Path = tmp_path / "orders.csv"
    orders.write_text("order_id,day,amount\nA,2026-10-01,-2\n", encoding="utf-8")
    assert main([str(orders), str(tmp_path / "report.csv")]) == 1
    assert "refused: line 2" in capsys.readouterr().err


def test_main_reports_usage_with_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["only-one"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_main_reads_sys_argv_when_no_arguments_are_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["tally"])
    assert main() == 2
