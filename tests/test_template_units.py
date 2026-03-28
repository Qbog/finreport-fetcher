from __future__ import annotations

from pathlib import Path


def test_templates_declare_expected_units_for_selected_series():
    root = Path('/root/.openclaw/workspace/a_share_finreport_fetcher/templates')
    pe = (root / 'nonfin-trend-pe.toml').read_text(encoding='utf-8')
    px = (root / 'nonfin-trend-price_close.toml').read_text(encoding='utf-8')
    gold = (root / 'gold_enterprises#黄金企业' / 'nonfin-trend-gold_price.toml').read_text(encoding='utf-8')
    merge = (root / 'gold_enterprises#黄金企业' / 'nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index.toml').read_text(encoding='utf-8')

    assert 'unit = "倍"' in pe
    assert 'unit = "元"' in px
    assert 'unit = "美元"' in gold
    assert 'unit = "点"' in merge
