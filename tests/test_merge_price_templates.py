from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import load_template_dir


def test_gold_price_template_uses_price_mode(tmp_path: Path):
    root = tmp_path / "templates"
    (root / "gold_enterprises#黄金企业").mkdir(parents=True)

    (root / "gold_enterprises#黄金企业" / "nonfin-trend-gold_price.toml").write_text(
        'name = "nonfin-trend-gold_price"\n'
        'alias = "黄金价格"\n'
        'type = "line"\n'
        'mode = "price"\n'
        '[[series]]\n'
        'name = "黄金价格"\n'
        'expr = "commodity.黄金.close"\n',
        encoding="utf-8",
    )

    tpl = load_template_dir(root)["nonfin-trend-gold_price"]
    assert tpl.type == "line"
    assert tpl.mode == "price"


def test_merge_template_with_gold_and_sh_index_keeps_all_series(tmp_path: Path):
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
    exprs = [x.expr for x in (tpl.series or [])]
    assert exprs == [
        "nonfin-trend-income",
        "nonfin-trend-price_close",
        "nonfin-trend-gold_price",
        "idx.sh000001.close",
    ]
