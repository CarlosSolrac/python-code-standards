"""Tests for the nightshift log elapsed-time checker."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from check_elapsed import check_log, main

IN_PROGRESS: str = "—"
WAITING: str = "— (waiting for Codex)"
FIXTURE: Path = Path(__file__).parent / "fixtures" / "resume-with-boundary" / "nightshift" / "LOG-2026-10-07.md"


def _header(started: str, finished: str) -> str:
    return f"Started: {started} · Last update: 2026-10-08 00:00 · Finished: {finished}"


def _summary(started: str, completed: str, elapsed: str) -> str:
    return f"Started: {started} · Completed: {completed} · Elapsed: {elapsed}"


def _log(header: str | None, summary: str | None) -> str:
    """Build a minimal log; a ``None`` line is left out."""
    lines: list[str]
    lines = ["# Nightshift log — statskit — 2026-10-07", "", "Status: complete"]
    if header is not None:
        lines.append(header)
    lines += ["Session: abc123", "", "## Morning summary"]
    if summary is not None:
        lines.append(summary)
    lines += ["Done: 1.", "", "## Timeline", "- 22:00 Night started."]
    return "\n".join(lines) + "\n"


def _times(started: str, finished: str, elapsed: str) -> str:
    """Build a log whose summary copies the header's times."""
    return _log(_header(started, finished), _summary(started, finished, elapsed))


class CheckElapsedTestCase(unittest.TestCase):
    def assert_problem(self, problems: list[str], prefix: str, word: str) -> None:
        self.assertTrue(any(p.startswith(prefix) and word.lower() in p.lower() for p in problems), problems)


