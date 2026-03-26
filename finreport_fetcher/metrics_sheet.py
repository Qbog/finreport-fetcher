from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

import pandas as pd

from finreport_fetcher.mappings.enrich import _auto_en_from_cn, _short_hash, _slugify_en


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
    MetricSpec("metrics.roe", "净资产收益率(ROE)", "Return on equity (ROE)", "returns", "回报能力", aliases=("ROE", "净资产收益率", "roe", "roe_dt"), note="百分比指标；不同数据源口径可能略有差异。"),
    MetricSpec("metrics.roa", "总资产报酬率(ROA)", "Return on assets (ROA)", "returns", "回报能力", aliases=("ROA", "总资产报酬率", "总资产净利率", "roa"), note="百分比指标；不同数据源口径可能略有差异。"),
    MetricSpec("metrics.roic", "投入资本回报率(ROIC)", "Return on invested capital (ROIC)", "returns", "回报能力", aliases=("ROIC", "投入资本回报率", "roic"), note="百分比指标；部分公司/数据源可能缺失。"),
    MetricSpec("metrics.ev", "企业价值(EV)", "Enterprise value (EV)", "valuation", "估值与现金创造", aliases=("EV", "企业价值", "ev"), note="估值指标；部分公司/数据源可能缺失。"),
    MetricSpec("metrics.ebitda", "息税折旧摊销前利润(EBITDA)", "EBITDA", "valuation", "估值与现金创造", aliases=("EBITDA", "ebitda"), note="利润规模指标；部分公司/数据源可能缺失。"),
]

SHEET_COLUMNS = ["科目", "数值", "key", "备注", "英文", "__level", "__is_header", "__uncommon"]
_METADATA_FIELDS = {"ts_code", "code6", "name", "ann_date", "end_date", "update_flag"}

_METRIC_ALIAS_LOOKUP: dict[str, MetricSpec] = {}
for spec in METRIC_SPECS:
    for alias in {spec.cn, spec.key, *spec.aliases}:
        _METRIC_ALIAS_LOOKUP[str(alias).strip().lower()] = spec

_TUSHARE_FIELD_LABELS = {
    "eps": "基本每股收益(EPS)",
    "dt_eps": "稀释每股收益",
    "bps": "每股净资产(BPS)",
    "ocfps": "每股经营现金流(OCFPS)",
    "retainedps": "每股留存收益",
    "cfps": "每股现金流量净额(CFPS)",
    "ebit_ps": "每股息税前利润",
    "fcff_ps": "每股企业自由现金流",
    "fcfe_ps": "每股股东自由现金流",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "cash_ratio": "现金比率",
    "ar_turn": "应收账款周转率",
    "ca_turn": "流动资产周转率",
    "fa_turn": "固定资产周转率",
    "assets_turn": "总资产周转率",
    "op_income": "营业利润",
    "valuechange_income": "公允价值变动收益",
    "interst_income": "利息收入",
    "daa": "折旧与摊销",
    "ebit": "息税前利润(EBIT)",
    "fcff": "企业自由现金流(FCFF)",
    "fcfe": "股东自由现金流(FCFE)",
    "current_exint": "非息流动负债",
    "noncurrent_exint": "非息非流动负债",
    "interestdebt": "带息债务",
    "netdebt": "净债务",
    "tangible_asset": "有形资产",
    "working_capital": "营运资金",
    "networking_capital": "净营运资金",
    "invest_capital": "投入资本",
    "retained_earnings": "留存收益",
    "diluted2_eps": "稀释每股收益(持续经营)",
    "turn_days": "营业周期",
    "roa_yearly": "年化ROA",
    "roa_dp": "ROA(摊薄)",
    "grossprofit_margin": "毛利率",
    "netprofit_margin": "净利率",
    "profit_to_gr": "营业利润率",
    "saleexp_to_gr": "销售费用率",
    "adminexp_of_gr": "管理费用率",
    "finaexp_of_gr": "财务费用率",
    "impai_ttm": "资产减值损失(TTM)",
    "gc_of_gr": "营业总成本率",
    "op_of_gr": "营业利润率",
    "ebit_of_gr": "EBIT/营业总收入",
    "roe_yearly": "年化ROE",
    "roa2_yearly": "年化总资产报酬率",
    "debt_to_assets": "资产负债率",
    "assets_to_eqt": "权益乘数",
    "dp_assets_to_eqt": "权益乘数(摊薄)",
    "ca_to_assets": "流动资产占总资产比",
    "nca_to_assets": "非流动资产占总资产比",
    "tbassets_to_totalassets": "有形资产占总资产比",
    "int_to_talcap": "带息债务占总资本比",
    "eqt_to_talcapital": "归母权益占投入资本比",
    "currentdebt_to_debt": "流动负债占总负债比",
    "longdeb_to_debt": "长期负债占总负债比",
    "ocf_to_shortdebt": "经营现金流/短期债务",
    "debt_to_eqt": "产权比率",
    "eqt_to_debt": "股东权益比率",
    "eqt_to_interestdebt": "股东权益/带息债务",
    "tangibleasset_to_debt": "有形资产/总负债",
    "tangasset_to_intdebt": "有形资产/带息债务",
    "tangibleasset_to_netdebt": "有形资产/净债务",
    "ocf_to_debt": "经营现金流/总负债",
    "turnover_rate": "存货周转率",
    "inventory_turn": "存货周转率",
    "inventory_days": "存货周转天数",
    "ar_days": "应收账款周转天数",
    "ca_days": "流动资产周转天数",
    "fa_days": "固定资产周转天数",
    "assets_days": "总资产周转天数",
    "revenue_yoy": "营业收入同比增长率",
    "op_yoy": "营业利润同比增长率",
    "ebt_yoy": "利润总额同比增长率",
    "netprofit_yoy": "净利润同比增长率",
    "dt_netprofit_yoy": "扣非净利润同比增长率",
    "ocf_yoy": "经营现金流同比增长率",
    "roe_yoy": "ROE同比变动",
    "bps_yoy": "每股净资产同比增长率",
    "assets_yoy": "总资产同比增长率",
    "eqt_yoy": "净资产同比增长率",
    "tr_yoy": "营业总收入同比增长率",
    "or_yoy": "营业收入同比增长率",
    "q_gr_yoy": "季度营业总收入同比增长率",
    "q_gr_qoq": "季度营业总收入环比增长率",
    "q_sales_yoy": "季度营业收入同比增长率",
    "q_sales_qoq": "季度营业收入环比增长率",
    "q_op_yoy": "季度营业利润同比增长率",
    "q_op_qoq": "季度营业利润环比增长率",
    "q_profit_yoy": "季度净利润同比增长率",
    "q_profit_qoq": "季度净利润环比增长率",
    "q_netprofit_yoy": "季度归母净利润同比增长率",
    "q_netprofit_qoq": "季度归母净利润环比增长率",
    "equity_yoy": "归母净资产同比增长率",
}

