from __future__ import annotations

from pathlib import Path


def test_builtin_trend_templates_keep_expected_financial_exprs():
    root = Path('/root/.openclaw/workspace/a_share_finreport_fetcher/templates')
    income = (root / 'income_trend#收入趋势.toml').read_text(encoding='utf-8')
    netp = (root / 'net_profit_q#归母净利润.toml').read_text(encoding='utf-8')
    assert 'is.revenue_total' in income
    assert 'type = "bar"' in income and 'mode = "trend"' in income
    assert 'is.net_profit_parent' in netp
    assert 'prev_in_year' in netp
