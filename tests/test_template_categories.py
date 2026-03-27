from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import find_template_file, list_template_categories, load_template_dir


def test_load_template_dir_supports_recursive_categories(tmp_path: Path):
    root = tmp_path / "templates"
    (root / "merge_templates#合并模板").mkdir(parents=True)
    (root / "gold_enterprises#黄金企业").mkdir(parents=True)

    (root / "merge_templates#合并模板" / "revenue_vs_price_close#收入趋势+股价-收盘.toml").write_text(
        """
name = "revenue_vs_price_close"
alias = "收入趋势+股价-收盘"

type = "combo"
mode = "merge"

[[series]]
expr = "income_trend"
""".strip(),
        encoding="utf-8",
    )
    (root / "gold_enterprises#黄金企业" / "gold_price_trend#黄金价格.toml").write_text(
        """
name = "gold_price_trend"
alias = "黄金价格"

type = "line"
mode = "trend"

[[series]]
name = "黄金价格"
expr = "commodity.黄金.close"
""".strip(),
        encoding="utf-8",
    )

    loaded = load_template_dir(root)
    assert set(loaded.keys()) == {"revenue_vs_price_close", "gold_price_trend"}
    assert loaded["revenue_vs_price_close"].category == "merge_templates"
    assert loaded["revenue_vs_price_close"].category_alias == "合并模板"
    assert loaded["gold_price_trend"].category == "gold_enterprises"
    assert loaded["gold_price_trend"].category_alias == "黄金企业"

    cats = list_template_categories(root)
    assert [x["key"] for x in cats] == ["gold_enterprises", "merge_templates"]
    assert find_template_file(root, "收入趋势+股价-收盘").name == "revenue_vs_price_close#收入趋势+股价-收盘.toml"
    assert find_template_file(root, "merge_templates#合并模板/revenue_vs_price_close#收入趋势+股价-收盘.toml") is not None


def test_merge_template_expr_supports_same_specs_as_template_option(tmp_path: Path):
    root = tmp_path / "templates"
    (root / "gold_enterprises#黄金企业").mkdir(parents=True)
    (root / "nonfin-trend-income.toml").write_text('name = "nonfin-trend-income"\nnames = ["income_trend"]\nalias = "收入趋势"\ntype = "bar"\nmode = "trend"\n[[series]]\nexpr = "is.revenue_total"\n', encoding='utf-8')
    (root / "nonfin-trend-price_close.toml").write_text('name = "nonfin-trend-price_close"\nnames = ["price_close_trend"]\nalias = "股价-收盘"\ntype = "line"\nmode = "price"\n[[series]]\nexpr = "px.close"\n', encoding='utf-8')
    (root / "gold_enterprises#黄金企业" / "nonfin-trend-gold_price.toml").write_text('name = "nonfin-trend-gold_price"\nnames = ["gold_price_trend"]\nalias = "黄金价格"\ntype = "line"\nmode = "trend"\n[[series]]\nexpr = "commodity.黄金.close"\n', encoding='utf-8')
    p = root / "gold_enterprises#黄金企业" / "revenue_vs_price_close_vs_gold#收入趋势+股价-收盘+黄金价格.toml"
    p.write_text(
        'name = "nonfin-merge-revenue_vs_price_close_vs_gold"\nalias = "收入趋势+股价-收盘+黄金价格"\ntype = "combo"\nmode = "merge"\n[[series]]\nexpr = "nonfin-trend-income"\n[[series]]\nexpr = "nonfin-trend-price_close"\n[[series]]\nexpr = "nonfin-trend-gold_price"\n',
        encoding='utf-8',
    )
    tpl = load_template_dir(root)["nonfin-merge-revenue_vs_price_close_vs_gold"]
    exprs = [x.expr for x in (tpl.series or [])]
    assert exprs == ["nonfin-trend-income", "nonfin-trend-price_close", "nonfin-trend-gold_price"]
