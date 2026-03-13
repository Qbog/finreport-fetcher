from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectSpec:
    """A single statement item (subject) mapping.

    key: template key used by chart templates / expressions (e.g. is.revenue)
    cn:  CN name as appears in exported statements
    en:  English translation (short, for readability)
    aliases: additional CN names that should map to the same key/en
    """

    key: str
    cn: str
    en: str
    aliases: tuple[str, ...] = ()


# NOTE:
# - This is a curated starter glossary. It does not cover every possible statement line.
# - For unknown subjects, exporter will leave key/en empty and keep CN-only display.

SUBJECT_SPECS: list[SubjectSpec] = [
    # -------------------- Income Statement (IS) --------------------
    # Section headers inserted by provider (for readability)
    SubjectSpec("is.section.revenue", "收入", "Revenue"),
    SubjectSpec("is.section.costs", "成本费用", "Costs & expenses"),
    SubjectSpec("is.section.profit", "利润", "Profit"),
    SubjectSpec("is.section.comprehensive_income", "综合收益", "Comprehensive income"),

    SubjectSpec("is.revenue_total", "营业总收入", "Total operating revenue"),
    SubjectSpec("is.revenue", "营业收入", "Operating revenue", aliases=("主营业务收入",)),
    SubjectSpec("is.cogs", "营业成本", "Cost of sales"),
    SubjectSpec("is.total_costs", "营业总成本", "Total operating costs"),
    SubjectSpec("is.taxes_and_surcharges", "税金及附加", "Taxes and surcharges"),
    SubjectSpec("is.selling_expense", "销售费用", "Selling expenses"),
    SubjectSpec("is.admin_expense", "管理费用", "Administrative expenses"),
    SubjectSpec("is.rnd_expense", "研发费用", "R&D expenses"),
    SubjectSpec("is.fin_expense", "财务费用", "Financial expenses"),
    SubjectSpec("is.impairment_loss", "资产减值损失", "Asset impairment loss"),
    SubjectSpec("is.credit_impairment_loss", "信用减值损失", "Credit impairment loss"),
    SubjectSpec("is.invest_income", "投资收益", "Investment income"),
    SubjectSpec("is.fv_change_income", "公允价值变动收益", "Gains from fair value changes"),
    SubjectSpec("is.other_income", "其他收益", "Other income"),
    SubjectSpec("is.operating_profit", "营业利润", "Operating profit"),
    SubjectSpec("is.total_profit", "利润总额", "Total profit"),
    SubjectSpec("is.income_tax", "所得税费用", "Income tax expense"),
    SubjectSpec("is.net_profit", "净利润", "Net profit"),
    SubjectSpec("is.net_profit_parent", "归属于母公司所有者的净利润", "Net profit attributable to parent"),
    SubjectSpec("is.minority_interest", "少数股东损益", "Minority interests"),
    SubjectSpec("is.oci", "其他综合收益", "Other comprehensive income"),
    SubjectSpec("is.total_comprehensive_income", "综合收益总额", "Total comprehensive income"),
    SubjectSpec(
        "is.total_comprehensive_income_parent",
        "归属于母公司所有者的综合收益总额",
        "Total comprehensive income attributable to parent",
    ),
    SubjectSpec("is.eps", "每股收益", "Earnings per share"),
    SubjectSpec("is.eps_basic", "基本每股收益", "Basic EPS"),
    SubjectSpec("is.eps_diluted", "稀释每股收益", "Diluted EPS"),

    # -------------------- Balance Sheet (BS) --------------------
    SubjectSpec("bs.section.current_assets", "流动资产", "Current assets"),
    SubjectSpec("bs.section.non_current_assets", "非流动资产", "Non-current assets"),
    SubjectSpec("bs.section.current_liabilities", "流动负债", "Current liabilities"),
    SubjectSpec("bs.section.non_current_liabilities", "非流动负债", "Non-current liabilities"),
    SubjectSpec("bs.section.equity", "所有者权益", "Owners' equity", aliases=("股东权益",)),

    SubjectSpec("bs.cash", "货币资金", "Cash and cash equivalents"),
    SubjectSpec("bs.trading_fin_assets", "交易性金融资产", "Trading financial assets"),
    SubjectSpec("bs.notes_receivable", "应收票据", "Notes receivable"),
    SubjectSpec("bs.accounts_receivable", "应收账款", "Accounts receivable"),
    SubjectSpec("bs.receivables_financing", "应收款项融资", "Receivables financing"),
    SubjectSpec("bs.prepayments", "预付款项", "Prepayments"),
    SubjectSpec("bs.other_receivables", "其他应收款", "Other receivables"),
    SubjectSpec("bs.inventories", "存货", "Inventories"),
    SubjectSpec("bs.contract_assets", "合同资产", "Contract assets"),
    SubjectSpec("bs.nca_due_within_one_year", "一年内到期的非流动资产", "Non-current assets due within one year"),
    SubjectSpec("bs.other_current_assets", "其他流动资产", "Other current assets"),
    SubjectSpec("bs.total_current_assets", "流动资产合计", "Total current assets"),
    SubjectSpec("bs.total_non_current_assets", "非流动资产合计", "Total non-current assets"),
    SubjectSpec("bs.total_assets", "资产总计", "Total assets"),

    SubjectSpec("bs.short_term_borrowings", "短期借款", "Short-term borrowings"),
    SubjectSpec("bs.notes_payable", "应付票据", "Notes payable"),
    SubjectSpec("bs.accounts_payable", "应付账款", "Accounts payable"),
    SubjectSpec("bs.advance_receipts", "预收款项", "Advance receipts"),
    SubjectSpec("bs.contract_liabilities", "合同负债", "Contract liabilities"),
    SubjectSpec("bs.payroll_payable", "应付职工薪酬", "Employee benefits payable"),
    SubjectSpec("bs.taxes_payable", "应交税费", "Taxes payable"),
    SubjectSpec("bs.other_payables", "其他应付款", "Other payables"),
    SubjectSpec(
        "bs.ncl_due_within_one_year",
        "一年内到期的非流动负债",
        "Non-current liabilities due within one year",
    ),
    SubjectSpec("bs.other_current_liabilities", "其他流动负债", "Other current liabilities"),
    SubjectSpec("bs.total_current_liabilities", "流动负债合计", "Total current liabilities"),
    SubjectSpec("bs.long_term_borrowings", "长期借款", "Long-term borrowings"),
    SubjectSpec("bs.bonds_payable", "应付债券", "Bonds payable"),
    SubjectSpec("bs.provisions", "预计负债", "Provisions"),
    SubjectSpec("bs.deferred_tax_liabilities", "递延所得税负债", "Deferred tax liabilities"),
    SubjectSpec("bs.total_non_current_liabilities", "非流动负债合计", "Total non-current liabilities"),
    SubjectSpec("bs.total_liabilities", "负债合计", "Total liabilities"),

    SubjectSpec("bs.share_capital", "实收资本(或股本)", "Share capital"),
    SubjectSpec("bs.capital_reserve", "资本公积", "Capital reserve"),
    SubjectSpec("bs.surplus_reserve", "盈余公积", "Surplus reserve"),
    SubjectSpec("bs.retained_earnings", "未分配利润", "Retained earnings"),
    SubjectSpec(
        "bs.total_equity_parent",
        "归属于母公司所有者权益合计",
        "Total equity attributable to parent",
    ),
    SubjectSpec("bs.minority_equity", "少数股东权益", "Minority interests"),
    SubjectSpec("bs.total_equity", "所有者权益合计", "Total equity"),
    SubjectSpec(
        "bs.total_liabilities_and_equity",
        "负债和所有者权益总计",
        "Total liabilities and equity",
    ),

    # -------------------- Cash Flow (CF) --------------------
    SubjectSpec("cf.section.ops", "经营活动产生的现金流量", "Operating activities"),
    SubjectSpec("cf.section.investing", "投资活动产生的现金流量", "Investing activities"),
    SubjectSpec("cf.section.financing", "筹资活动产生的现金流量", "Financing activities"),
    SubjectSpec("cf.section.supplement", "补充资料", "Supplement"),

    SubjectSpec("cf.net_cash_from_ops", "经营活动产生的现金流量净额", "Net cash from operating activities"),
    SubjectSpec(
        "cf.net_cash_from_investing",
        "投资活动产生的现金流量净额",
        "Net cash from investing activities",
    ),
    SubjectSpec(
        "cf.net_cash_from_financing",
        "筹资活动产生的现金流量净额",
        "Net cash from financing activities",
    ),
    SubjectSpec("cf.net_increase_in_cash", "现金及现金等价物净增加额", "Net increase in cash and cash equivalents"),
    SubjectSpec(
        "cf.cash_begin",
        "期初现金及现金等价物余额",
        "Cash and cash equivalents at beginning of period",
    ),
    SubjectSpec(
        "cf.cash_end",
        "期末现金及现金等价物余额",
        "Cash and cash equivalents at end of period",
    ),
    SubjectSpec(
        "cf.cash_received_from_sales",
        "销售商品、提供劳务收到的现金",
        "Cash received from sales of goods and services",
    ),
    SubjectSpec(
        "cf.cash_paid_for_goods",
        "购买商品、接受劳务支付的现金",
        "Cash paid for goods and services",
    ),
]


def build_cn_lookup() -> dict[str, dict[str, SubjectSpec]]:
    """Return mapping: prefix -> cn/alias -> SubjectSpec."""

    m: dict[str, dict[str, SubjectSpec]] = {"is": {}, "bs": {}, "cf": {}}
    for spec in SUBJECT_SPECS:
        # prefix is the first token in key
        prefix = spec.key.split(".", 1)[0].strip()
        if prefix not in m:
            continue
        m[prefix][spec.cn] = spec
        for a in spec.aliases:
            m[prefix][a] = spec
    return m


_CN_LOOKUP = build_cn_lookup()


def lookup_subject(prefix: str, cn_name: str) -> SubjectSpec | None:
    s = (cn_name or "").strip()
    if not s:
        return None
    return _CN_LOOKUP.get(prefix, {}).get(s)
