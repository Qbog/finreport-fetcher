from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

import pandas as pd

from finreport_fetcher.mappings.enrich import _slugify_en


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
    MetricSpec("metrics.roa", "总资产报酬率(ROA)", "Return on assets (ROA)", "returns", "回报能力", aliases=("ROA", "总资产报酬率", "总资产净利率", "roa", "总资产报酬率"), note="百分比指标；不同数据源口径可能略有差异。"),
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

_AKSHARE_SECTION_MAP = {
    "常用指标": ("highlights", "常用指标", "Highlights"),
    "每股指标": ("per_share", "每股指标", "Per-share metrics"),
    "盈利能力": ("profitability", "盈利能力", "Profitability"),
    "成长能力": ("growth", "成长能力", "Growth"),
    "收益质量": ("quality", "收益质量", "Earnings quality"),
    "财务风险": ("solvency", "财务风险", "Financial risk"),
    "营运能力": ("operation", "营运能力", "Operating efficiency"),
}

_CN_TO_EN_EXACT = {
    "归母净利润": "Parent net profit",
    "营业总收入": "Total operating revenue",
    "营业成本": "Operating cost",
    "净利润": "Net profit",
    "扣非净利润": "Net profit excluding non-recurring items",
    "股东权益合计(净资产)": "Total equity (net assets)",
    "商誉": "Goodwill",
    "经营现金流量净额": "Net operating cashflow",
    "总资产报酬率(ROA)": "Return on assets (ROA)",
    "总资产报酬率": "Return on assets",
    "企业价值(EV)": "Enterprise value (EV)",
    "息税前利润(EBIT)": "EBIT",
    "基本每股收益": "Basic EPS",
    "基本每股收益(EPS)": "Basic EPS",
    "稀释每股收益": "Diluted EPS",
    "摊薄每股收益_最新股数": "Diluted EPS (latest shares)",
    "摊薄每股净资产_期末股数": "Diluted BPS (period-end shares)",
    "调整每股净资产_期末股数": "Adjusted BPS (period-end shares)",
    "每股净资产(BPS)": "Book value per share (BPS)",
    "每股净资产_最新股数": "BPS (latest shares)",
    "每股经营现金流": "Operating cashflow per share",
    "每股现金流": "Cashflow per share",
    "每股现金流量净额": "Net cashflow per share",
    "每股企业自由现金流量": "FCFF per share",
    "每股股东自由现金流量": "FCFE per share",
    "每股未分配利润": "Undistributed profit per share",
    "每股资本公积金": "Capital reserve per share",
    "每股盈余公积金": "Surplus reserve per share",
    "每股留存收益": "Retained earnings per share",
    "每股营业收入": "Operating revenue per share",
    "每股营业总收入": "Total operating revenue per share",
    "每股息税前利润": "EBIT per share",
    "净资产收益率(ROE)": "Return on equity (ROE)",
    "摊薄净资产收益率": "Diluted return on equity",
    "净资产收益率_平均": "Average return on equity",
    "净资产收益率_平均_扣除非经常损益": "Average return on equity excluding non-recurring items",
    "摊薄净资产收益率_扣除非经常损益": "Diluted return on equity excluding non-recurring items",
    "息税前利润率": "EBIT margin",
    "总资产报酬率": "Return on assets",
    "总资本回报率": "Return on total capital",
    "投入资本回报率": "Return on invested capital",
    "息前税后总资产报酬率_平均": "Average after-tax return on assets",
    "毛利率": "Gross margin",
    "销售净利率": "Net margin",
    "期间费用率": "Period expense ratio",
    "成本费用利润率": "Cost expense profit ratio",
    "营业利润率": "Operating margin",
    "总资产净利率_平均": "Average return on assets",
    "总资产净利率_平均(含少数股东损益)": "Average return on assets incl. minority interests",
    "营业总收入增长率": "Total operating revenue growth rate",
    "归属母公司净利润增长率": "Parent net profit growth rate",
    "经营活动净现金/销售收入": "Operating cash to sales",
    "经营性现金净流量/营业总收入": "Operating cashflow to total operating revenue",
    "成本费用率": "Cost expense ratio",
    "销售成本率": "Cost of sales ratio",
    "经营活动净现金/归属母公司的净利润": "Operating cash to parent net profit",
    "所得税/利润总额": "Income tax to total profit",
    "流动比率": "Current ratio",
    "速动比率": "Quick ratio",
    "保守速动比率": "Conservative quick ratio",
    "资产负债率": "Debt to assets ratio",
    "权益乘数": "Equity multiplier",
    "权益乘数(含少数股权的净资产)": "Equity multiplier incl. minority interests",
    "产权比率": "Debt to equity ratio",
    "现金比率": "Cash ratio",
    "应收账款周转率": "Accounts receivable turnover ratio",
    "应收账款周转天数": "Accounts receivable turnover days",
    "存货周转率": "Inventory turnover ratio",
    "存货周转天数": "Inventory turnover days",
    "总资产周转率": "Asset turnover ratio",
    "总资产周转天数": "Asset turnover days",
    "流动资产周转率": "Current asset turnover ratio",
    "流动资产周转天数": "Current asset turnover days",
    "应付账款周转率": "Accounts payable turnover ratio",
}