class ValidLogTest(CheckElapsedTestCase):
    def test_same_offset(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 00m")), [])

    def test_colon_offset(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 22:00 -05:00", "2026-10-08 00:00 -05:00", "2h 00m")), [])

    def test_two_digit_hours(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 10:00 -0500", "2026-10-07 23:05 -0500", "13h 05m")), [])

    def test_midnight_crossing(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 23:30 -0500", "2026-10-08 01:15 -0500", "1h 45m")), [])

    def test_same_minute(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 23:30 -0500", "2026-10-07 23:30 -0500", "0h 00m")), [])


class DaylightSavingTest(CheckElapsedTestCase):
    # 00:30 -0400 is 04:30 UTC and 02:30 -0500 is 07:30 UTC, so the true elapsed time is 3h; the wall clocks differ by 2h.
    def test_fall_back_to_half_past_two(self) -> None:
        self.assertEqual(check_log(_times("2026-11-01 00:30 -0400", "2026-11-01 02:30 -0500", "3h 00m")), [])

    def test_fall_back_naive_value_to_half_past_two_is_flagged(self) -> None:
        self.assert_problem(check_log(_times("2026-11-01 00:30 -0400", "2026-11-01 02:30 -0500", "2h 00m")), "summary:", "Elapsed")

    def test_fall_back_to_half_past_one(self) -> None:
        self.assertEqual(check_log(_times("2026-11-01 00:30 -0400", "2026-11-01 01:30 -0500", "2h 00m")), [])

    def test_fall_back_naive_value_to_half_past_one_is_flagged(self) -> None:
        self.assert_problem(check_log(_times("2026-11-01 00:30 -0400", "2026-11-01 01:30 -0500", "1h 00m")), "summary:", "Elapsed")


class HeaderProblemTest(CheckElapsedTestCase):
    def test_finished_before_started(self) -> None:
        self.assert_problem(check_log(_times("2026-10-08 00:00 -0500", "2026-10-07 22:00 -0500", "0h 00m")), "header:", "Finished")

    def test_header_line_missing(self) -> None:
        self.assert_problem(check_log(_log(None, _summary("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 00m"))), "header:", "missing")

    def test_unparseable_started(self) -> None:
        self.assert_problem(check_log(_times("last night", "2026-10-08 00:00 -0500", "2h 00m")), "header:", "Started")

    def test_unparseable_finished(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 25:00 -0500", "2h 00m")), "header:", "Finished")

    def test_legacy_finished_without_offset(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00", "2026-10-08 00:00", "2h 00m (approx.)")), "header:", "offset")


class LegacyLogTest(CheckElapsedTestCase):
    def test_legacy_approx(self) -> None:
        self.assertEqual(check_log(_times("2026-10-07 22:00", "2026-10-08 00:00 -0500", "2h 00m (approx.)")), [])

    def test_legacy_missing_approx(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00", "2026-10-08 00:00 -0500", "2h 00m")), "summary:", "approx.")

    def test_legacy_wrong_value(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00", "2026-10-08 00:00 -0500", "1h 00m (approx.)")), "summary:", "Elapsed")


class InProgressLogTest(CheckElapsedTestCase):
    def test_in_progress(self) -> None:
        text: str
        text = _log(_header("2026-10-07 22:00 -0500", IN_PROGRESS), _summary("2026-10-07 22:00 -0500", WAITING, "3h 10m (so far)"))
        self.assertEqual(check_log(text), [])

    def test_in_progress_missing_so_far(self) -> None:
        text: str
        text = _log(_header("2026-10-07 22:00 -0500", IN_PROGRESS), _summary("2026-10-07 22:00 -0500", WAITING, "3h 10m"))
        self.assert_problem(check_log(text), "summary:", "so far")

    def test_in_progress_completed_not_waiting(self) -> None:
        text: str
        text = _log(_header("2026-10-07 22:00 -0500", IN_PROGRESS), _summary("2026-10-07 22:00 -0500", IN_PROGRESS, "3h 10m (so far)"))
        self.assert_problem(check_log(text), "summary:", "Completed")

    # The fixture is a legacy in-progress log: its header must pass, but its summary has no times line yet.
    def test_fixture_header_is_valid(self) -> None:
        problems: list[str]
        problems = check_log(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual([p for p in problems if p.startswith("header:")], [])


class SummaryProblemTest(CheckElapsedTestCase):
    def test_summary_line_missing(self) -> None:
        self.assert_problem(check_log(_log(_header("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500"), None)), "summary:", "missing")

    def test_started_mismatch(self) -> None:
        text: str
        text = _log(_header("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500"), _summary("2026-10-07 22:05 -0500", "2026-10-08 00:00 -0500", "2h 00m"))
        self.assert_problem(check_log(text), "summary:", "Started")

    def test_completed_mismatch(self) -> None:
        text: str
        text = _log(_header("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500"), _summary("2026-10-07 22:00 -0500", "2026-10-08 00:05 -0500", "2h 00m"))
        self.assert_problem(check_log(text), "summary:", "Completed")

    def test_wrong_elapsed(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 05m")), "summary:", "Elapsed")

    def test_stray_suffix_on_offset_log(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 00m (approx.)")), "summary:", "Elapsed")

    def test_elapsed_unparseable(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "two hours")), "summary:", "Elapsed")

    def test_elapsed_minutes_not_padded(self) -> None:
        self.assert_problem(check_log(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 0m")), "summary:", "Elapsed")


class MainTest(unittest.TestCase):
    def run_main(self, text: str) -> tuple[int, str]:
        tmp: str
        with tempfile.TemporaryDirectory() as tmp:
            path: Path
            path = Path(tmp) / "LOG.md"
            path.write_text(text, encoding="utf-8")
            buffer: io.StringIO
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code: int
                code = main([str(path)])
        return code, buffer.getvalue()

    def test_clean_file(self) -> None:
        self.assertEqual(self.run_main(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 00m")), (0, ""))

    def test_problem_file(self) -> None:
        code: int
        output: str
        code, output = self.run_main(_times("2026-10-07 22:00 -0500", "2026-10-08 00:00 -0500", "2h 05m"))
        self.assertEqual(code, 1)
        self.assertIn("summary:", output)


if __name__ == "__main__":
    unittest.main()
