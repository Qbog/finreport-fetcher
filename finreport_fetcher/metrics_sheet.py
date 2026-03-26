from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class MetricSpec:
    key: str
    cn: str
    en: str
    section_key: str
    section_cn: str
    aliases: tuple[str, ...] = ()
    note: str = ""


METRIC_SPECS: list[MetricSpec] = [
    MetricSpec("metrics.roe", "净资产收益率(ROE)", "Return on equity (ROE)", "returns", "回报能力", aliases=("ROE", "净资产收益率"), note="百分比指标；不同数据源口径可能略有差异。"),
    MetricSpec("metrics.roa", "总资产报酬率(ROA)", "Return on assets (ROA)", "returns", "回报能力", aliases=("ROA", "总资产报酬率", "总资产净利率"), note="百分比指标；不同数据源口径可能略有差异。"),
    MetricSpec("metrics.roic", "投入资本回报率(ROIC)", "Return on invested capital (ROIC)", "returns", "回报能力", aliases=("ROIC", "投入资本回报率"), note="百分比指标；部分公司/数据源可能缺失。"),
    MetricSpec("metrics.ev", "企业价值(EV)", "Enterprise value (EV)", "valuation", "估值与现金创造", aliases=("EV", "企业价值"), note="估值指标；部分公司/数据源可能缺失。"),
    MetricSpec("metrics.ebitda", "息税折旧摊销前利润(EBITDA)", "EBITDA", "valuation", "估值与现金创造", aliases=("EBITDA",), note="利润规模指标；部分公司/数据源可能缺失。"),
]

_METRIC_BY_FIELD = {spec.key.split(".", 1)[1]: spec for spec in METRIC_SPECS}


def build_metrics_sheet(metrics_df: pd.DataFrame, period_end: date) -> pd.DataFrame:
    if metrics_df is None or metrics_df.empty:
        return pd.DataFrame(columns=["科目", "数值", "key", "备注", "英文", "__level", "__is_header", "__uncommon"])

    period_key = period_end.strftime("%Y%m%d")
    end_dates = metrics_df["end_date"].astype(str).str.replace(r"[^0-9]", "", regex=True) if "end_date" in metrics_df.columns else pd.Series(dtype=str)
    sub = metrics_df[end_dates == period_key].copy()
    if sub.empty:
        return pd.DataFrame(columns=["科目", "数值", "key", "备注", "英文", "__level", "__is_header", "__uncommon"])

    row = sub.iloc[-1]
    rows: list[dict[str, object]] = []
    current_section = None
    for spec in METRIC_SPECS:
        field = spec.key.split(".", 1)[1]
        if field not in row.index:
            continue
        value = row.get(field)
        if pd.isna(value):
            continue
        if spec.section_cn != current_section:
            rows.append({
                "科目": spec.section_cn,
                "数值": None,
                "key": f"metrics.section.{spec.section_key}",
                "备注": "",
                "英文": spec.section_cn,
                "__level": 0,
                "__is_header": True,
                "__uncommon": False,
            })
            current_section = spec.section_cn
        rows.append({
            "科目": spec.cn,
            "数值": value,
            "key": spec.key,
            "备注": spec.note,
            "英文": spec.en,
            "__level": 1,
            "__is_header": False,
            "__uncommon": False,
        })

    return pd.DataFrame(rows, columns=["科目", "数值", "key", "备注", "英文", "__level", "__is_header", "__uncommon"])
