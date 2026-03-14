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
    SubjectSpec("is.taxes_and_surcharges", "税金及附加", "Taxes and surcharges", aliases=("营业税金及附加",)), 
    SubjectSpec("is.selling_expense", "销售费用", "Selling expenses"),
    SubjectSpec("is.admin_expense", "管理费用", "Administrative expenses"),
    SubjectSpec("is.rnd_expense", "研发费用", "R&D expenses"),
    SubjectSpec("is.fin_expense", "财务费用", "Financial expenses"),
    SubjectSpec("is.impairment_loss", "资产减值损失", "Asset impairment loss"),
    SubjectSpec("is.credit_impairment_loss", "信用减值损失", "Credit impairment loss"),
    SubjectSpec("is.invest_income", "投资收益", "Investment income"),
    SubjectSpec(
        "is.invest_income_associates",
        "联营企业和合营企业的投资收益",
        "Investment income from associates and joint ventures",
        aliases=("其中：联营企业和合营企业的投资收益",),
    ),
    SubjectSpec("is.interest_income", "利息收入", "Interest income"),
    SubjectSpec("is.interest_expense", "利息费用", "Interest expense", aliases=("其中：利息费用",)),
    SubjectSpec("is.fv_change_income", "公允价值变动收益", "Gains from fair value changes"),
    SubjectSpec("is.other_income", "其他收益", "Other income"),
    SubjectSpec("is.operating_profit", "营业利润", "Operating profit"),
    SubjectSpec("is.asset_disposal_gain", "资产处置收益", "Gains from asset disposal", aliases=("非流动资产处置利得",)),
    SubjectSpec("is.asset_disposal_loss", "资产处置损失", "Losses from asset disposal", aliases=("非流动资产处置损失",)),
    SubjectSpec("is.non_operating_income", "营业外收入", "Non-operating income"),
    SubjectSpec("is.non_operating_expense", "营业外支出", "Non-operating expense"),
    SubjectSpec("is.total_profit", "利润总额", "Total profit"),
    SubjectSpec("is.income_tax", "所得税费用", "Income tax expense"),
    SubjectSpec("is.net_profit", "净利润", "Net profit"),
    SubjectSpec(
        "is.net_profit_continuing",
        "持续经营净利润",
        "Net profit from continuing operations",
        aliases=("（一）持续经营净利润",),
    ),
    SubjectSpec(
        "is.net_profit_excluding_nonrecurring",
        "扣除非经常性损益后的净利润",
        "Net profit excluding non-recurring items",
    ),
    SubjectSpec("is.net_profit_parent", "归属于母公司所有者的净利润", "Net profit attributable to parent"),
    SubjectSpec("is.minority_interest", "少数股东损益", "Minority interests"),
    SubjectSpec("is.oci", "其他综合收益", "Other comprehensive income"),
    SubjectSpec("is.total_comprehensive_income", "综合收益总额", "Total comprehensive income"),
    SubjectSpec(
        "is.total_comprehensive_income_parent",
        "归属于母公司所有者的综合收益总额",
        "Total comprehensive income attributable to parent",
        aliases=("归属于母公司股东的综合收益总额",),
    ),
    SubjectSpec(
        "is.total_comprehensive_income_minority",
        "归属于少数股东的综合收益总额",
        "Total comprehensive income attributable to minority interests",
    ),
    SubjectSpec(
        "is.oci_parent",
        "归属母公司所有者的其他综合收益",
        "Other comprehensive income attributable to parent",
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
    SubjectSpec("bs.total_cash", "总现金", "Total cash"),
    SubjectSpec("bs.trading_fin_assets", "交易性金融资产", "Trading financial assets"),
    SubjectSpec("bs.notes_receivable", "应收票据", "Notes receivable"),
    SubjectSpec("bs.accounts_receivable", "应收账款", "Accounts receivable"),
    SubjectSpec(
        "bs.notes_and_accounts_receivable",
        "应收票据及应收账款",
        "Notes and accounts receivable",
    ),
    SubjectSpec("bs.receivables_financing", "应收款项融资", "Receivables financing"),
    SubjectSpec("bs.prepayments", "预付款项", "Prepayments"),
    SubjectSpec("bs.other_receivables", "其他应收款", "Other receivables", aliases=("其他应收款合计",)), 
    SubjectSpec("bs.inventories", "存货", "Inventories"),
    SubjectSpec("bs.contract_assets", "合同资产", "Contract assets"),

    SubjectSpec("bs.interest_receivable", "应收利息", "Interest receivable"),
    SubjectSpec("bs.fixed_assets", "固定资产", "Fixed assets", aliases=("固定资产合计", "其中：固定资产")),
    SubjectSpec(
        "bs.construction_in_progress",
        "在建工程",
        "Construction in progress",
        aliases=("在建工程合计", "其中：在建工程"),
    ),
    SubjectSpec("bs.intangible_assets", "无形资产", "Intangible assets"),
    SubjectSpec("bs.long_term_deferred_expenses", "长期待摊费用", "Long-term deferred expenses"),
    SubjectSpec("bs.long_term_equity_investment", "长期股权投资", "Long-term equity investment"),
    SubjectSpec("bs.deferred_tax_assets", "递延所得税资产", "Deferred tax assets"),
    SubjectSpec("bs.other_non_current_fin_assets", "其他非流动金融资产", "Other non-current financial assets"),
    SubjectSpec(
        "bs.other_equity_instruments_investment",
        "其他权益工具投资",
        "Other investments in equity instruments",
    ),
    SubjectSpec("bs.other_non_current_assets", "其他非流动资产", "Other non-current assets"),

    SubjectSpec("bs.nca_due_within_one_year", "一年内到期的非流动资产", "Non-current assets due within one year"),
    SubjectSpec("bs.other_current_assets", "其他流动资产", "Other current assets"),
    SubjectSpec("bs.total_current_assets", "流动资产合计", "Total current assets"),
    SubjectSpec("bs.total_non_current_assets", "非流动资产合计", "Total non-current assets"),
    SubjectSpec("bs.total_assets", "资产总计", "Total assets", aliases=("资产合计",)), 

    SubjectSpec("bs.short_term_borrowings", "短期借款", "Short-term borrowings"),
    SubjectSpec("bs.notes_payable", "应付票据", "Notes payable", aliases=("其中：应付票据",)),
    SubjectSpec("bs.accounts_payable", "应付账款", "Accounts payable"),
    SubjectSpec(
        "bs.notes_and_accounts_payable",
        "应付票据及应付账款",
        "Notes and accounts payable",
    ),
    SubjectSpec("bs.interest_payable", "应付利息", "Interest payable", aliases=("其中：应付利息",)),
    SubjectSpec("bs.dividends_payable", "应付股利", "Dividends payable"),
    SubjectSpec("bs.advance_receipts", "预收款项", "Advance receipts"),
    SubjectSpec("bs.contract_liabilities", "合同负债", "Contract liabilities"),
    SubjectSpec("bs.payroll_payable", "应付职工薪酬", "Employee benefits payable"),
    SubjectSpec("bs.taxes_payable", "应交税费", "Taxes payable"),
    SubjectSpec("bs.other_payables", "其他应付款", "Other payables", aliases=("其他应付款合计",)), 
    SubjectSpec(
        "bs.ncl_due_within_one_year",
        "一年内到期的非流动负债",
        "Non-current liabilities due within one year",
    ),
    SubjectSpec("bs.other_current_liabilities", "其他流动负债", "Other current liabilities"),
    SubjectSpec("bs.total_current_liabilities", "流动负债合计", "Total current liabilities"),
    SubjectSpec("bs.long_term_borrowings", "长期借款", "Long-term borrowings"),
    SubjectSpec("bs.bonds_payable", "应付债券", "Bonds payable"),
    SubjectSpec(
        "bs.long_term_payables",
        "长期应付款",
        "Long-term payables",
        aliases=("长期应付款合计", "其中：长期应付款"),
    ),
    SubjectSpec(
        "bs.deferred_income_non_current",
        "递延收益-非流动负债",
        "Deferred income (non-current liabilities)",
    ),
    SubjectSpec("bs.other_non_current_liabilities", "其他非流动负债", "Other non-current liabilities"),
    SubjectSpec("bs.provisions", "预计负债", "Provisions"),
    SubjectSpec("bs.deferred_tax_liabilities", "递延所得税负债", "Deferred tax liabilities"),
    SubjectSpec("bs.total_non_current_liabilities", "非流动负债合计", "Total non-current liabilities"),
    SubjectSpec("bs.total_liabilities", "负债合计", "Total liabilities"),

    SubjectSpec("bs.share_capital", "实收资本（或股本）", "Share capital", aliases=("实收资本(或股本)",)), 
    SubjectSpec("bs.capital_reserve", "资本公积", "Capital reserve"),
    SubjectSpec("bs.surplus_reserve", "盈余公积", "Surplus reserve"),
    SubjectSpec("bs.retained_earnings", "未分配利润", "Retained earnings"),
    SubjectSpec("bs.other_comprehensive_income", "其他综合收益", "Other comprehensive income"),
    SubjectSpec("bs.treasury_stock", "库存股", "Treasury stock"),
    SubjectSpec(
        "bs.total_equity_parent",
        "归属于母公司所有者权益合计",
        "Total equity attributable to parent",
    ),
    SubjectSpec("bs.minority_equity", "少数股东权益", "Minority interests"),
    SubjectSpec("bs.total_equity", "所有者权益合计", "Total equity", aliases=("所有者权益（或股东权益）合计",)), 
    SubjectSpec(
        "bs.total_liabilities_and_equity",
        "负债和所有者权益总计",
        "Total liabilities and equity",
        aliases=(
            "负债和所有者权益合计",
            "负债和所有者权益（或股东权益）合计",
        ),
    ),

    # -------------------- Cash Flow (CF) --------------------
    SubjectSpec("cf.section.ops", "经营活动产生的现金流量", "Operating activities"),
    SubjectSpec("cf.section.investing", "投资活动产生的现金流量", "Investing activities"),
    SubjectSpec("cf.section.financing", "筹资活动产生的现金流量", "Financing activities"),
    SubjectSpec("cf.section.supplement", "补充资料", "Supplement"),

    SubjectSpec(
        "cf.net_cash_from_ops",
        "经营活动产生的现金流量净额",
        "Net cash from operating activities",
        aliases=("间接法-经营活动产生的现金流量净额",),
    ),
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
    SubjectSpec(
        "cf.net_increase_in_cash",
        "现金及现金等价物净增加额",
        "Net increase in cash and cash equivalents",
        aliases=("间接法-现金及现金等价物净增加额",),
    ),
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

    # --- Cash flow common items (indirect method + subtotals) ---
    SubjectSpec("cf.net_profit", "净利润", "Net profit"),
    SubjectSpec("cf.asset_impairment_provision", "资产减值准备", "Provision for asset impairment", aliases=("加：资产减值准备",)),
    SubjectSpec(
        "cf.depreciation",
        "固定资产折旧、油气资产折耗、生产性生物资产折旧",
        "Depreciation",
    ),
    SubjectSpec("cf.amortization_intangibles", "无形资产摊销", "Amortization of intangible assets"),
    SubjectSpec(
        "cf.amortization_long_term_deferred_expenses",
        "长期待摊费用摊销",
        "Amortization of long-term deferred expenses",
    ),
    SubjectSpec("cf.financial_expense", "财务费用", "Financial expenses"),
    SubjectSpec("cf.fv_change_loss", "公允价值变动损失", "Losses from fair value changes"),
    SubjectSpec("cf.investment_loss", "投资损失", "Investment loss"),
    SubjectSpec("cf.loss_on_disposal_of_fixed_assets", "固定资产报废损失", "Loss on disposal of fixed assets"),
    SubjectSpec(
        "cf.loss_on_disposal_of_long_term_assets",
        "处置固定资产、无形资产和其他长期资产的损失",
        "Loss on disposal of long-term assets",
    ),

    SubjectSpec("cf.decrease_in_inventories", "存货的减少", "Decrease in inventories"),
    SubjectSpec(
        "cf.decrease_in_operating_receivables",
        "经营性应收项目的减少",
        "Decrease in operating receivables",
    ),
    SubjectSpec(
        "cf.increase_in_operating_payables",
        "经营性应付项目的增加",
        "Increase in operating payables",
    ),
    SubjectSpec(
        "cf.increase_in_deferred_tax_liabilities",
        "递延所得税负债增加",
        "Increase in deferred tax liabilities",
    ),
    SubjectSpec(
        "cf.decrease_in_deferred_tax_assets",
        "递延所得税资产减少",
        "Decrease in deferred tax assets",
    ),

    SubjectSpec(
        "cf.cash_received_from_tax_refunds",
        "收到的税费与返还",
        "Cash received from tax refunds",
    ),
    SubjectSpec(
        "cf.cash_received_other_ops",
        "收到其他与经营活动有关的现金",
        "Other cash received relating to operating activities",
    ),
    SubjectSpec(
        "cf.cash_paid_to_employees",
        "支付给职工以及为职工支付的现金",
        "Cash paid to and for employees",
    ),
    SubjectSpec(
        "cf.cash_paid_for_taxes",
        "支付的各项税费",
        "Cash paid for taxes",
    ),
    SubjectSpec(
        "cf.cash_paid_other_ops",
        "支付其他与经营活动有关的现金",
        "Other cash paid relating to operating activities",
    ),

    SubjectSpec(
        "cf.ops_cash_inflow_subtotal",
        "经营活动现金流入小计",
        "Subtotal of cash inflows from operating activities",
    ),
    SubjectSpec(
        "cf.ops_cash_outflow_subtotal",
        "经营活动现金流出小计",
        "Subtotal of cash outflows from operating activities",
    ),

    SubjectSpec(
        "cf.cash_received_from_investment_recovery",
        "收回投资收到的现金",
        "Cash received from investment recovery",
    ),
    SubjectSpec(
        "cf.cash_received_from_investment_income",
        "取得投资收益收到的现金",
        "Cash received from investment income",
    ),
    SubjectSpec(
        "cf.cash_received_from_disposal_of_long_term_assets",
        "处置固定资产、无形资产和其他长期资产收回的现金净额",
        "Net cash received from disposal of long-term assets",
    ),
    SubjectSpec(
        "cf.cash_paid_for_purchase_of_long_term_assets",
        "购建固定资产、无形资产和其他长期资产支付的现金",
        "Cash paid for purchase and construction of long-term assets",
    ),
    SubjectSpec(
        "cf.cash_paid_for_investments",
        "投资支付的现金",
        "Cash paid for investments",
    ),
    SubjectSpec(
        "cf.cash_paid_other_inv",
        "支付其他与投资活动有关的现金",
        "Other cash paid relating to investing activities",
    ),
    SubjectSpec(
        "cf.cash_received_from_disposal_of_subsidiaries",
        "处置子公司及其他营业单位收到的现金净额",
        "Net cash received from disposal of subsidiaries and other business units",
    ),

    SubjectSpec(
        "cf.inv_cash_inflow_subtotal",
        "投资活动现金流入小计",
        "Subtotal of cash inflows from investing activities",
    ),
    SubjectSpec(
        "cf.inv_cash_outflow_subtotal",
        "投资活动现金流出小计",
        "Subtotal of cash outflows from investing activities",
    ),

    SubjectSpec(
        "cf.cash_received_from_borrowings",
        "取得借款收到的现金",
        "Cash received from borrowings",
    ),
    SubjectSpec(
        "cf.cash_received_from_investments",
        "吸收投资收到的现金",
        "Cash received from investments",
    ),
    SubjectSpec(
        "cf.cash_received_from_minority_investment_in_subsidiaries",
        "子公司吸收少数股东投资收到的现金",
        "Cash received from minority investments in subsidiaries",
        aliases=("其中：子公司吸收少数股东投资收到的现金",),
    ),
    SubjectSpec(
        "cf.cash_paid_for_debt_repayment",
        "偿还债务支付的现金",
        "Cash paid for debt repayment",
    ),
    SubjectSpec(
        "cf.cash_paid_for_dividends_interest",
        "分配股利、利润或偿付利息支付的现金",
        "Cash paid for dividends, profit distributions and interest",
    ),
    SubjectSpec(
        "cf.cash_received_other_fin",
        "收到其他与筹资活动有关的现金",
        "Other cash received relating to financing activities",
    ),
    SubjectSpec(
        "cf.cash_paid_other_fin",
        "支付其他与筹资活动有关的现金",
        "Other cash paid relating to financing activities",
    ),

    SubjectSpec(
        "cf.fin_cash_inflow_subtotal",
        "筹资活动现金流入小计",
        "Subtotal of cash inflows from financing activities",
    ),
    SubjectSpec(
        "cf.fin_cash_outflow_subtotal",
        "筹资活动现金流出小计",
        "Subtotal of cash outflows from financing activities",
    ),

    SubjectSpec(
        "cf.fx_effect_on_cash",
        "汇率变动对现金及现金等价物的影响",
        "Effect of exchange rate changes on cash and cash equivalents",
    ),

    SubjectSpec(
        "cf.cash_begin_alt",
        "现金的期初余额",
        "Cash balance at beginning of period",
        aliases=("减：现金的期初余额",),
    ),
    SubjectSpec(
        "cf.cash_end_alt",
        "现金的期末余额",
        "Cash balance at end of period",
    ),

    # Section headers (often value is blank)
    SubjectSpec(
        "cf.section.reconcile",
        "将净利润调节为经营活动现金流量",
        "Reconciliation of net profit to net cash from operating activities",
        aliases=("将净利润调节为经营活动现金流量",),
    ),
    SubjectSpec(
        "cf.section.supplement",
        "补充资料",
        "Supplement",
        aliases=("补充资料：",),
    ),
    SubjectSpec(
        "cf.section.non_cash",
        "不涉及现金收支的重大投资和筹资活动",
        "Significant investing and financing activities not involving cash",
        aliases=("不涉及现金收支的重大投资和筹资活动：",),
    ),
    SubjectSpec(
        "cf.section.cash_change",
        "现金及现金等价物净变动情况",
        "Net change in cash and cash equivalents",
        aliases=("现金及现金等价物净变动情况：",),
    ),

    # Very generic line used by some providers; keep key stable but will be uniquified by exporter.
    SubjectSpec("cf.other", "其他", "Other"),
]



def build_cn_lookup() -> dict[str, dict[str, SubjectSpec]]:
    """Return mapping: prefix -> cn/alias -> SubjectSpec."""

    m: dict[str, dict[str, SubjectSpec]] = {"is": {}, "bs": {}, "cf": {}}
    for spec in SUBJECT_SPECS:
        prefix = spec.key.split(".", 1)[0].strip()
        if prefix not in m:
            continue
        m[prefix][spec.cn] = spec
        for a in spec.aliases:
            m[prefix][a] = spec
    return m


def build_key_lookup() -> dict[str, SubjectSpec]:
    """Return mapping: full key -> SubjectSpec."""

    return {spec.key: spec for spec in SUBJECT_SPECS}


_CN_LOOKUP = build_cn_lookup()
_KEY_LOOKUP = build_key_lookup()


def lookup_subject(prefix: str, cn_name: str) -> SubjectSpec | None:
    s = (cn_name or "").strip()
    if not s:
        return None
    return _CN_LOOKUP.get(prefix, {}).get(s)


def lookup_subject_by_key(key: str) -> SubjectSpec | None:
    k = (key or "").strip()
    if not k:
        return None
    return _KEY_LOOKUP.get(k)