_CN_KEY_TOKEN_MAP = [
    ("净资产收益率", "return_on_equity"),
    ("总资产报酬率", "return_on_assets"),
    ("总资产净利率", "return_on_assets"),
    ("投入资本回报率", "return_on_invested_capital"),
    ("每股经营现金流", "operating_cashflow_per_share"),
    ("每股现金流量净额", "cashflow_per_share"),
    ("每股净资产", "book_value_per_share"),
    ("基本每股收益", "eps_basic"),
    ("稀释每股收益", "eps_diluted"),
    ("每股", "per_share"),
    ("同比增长率", "yoy_growth_rate"),
    ("环比增长率", "qoq_growth_rate"),
    ("增长率", "growth_rate"),
    ("资产负债率", "debt_to_assets_ratio"),
    ("流动比率", "current_ratio"),
    ("速动比率", "quick_ratio"),
    ("现金比率", "cash_ratio"),
    ("毛利率", "gross_margin"),
    ("净利率", "net_margin"),
    ("营业利润率", "operating_margin"),
    ("存货周转率", "inventory_turnover"),
    ("应收账款周转率", "accounts_receivable_turnover"),
    ("总资产周转率", "asset_turnover"),
    ("流动资产周转率", "current_asset_turnover"),
    ("固定资产周转率", "fixed_asset_turnover"),
    ("周转天数", "turnover_days"),
    ("企业价值", "enterprise_value"),
    ("营业总收入", "total_operating_revenue"),
    ("营业收入", "operating_revenue"),
    ("营业利润", "operating_profit"),
    ("净利润", "net_profit"),
    ("扣非净利润", "net_profit_excluding_nonrecurring"),
    ("经营现金流", "operating_cashflow"),
    ("经营活动产生的现金流量净额", "operating_cashflow"),
    ("带息债务", "interest_bearing_debt"),
    ("净债务", "net_debt"),
    ("有形资产", "tangible_assets"),
    ("营运资金", "working_capital"),
    ("留存收益", "retained_earnings"),
    ("折旧与摊销", "depreciation_and_amortization"),
    ("折旧摊销前利润", "ebitda"),
    ("息税前利润", "ebit"),
    ("股东权益", "equity"),
    ("净资产", "net_assets"),
    ("总资产", "total_assets"),
]

