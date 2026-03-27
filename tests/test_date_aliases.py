from __future__ import annotations

from datetime import date, timedelta

from finindex_fetcher.cli import parse_date_local as parse_index_date
from finmetrics_fetcher.cli import parse_date_local as parse_metrics_date
from finreport_fetcher.utils.dates import parse_date


def test_parse_date_supports_now_and_yesterday_aliases():
    today = date.today()
    assert parse_date("now") == today
    assert parse_date("today") == today
    assert parse_date("yesterday") == today - timedelta(days=1)


def test_local_parse_helpers_share_date_alias_support():
    today = date.today()
    yesterday = today - timedelta(days=1)
    assert parse_index_date("now") == today
    assert parse_index_date("yesterday") == yesterday
    assert parse_metrics_date("now") == today
    assert parse_metrics_date("yesterday") == yesterday
