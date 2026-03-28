from __future__ import annotations

from pathlib import Path


def test_new_builtin_templates_exist_and_keep_expected_exprs():
    root = Path('/root/.openclaw/workspace/a_share_finreport_fetcher/templates')
    ebitda = (root / 'nonfin-trend-ebitda.toml').read_text(encoding='utf-8')
    pe = (root / 'nonfin-trend-pe.toml').read_text(encoding='utf-8')

    assert 'type = "bar"' in ebitda and 'mode = "trend"' in ebitda
    assert 'is.total_profit' in ebitda
    assert 'is.interest_expense' in ebitda
    assert 'cf.depreciation' in ebitda

    assert 'type = "line"' in pe and 'mode = "price"' in pe
    assert 'metrics.per_share.basic_eps' in pe
    assert 'px.close' in pe
    assert 'abs(' in pe
