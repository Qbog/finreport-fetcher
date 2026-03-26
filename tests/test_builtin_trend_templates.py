from __future__ import annotations

from pathlib import Path


def test_income_trend_is_cumulative_and_net_profit_q_is_single_quarter_diff():
    root = Path('/root/.openclaw/workspace/a_share_finreport_fetcher/templates')
    income = (root / 'income_trend#收入趋势.toml').read_text(encoding='utf-8')
    netp = (root / 'net_profit_q#归母净利润.toml').read_text(encoding='utf-8')
    assert 'expr = "is.revenue_total"' in income
    assert 'prev_in_year' not in income
    assert 'is.net_profit_parent - is.net_profit_parent.prev_in_year' in netp
