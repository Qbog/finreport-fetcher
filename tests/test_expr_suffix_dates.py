from __future__ import annotations

from datetime import date

from finreport_charts.cli import _prev_in_year_quarter_end, _prev_year_same_quarter_end, _quarter_end_for_q


def test_prev_in_year_quarter_end_logic():
    assert _prev_in_year_quarter_end(date(2024, 3, 31)) is None
    assert _prev_in_year_quarter_end(date(2024, 6, 30)) == date(2024, 3, 31)
    assert _prev_in_year_quarter_end(date(2024, 9, 30)) == date(2024, 6, 30)
    assert _prev_in_year_quarter_end(date(2024, 12, 31)) == date(2024, 9, 30)


def test_prev_year_quarter_suffix_helpers():
    assert _prev_year_same_quarter_end(date(2024, 12, 31)) == date(2023, 12, 31)
    assert _prev_year_same_quarter_end(date(2024, 6, 30)) == date(2023, 6, 30)
    assert _quarter_end_for_q(2023, 1) == date(2023, 3, 31)
    assert _quarter_end_for_q(2023, 2) == date(2023, 6, 30)
    assert _quarter_end_for_q(2023, 3) == date(2023, 9, 30)
    assert _quarter_end_for_q(2023, 4) == date(2023, 12, 31)
