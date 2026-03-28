from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import load_template_dir


def test_merge_template_allows_direct_price_series_expr(tmp_path: Path):
    root = tmp_path / "templates"
    (root / "gold_enterprises#黄金企业").mkdir(parents=True)

    (root / "gold_enterprises#黄金企业" / "nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index.toml").write_text(
        'name = "nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index"\n'
        'alias = "收入趋势+股价-收盘+黄金价格+上证指数"\n'
        'type = "combo"\n'
        'mode = "merge"\n'
        '[[series]]\n'
        'expr = "nonfin-trend-income"\n'
        '[[series]]\n'
        'expr = "nonfin-trend-price_close"\n'
        '[[series]]\n'
        'expr = "nonfin-trend-gold_price"\n'
        '[[series]]\n'
        'name = "上证指数"\n'
        'expr = "idx.sh000001.close"\n',
        encoding="utf-8",
    )

    tpl = load_template_dir(root)["nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index"]
    series = tpl.series or []
    assert len(series) == 4
    assert series[-1].name == "上证指数"
    assert series[-1].expr == "idx.sh000001.close"