_CN_TO_KEY_EXACT = {
    "归母净利润": "metrics.parent_net_profit",
    "营业总收入": "metrics.total_operating_revenue",
    "营业成本": "metrics.operating_cost",
    "净利润": "metrics.net_profit",
    "扣非净利润": "metrics.net_profit_excluding_non_recurring_items",
    "股东权益合计(净资产)": "metrics.total_equity_net_assets",
    "商誉": "metrics.goodwill",
    "经营现金流量净额": "metrics.net_operating_cashflow",
    "基本每股收益": "metrics.basic_eps",
    "稀释每股收益": "metrics.diluted_eps",
    "摊薄每股收益_最新股数": "metrics.diluted_eps_latest_shares",
    "摊薄每股净资产_期末股数": "metrics.diluted_bps_period_end_shares",
    "调整每股净资产_期末股数": "metrics.adjusted_bps_period_end_shares",
    "每股净资产_最新股数": "metrics.bps_latest_shares",
    "每股经营现金流": "metrics.operating_cashflow_per_share",
    "每股现金流": "metrics.cashflow_per_share",
    "每股现金流量净额": "metrics.net_cashflow_per_share",
    "每股企业自由现金流量": "metrics.fcff_per_share",
    "每股股东自由现金流量": "metrics.fcfe_per_share",
    "每股未分配利润": "metrics.undistributed_profit_per_share",
    "每股资本公积金": "metrics.capital_reserve_per_share",
    "每股盈余公积金": "metrics.surplus_reserve_per_share",
    "每股留存收益": "metrics.retained_earnings_per_share",
    "每股营业收入": "metrics.operating_revenue_per_share",
    "每股营业总收入": "metrics.total_operating_revenue_per_share",
    "每股息税前利润": "metrics.ebit_per_share",
    "净资产收益率(ROE)": "metrics.roe",
    "摊薄净资产收益率": "metrics.diluted_roe",
    "净资产收益率_平均": "metrics.average_roe",
    "净资产收益率_平均_扣除非经常损益": "metrics.average_roe_excluding_non_recurring_items",
    "摊薄净资产收益率_扣除非经常损益": "metrics.diluted_roe_excluding_non_recurring_items",
    "息税前利润率": "metrics.ebit_margin",
    "总资产报酬率(ROA)": "metrics.return_on_assets_roa",
    "总资产报酬率": "metrics.return_on_assets",
    "总资本回报率": "metrics.return_on_total_capital",
    "投入资本回报率": "metrics.return_on_invested_capital",
    "息前税后总资产报酬率_平均": "metrics.average_after_tax_roa",
    "毛利率": "metrics.gross_margin",
    "销售净利率": "metrics.net_margin",
    "期间费用率": "metrics.period_expense_ratio",
    "成本费用利润率": "metrics.cost_expense_profit_ratio",
    "营业利润率": "metrics.operating_margin",
    "总资产净利率_平均": "metrics.average_roa",
    "总资产净利率_平均(含少数股东损益)": "metrics.average_roa_including_minority_interests",
    "营业总收入增长率": "metrics.total_operating_revenue_growth_rate",
    "归属母公司净利润增长率": "metrics.parent_net_profit_growth_rate",
    "经营活动净现金/销售收入": "metrics.operating_cash_to_sales",
    "经营性现金净流量/营业总收入": "metrics.operating_cashflow_to_total_operating_revenue",
    "成本费用率": "metrics.cost_expense_ratio",
    "销售成本率": "metrics.cost_of_sales_ratio",
    "经营活动净现金/归属母公司的净利润": "metrics.operating_cash_to_parent_net_profit",
    "所得税/利润总额": "metrics.income_tax_to_total_profit",
    "流动比率": "metrics.current_ratio",
    "速动比率": "metrics.quick_ratio",
    "保守速动比率": "metrics.conservative_quick_ratio",
    "资产负债率": "metrics.debt_to_assets_ratio",
    "权益乘数": "metrics.equity_multiplier",
    "权益乘数(含少数股权的净资产)": "metrics.equity_multiplier_including_minority_interests",
    "产权比率": "metrics.debt_to_equity_ratio",
    "现金比率": "metrics.cash_ratio",
    "应收账款周转率": "metrics.accounts_receivable_turnover_ratio",
    "应收账款周转天数": "metrics.accounts_receivable_turnover_days",
    "存货周转率": "metrics.inventory_turnover_ratio",
    "存货周转天数": "metrics.inventory_turnover_days",
    "总资产周转率": "metrics.asset_turnover_ratio",
    "总资产周转天数": "metrics.asset_turnover_days",
    "流动资产周转率": "metrics.current_asset_turnover_ratio",
    "流动资产周转天数": "metrics.current_asset_turnover_days",
    "应付账款周转率": "metrics.accounts_payable_turnover_ratio",
}

