from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import find_template_file, load_template_file, template_filename, template_lookup_names


def test_template_lookup_supports_english_and_chinese_names(tmp_path: Path):
    tpl_path = tmp_path / template_filename("income_trend", "收入趋势")
    tpl_path.write_text(
        """
name = "income_trend"
alias = "收入趋势"
names = ["营业总收入趋势", "income"]

type = "bar"
mode = "trend"
title = "营业总收入趋势"
x_label = "报告期"
y_label = "金额"

[[series]]
name = "营业总收入"
expr = "is.revenue_total"
""".strip(),
        encoding="utf-8",
    )

    tpl = load_template_file(tpl_path)
    assert template_lookup_names(tpl) == ["income_trend", "收入趋势", "营业总收入趋势", "income"]

    assert find_template_file(tmp_path, "income_trend") == tpl_path
    assert find_template_file(tmp_path, "收入趋势") == tpl_path
    assert find_template_file(tmp_path, "营业总收入趋势") == tpl_path
    assert find_template_file(tmp_path, "income") == tpl_path
    assert find_template_file(tmp_path, "income_trend.toml") == tpl_path
    assert find_template_file(tmp_path, tpl_path.name) == tpl_path