_SECTION_LABELS = {
    "growth": "成长能力",
    "returns": "回报能力",
    "profitability": "盈利能力",
    "operation": "营运效率",
    "solvency": "偿债与流动性",
    "per_share": "每股指标",
    "valuation": "估值与现金创造",
    "other": "其他指标",
}


def _empty_sheet() -> pd.DataFrame:
    return pd.DataFrame(columns=SHEET_COLUMNS)


def _clean_period_str(v: object) -> str:
    return re.sub(r"[^0-9]", "", str(v or ""))


def _humanize_field_name(field: str) -> str:
    return str(field or "").replace("_", " ").strip().title() or str(field or "")


def _metric_key_from_cn(cn: str) -> str:
    s = str(cn or "").strip()
    if not s:
        return "metrics.unknown"
    for src, dst in _CN_KEY_TOKEN_MAP:
        if src in s:
            key = s
            key = key.replace(src, dst)
            key = re.sub(r"[（）()【】\[\]：:、，,%％\-+/]+", "_", key)
            key = re.sub(r"[^A-Za-z0-9_]+", "_", key)
            key = re.sub(r"_+", "_", key).strip("_").lower()
            if key:
                return f"metrics.{key}"
    en = _auto_en_from_cn(s)
    slug = _slugify_en(en)
    if slug:
        return f"metrics.{slug}"
    return f"metrics.m_{_short_hash(s)}"


def _classify_metric(field_or_cn: str) -> tuple[str, str]:
    s = str(field_or_cn or "").strip().lower()
    if any(x in s for x in ["yoy", "qoq", "growth", "增长", "增速"]):
        return "growth", _SECTION_LABELS["growth"]
    if any(x in s for x in ["eps", "bps", "cfps", "ps", "每股"]):
        return "per_share", _SECTION_LABELS["per_share"]
    if any(x in s for x in ["roe", "roa", "roic", "回报", "收益率"]):
        return "returns", _SECTION_LABELS["returns"]
    if any(x in s for x in ["turn", "days", "周转", "营运"]):
        return "operation", _SECTION_LABELS["operation"]
    if any(x in s for x in ["current_ratio", "quick_ratio", "cash_ratio", "debt", "liab", "偿债", "负债", "流动比率", "速动比率", "现金比率", "产权比率", "债务"]):
        return "solvency", _SECTION_LABELS["solvency"]
    if any(x in s for x in ["ev", "ebitda", "cashflow", "现金流", "enterprise value", "估值"]):
        return "valuation", _SECTION_LABELS["valuation"]
    if any(x in s for x in ["margin", "profit", "收入", "利润", "毛利", "净利"]):
        return "profitability", _SECTION_LABELS["profitability"]
    return "other", _SECTION_LABELS["other"]


def _known_spec(alias: str) -> MetricSpec | None:
    return _METRIC_ALIAS_LOOKUP.get(str(alias or "").strip().lower())


def _row_from_known(spec: MetricSpec, value: object) -> dict[str, object]:
    return {
        "科目": spec.cn,
        "数值": value,
        "key": spec.key,
        "备注": spec.note,
        "英文": spec.en,
        "__level": 1,
        "__is_header": False,
        "__uncommon": False,
        "__section_key": spec.section_key,
        "__section_cn": spec.section_cn,
    }


def _row_from_tushare_field(field: str, value: object) -> dict[str, object]:
    spec = _known_spec(field)
    if spec is not None:
        return _row_from_known(spec, value)
    cn = _TUSHARE_FIELD_LABELS.get(field, field)
    section_key, section_cn = _classify_metric(field)
    return {
        "科目": cn,
        "数值": value,
        "key": f"metrics.{field}",
        "备注": "tushare fina_indicator 原始字段",
        "英文": _humanize_field_name(field),
        "__level": 1,
        "__is_header": False,
        "__uncommon": False,
        "__section_key": section_key,
        "__section_cn": section_cn,
    }


def _row_from_akshare_metric_name(name: str, value: object) -> dict[str, object]:
    spec = _known_spec(name)
    if spec is not None:
        return _row_from_known(spec, value)
    section_key, section_cn = _classify_metric(name)
    key = _metric_key_from_cn(name)
    en = _auto_en_from_cn(name) or name
    return {
        "科目": name,
        "数值": value,
        "key": key,
        "备注": "akshare 财务摘要原始指标",
        "英文": en,
        "__level": 1,
        "__is_header": False,
        "__uncommon": False,
        "__section_key": section_key,
        "__section_cn": section_cn,
    }


