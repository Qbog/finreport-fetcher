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