_FALLBACK_CN_TO_EN = [
    ("归属母公司", "parent company"),
    ("归母", "parent"),
    ("营业总收入", "total operating revenue"),
    ("营业收入", "operating revenue"),
    ("营业成本", "operating cost"),
    ("营业利润", "operating profit"),
    ("净利润", "net profit"),
    ("扣非", "excluding non-recurring items"),
    ("股东权益合计", "total equity"),
    ("净资产", "net assets"),
    ("商誉", "goodwill"),
    ("经营现金流量净额", "net operating cashflow"),
    ("经营性现金净流量", "operating cashflow"),
    ("经营活动净现金", "operating cash"),
    ("经营活动", "operating activities"),
    ("企业自由现金流量", "fcff"),
    ("股东自由现金流量", "fcfe"),
    ("自由现金流量", "free cashflow"),
    ("基本每股收益", "basic eps"),
    ("稀释每股收益", "diluted eps"),
    ("每股净资产", "bps"),
    ("每股经营现金流", "operating cashflow per share"),
    ("每股现金流量净额", "net cashflow per share"),
    ("每股现金流", "cashflow per share"),
    ("每股营业总收入", "total operating revenue per share"),
    ("每股营业收入", "operating revenue per share"),
    ("每股息税前利润", "ebit per share"),
    ("每股未分配利润", "undistributed profit per share"),
    ("每股资本公积金", "capital reserve per share"),
    ("每股盈余公积金", "surplus reserve per share"),
    ("每股留存收益", "retained earnings per share"),
    ("净资产收益率", "return on equity"),
    ("总资产报酬率", "return on assets"),
    ("总资产净利率", "return on assets"),
    ("总资本回报率", "return on total capital"),
    ("投入资本回报率", "return on invested capital"),
    ("毛利率", "gross margin"),
    ("销售净利率", "net margin"),
    ("期间费用率", "period expense ratio"),
    ("成本费用利润率", "cost expense profit ratio"),
    ("成本费用率", "cost expense ratio"),
    ("销售成本率", "cost of sales ratio"),
    ("营业利润率", "operating margin"),
    ("资产负债率", "debt to assets ratio"),
    ("流动比率", "current ratio"),
    ("速动比率", "quick ratio"),
    ("保守速动比率", "conservative quick ratio"),
    ("现金比率", "cash ratio"),
    ("产权比率", "debt to equity ratio"),
    ("权益乘数", "equity multiplier"),
    ("应收账款", "accounts receivable"),
    ("应付账款", "accounts payable"),
    ("存货", "inventory"),
    ("总资产", "asset"),
    ("流动资产", "current asset"),
    ("周转率", "turnover ratio"),
    ("周转天数", "turnover days"),
    ("增长率", "growth rate"),
    ("同比", "year-on-year"),
    ("环比", "quarter-on-quarter"),
    ("所得税", "income tax"),
    ("利润总额", "total profit"),
    ("息税前利润", "ebit"),
    ("息前税后", "after-tax"),
    ("平均", "average"),
    ("摊薄", "diluted"),
    ("最新股数", "latest shares"),
    ("期末股数", "period-end shares"),
    ("含少数股权的净资产", "including minority interests"),
    ("含少数股东损益", "including minority interests"),
]


def _empty_sheet() -> pd.DataFrame:
    return pd.DataFrame(columns=SHEET_COLUMNS)


def _clean_period_str(v: object) -> str:
    return re.sub(r"[^0-9]", "", str(v or ""))


def _humanize_field_name(field: str) -> str:
    return str(field or "").replace("_", " ").strip().title() or str(field or "")


def _english_from_key(key: str) -> str:
    tail = str(key or "").split(".")[-1].replace("_", " ").strip()
    return tail.title() if tail else "Indicator"