def _finalize_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return _empty_sheet()
    out_rows: list[dict[str, object]] = []
    current_section = None
    seen_keys: set[str] = set()
    for row in rows:
        sec_key = str(row.pop("__section_key"))
        sec_cn = str(row.pop("__section_cn"))
        if sec_key != current_section:
            out_rows.append({
                "科目": sec_cn,
                "数值": None,
                "key": f"metrics.section.{sec_key}",
                "备注": "",
                "英文": sec_cn,
                "__level": 0,
                "__is_header": True,
                "__uncommon": False,
            })
            current_section = sec_key
        key0 = str(row["key"])
        if key0 in seen_keys:
            key0 = f"{key0}__{_short_hash(str(row['科目']))[:4]}"
            row["key"] = key0
        seen_keys.add(key0)
        out_rows.append({k: row[k] for k in SHEET_COLUMNS})
    return pd.DataFrame(out_rows, columns=SHEET_COLUMNS)


def _build_from_tushare_source(source_df: pd.DataFrame, period_end: date) -> pd.DataFrame:
    if source_df is None or source_df.empty:
        return _empty_sheet()
    end_dates = source_df["end_date"].astype(str).map(_clean_period_str) if "end_date" in source_df.columns else pd.Series(dtype=str)
    sub = source_df[end_dates == period_end.strftime("%Y%m%d")].copy()
    if sub.empty:
        return _empty_sheet()
    row = sub.iloc[-1]
    rows: list[dict[str, object]] = []
    for field in row.index:
        if field in _METADATA_FIELDS:
            continue
        value = row.get(field)
        if pd.isna(value):
            continue
        rows.append(_row_from_tushare_field(str(field), value))
    rows.sort(key=lambda x: (str(x["__section_key"]), str(x["key"])))
    return _finalize_rows(rows)


def _build_from_akshare_source(source_df: pd.DataFrame, period_end: date) -> pd.DataFrame:
    if source_df is None or source_df.empty or "指标" not in source_df.columns:
        return _empty_sheet()
    period_key = period_end.strftime("%Y%m%d")
    period_col = None
    for col in source_df.columns:
        if _clean_period_str(col) == period_key:
            period_col = col
            break
    if period_col is None:
        return _empty_sheet()
    rows: list[dict[str, object]] = []
    for _, r in source_df.iterrows():
        name = str(r.get("指标") or "").strip()
        if not name:
            continue
        value = r.get(period_col)
        if pd.isna(value):
            continue
        rows.append(_row_from_akshare_metric_name(name, value))
    rows.sort(key=lambda x: (str(x["__section_key"]), str(x["key"])))
    return _finalize_rows(rows)


def build_metrics_sheet(source_df: pd.DataFrame | None, metrics_df: pd.DataFrame | None, period_end: date, provider_name: str | None) -> pd.DataFrame:
    provider = str(provider_name or "").strip().lower()
    if provider == "tushare":
        out = _build_from_tushare_source(source_df if source_df is not None else pd.DataFrame(), period_end)
        if not out.empty:
            return out
    if provider == "akshare" or provider == "mixed":
        out = _build_from_akshare_source(source_df if source_df is not None else pd.DataFrame(), period_end)
        if not out.empty:
            return out

    # fallback: use source shape inference first, then normalized summary metrics
    if source_df is not None and not source_df.empty:
        if "指标" in source_df.columns:
            out = _build_from_akshare_source(source_df, period_end)
        else:
            out = _build_from_tushare_source(source_df, period_end)
        if not out.empty:
            return out

    if metrics_df is None or metrics_df.empty:
        return _empty_sheet()
    end_dates = metrics_df["end_date"].astype(str).map(_clean_period_str) if "end_date" in metrics_df.columns else pd.Series(dtype=str)
    sub = metrics_df[end_dates == period_end.strftime("%Y%m%d")].copy()
    if sub.empty:
        return _empty_sheet()
    row = sub.iloc[-1]
    rows: list[dict[str, object]] = []
    for spec in METRIC_SPECS:
        field = spec.key.split(".", 1)[1]
        if field not in row.index:
            continue
        value = row.get(field)
        if pd.isna(value):
            continue
        rows.append(_row_from_known(spec, value))
    rows.sort(key=lambda x: (str(x["__section_key"]), str(x["key"])))
    return _finalize_rows(rows)
