from __future__ import annotations

from pathlib import Path

from finreport_web.server import AppContext


def test_web_context_bootstrap_and_category_template_create(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    data_dir = repo_root / "output"
    data_dir.mkdir()
    templates_dir = repo_root / "templates"
    templates_dir.mkdir()
    category_config = repo_root / "config" / "company_categories.toml"
    category_config.parent.mkdir(parents=True, exist_ok=True)
    category_config.write_text(
        """
[categories.demo]
alias = "演示分类"
items = [
  { name = "贵州茅台", code = "600519" },
  { name = "深信服", code = "300454" },
]
""".strip(),
        encoding="utf-8",
    )

    (data_dir / "_global" / "company_basics").mkdir(parents=True)
    (data_dir / "_global" / "company_basics" / "company_basics.csv").write_text(
        "code6,name,industry\n600519,贵州茅台,白酒\n300454,深信服,网络安全\n",
        encoding="utf-8",
    )

    (templates_dir / "income_trend.toml").write_text(
        """
name = "income_trend"
alias = "收入趋势"

type = "bar"
mode = "trend"

[[bars]]
name = "营业总收入"
expr = "is.revenue_total"
""".strip(),
        encoding="utf-8",
    )
    (templates_dir / "price_merge.toml").write_text(
        """
name = "price_merge"
alias = "收入+股价"

type = "combo"
mode = "merge"
bar_item = "is.revenue_total"
line = "close"
""".strip(),
        encoding="utf-8",
    )

    ctx = AppContext(repo_root=repo_root, data_dir=data_dir, templates_dir=templates_dir, category_config=category_config)
    payload = ctx.bootstrap_payload()
    assert payload["categories"][0]["key"] == "demo"
    assert [tpl["key"] for tpl in payload["templates"]] == ["income_trend", "price_merge"]
    assert payload["companyBasics"][0]["code6"] == "600519"

    result = ctx.create_category(
        {
            "label": "新分类",
            "companies": [
                {"code6": "601360", "name": "三六零"},
                {"code6": "300454", "name": "深信服"},
            ],
        }
    )
    assert result["ok"] is True
    assert result["created"] == "item"

    tpl_result = ctx.create_template({"mode": "peer", "label": "归母净利润同业", "expr": "is.net_profit_parent"})
    assert tpl_result["ok"] is True
    assert any(x["key"] == "item" for x in tpl_result["templates"])