def _translate_cn_metric(cn: str) -> str:
    s = str(cn or "").strip()
    if not s:
        return ""
    if s in _CN_TO_EN_EXACT:
        return _CN_TO_EN_EXACT[s]
    out = s
    for src, dst in _FALLBACK_CN_TO_EN:
        out = out.replace(src, dst)
    out = re.sub(r"[（）()【】\[\]：:、，,%％\-+/]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"[\u4e00-\u9fff]+", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _metric_key_from_cn(cn: str) -> str:
    s = str(cn or "").strip()
    if not s:
        return "metrics.indicator"
    if s in _CN_TO_KEY_EXACT:
        return _CN_TO_KEY_EXACT[s]
    en = _translate_cn_metric(s)
    slug = _slugify_en(en)
    return f"metrics.{slug}" if slug else "metrics.indicator"


def _classify_metric(field_or_cn: str) -> tuple[str, str]:
    s = str(field_or_cn or "").strip().lower()
    if any(x in s for x in ["yoy", "qoq", "growth", "增长", "增速"]):
        return "growth", "成长能力"
    if any(x in s for x in ["eps", "bps", "cfps", "ps", "每股"]):
        return "per_share", "每股指标"
    if any(x in s for x in ["roe", "roa", "roic", "回报", "收益率"]):
        return "returns", "回报能力"
    if any(x in s for x in ["turn", "days", "周转", "营运"]):
        return "operation", "营运效率"
    if any(x in s for x in ["current_ratio", "quick_ratio", "cash_ratio", "debt", "liab", "偿债", "负债", "流动比率", "速动比率", "现金比率", "产权比率", "债务"]):
        return "solvency", "偿债与流动性"
    if any(x in s for x in ["ev", "ebitda", "cashflow", "现金流", "enterprise value", "估值"]):
        return "valuation", "估值与现金创造"
    if any(x in s for x in ["margin", "profit", "收入", "利润", "毛利", "净利"]):
        return "profitability", "盈利能力"
    return "other", "其他指标"


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
        "__section_en": _english_from_key(spec.section_key),
    }


def _row_from_tushare_field(field: str, value: object) -> dict[str, object]:
    spec = _known_spec(field)
    if spec is not None:
        return _row_from_known(spec, value)
    cn = _TUSHARE_FIELD_LABELS.get(field, field)
    section_key, section_cn = _classify_metric(field)
    en = _translate_cn_metric(cn) or _humanize_field_name(field)
    return {
        "科目": cn,
        "数值": value,
        "key": f"metrics.{field}",
        "备注": "tushare fina_indicator 原始字段",
        "英文": en,
        "__level": 1,
        "__is_header": False,
        "__uncommon": False,
        "__section_key": section_key,
        "__section_cn": section_cn,
        "__section_en": _english_from_key(section_key),
    }


def _row_from_akshare_metric_name(name: str, value: object, section_name: str | None) -> dict[str, object]:
    # 对 akshare 财务摘要：保留原始 section 与原始中文指标名。
    if section_name and section_name in _AKSHARE_SECTION_MAP:
        section_key, section_cn, section_en = _AKSHARE_SECTION_MAP[section_name]
    else:
        section_key, section_cn = _classify_metric(name)
        section_en = _english_from_key(section_key)
    base_key = _metric_key_from_cn(name)
    tail = base_key.split('.', 1)[1] if base_key.startswith('metrics.') else base_key
    key = f"metrics.{section_key}.{tail}" if section_key else f"metrics.{tail}"
    en = _translate_cn_metric(name) or _english_from_key(key)
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
        "__section_en": section_en,
    }


def _finalize_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return _empty_sheet()
    out_rows: list[dict[str, object]] = []
    current_section = None
    seen_rows: set[tuple[str, str, str]] = set()
    for row in rows:
        sec_key = str(row.pop("__section_key"))
        sec_cn = str(row.pop("__section_cn"))
        sec_en = str(row.pop("__section_en"))
        key0 = str(row["key"])
        subj0 = str(row["科目"])
        dup_key = (sec_key, key0, subj0)
        if dup_key in seen_rows:
            continue
        if sec_key != current_section:
            out_rows.append({
                "科目": sec_cn,
                "数值": None,
                "key": f"metrics.section.{sec_key}",
                "备注": "",
                "英文": sec_en,
                "__level": 0,
                "__is_header": True,
                "__uncommon": False,
            })
            current_section = sec_key
        seen_rows.add(dup_key)
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
    rows.sort(key=lambda x: (str(x["__section_key"]), str(x["key"]), str(x["科目"])))
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
        section_name = str(r.get("选项") or "").strip() or None
        rows.append(_row_from_akshare_metric_name(name, value, section_name))

    def _akshare_row_sort(item: dict[str, object]) -> tuple[str, int, str]:
        sec = str(item["__section_key"])
        # 常用指标里常有重复摘要，放后面，便于更具体分类优先保留
        priority = 1 if sec == "highlights" else 0
        return (sec, priority, str(item["key"]))

    rows.sort(key=_akshare_row_sort)
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
