from __future__ import annotations


def resolve_display(*, only_one: bool, blk_name: str, ref_label: str, prefix: str = "") -> str:
    if only_one:
        display = blk_name or ref_label
    else:
        display = f"{ref_label}/{blk_name or 'value'}"
    if prefix:
        display = prefix
    return display


def test_merge_single_series_prefers_leaf_name_then_alias():
    assert resolve_display(only_one=True, blk_name="股价收盘", ref_label="股价-收盘") == "股价收盘"
    assert resolve_display(only_one=True, blk_name="", ref_label="股价-收盘") == "股价-收盘"


def test_merge_override_name_wins():
    assert resolve_display(only_one=True, blk_name="黄金价格", ref_label="黄金价格", prefix="上证指数") == "上证指数"


def test_merge_multi_series_uses_friendly_prefix():
    assert resolve_display(only_one=False, blk_name="经营现金流", ref_label="现金流趋势") == "现金流趋势/经营现金流"
