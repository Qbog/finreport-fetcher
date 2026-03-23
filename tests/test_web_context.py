from __future__ import annotations

from pathlib import Path

from finreport_web.server import AppContext


def test_web_context_bootstrap_and_config_save(tmp_path: Path):
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

    (templates_dir / "income_trend.toml").write_text(
        """
name = "income_trend"
alias = "收入趋势"
names = ["营业总收入趋势"]

type = "bar"
mode = "trend"
title = "收入趋势"
x_label = "报告期"
y_label = "金额"

[[bars]]
name = "营业总收入"
expr = "is.revenue_total"
""".strip(),
        encoding="utf-8",
    )
    (templates_dir / "liability_structure.toml").write_text(
        """
name = "liability_structure"
alias = "负债结构"

type = "bar"
mode = "structure"
title = "负债结构"
x_label = "科目"
y_label = "金额"

[[bars]]
name = "负债合计"
expr = "bs.total_liabilities"
""".strip(),
        encoding="utf-8",
    )

    ctx = AppContext(
        repo_root=repo_root,
        data_dir=data_dir,
        templates_dir=templates_dir,
        category_config=category_config,
    )

    payload = ctx.bootstrap_payload()
    assert payload["categories"][0]["key"] == "demo"
    assert [tpl["key"] for tpl in payload["templates"]] == ["income_trend", "liability_structure"]
    assert payload["templates"][0]["names"] == ["income_trend", "收入趋势", "营业总收入趋势"]

    result = ctx.save_category_config(
        """
[categories.saved]
alias = "保存后的分类"
items = [
  { name = "三六零", code = "601360" },
]
""".strip()
    )
    assert result["ok"] is True
    assert result["categories"][0]["key"] == "saved"
