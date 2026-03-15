from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectSpec:
    """A single statement item (subject) mapping.

    key: template key used by chart templates / expressions (e.g. is.revenue)
    cn:  CN name as appears in exported statements
    en:  English translation (short, for readability)
    aliases: additional CN names that should map to the same key/en
    common: whether it is a common, cross-industry subject
    note: optional CN note to show in exported Excel
    """

    key: str
    cn: str
    en: str
    aliases: tuple[str, ...] = ()
    # 是否“通用科目”：
    # - 若 common_in 为空：common=False 表示仅少数公司/行业/会计准则下出现（全局非通用）。
    # - 若 common_in 非空：则按公司类别判断是否通用（类别内通用/类别外非通用）。
    common: bool = True

    # 通用类别列表：例如银行特有科目可设置 common_in=("bank",)
    # 为空表示“对所有类别都通用”（或由 common=False 作为全局非通用）。
    common_in: tuple[str, ...] = ()

    # 备注说明（中文），用于解释口径/出现条件等（写入导出 Excel 的“备注”列）
    note: str = ""


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
        aliases=(
            "其中：联营企业和合营企业的投资收益",
            "对联营企业和合营企业的投资收益",
            "对联营公司的投资收益",
        ),
    ),
    SubjectSpec("is.interest_income", "利息收入", "Interest income"),
    SubjectSpec(
        "is.net_interest_income",
        "利息净收入",
        "Net interest income",
        aliases=("净利息收入",),
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.interest_expense",
        "利息费用",
        "Interest expense",
        aliases=("其中：利息费用", "利息支出"),
    ),

    # Bank-specific income/expense lines
    SubjectSpec(
        "is.operating_expense",
        "营业支出",
        "Operating expenses",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.net_fee_and_commission_income",
        "手续费及佣金净收入",
        "Net fee and commission income",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.fee_and_commission_income",
        "手续费及佣金收入",
        "Fee and commission income",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.fee_and_commission_expense",
        "手续费及佣金支出",
        "Fee and commission expense",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.fx_gain",
        "汇兑收益",
        "Foreign exchange gains",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.other_operating_revenue",
        "其他业务收入",
        "Other operating revenue",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.other_operating_cost",
        "其他业务成本",
        "Other operating cost",
        aliases=("其他业务支出",),
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.operating_and_admin_expense",
        "业务及管理费",
        "Operating and administrative expenses",
        aliases=("业务及管理费用",),
        common_in=("bank",),
    ),

    # Securities / financial institutions
    SubjectSpec(
        "is.net_trading_income",
        "净交易收入",
        "Net trading income",
        common_in=("bank", "securities"),
    ),
    SubjectSpec(
        "is.securities_brokerage_fee_net",
        "经纪业务手续费净收入",
        "Net brokerage fee income",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_investment_banking_fee_net",
        "投资银行业务手续费净收入",
        "Net investment banking fee income",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_asset_management_fee_net",
        "资产管理业务手续费净收入",
        "Net asset management fee income",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_fee_net",
        "手续费净收入",
        "Net fee income",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_agency_trading_net_income",
        "代理买卖证券业务净收入",
        "Net income from securities brokerage",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_underwriting_net_income",
        "证券承销业务净收入",
        "Net income from securities underwriting",
        common_in=("securities",),
    ),
    SubjectSpec(
        "is.securities_trust_asset_management_net_income",
        "委托管理资产业务净收入",
        "Net income from entrusted asset management",
        common_in=("securities",),
    ),

    # Insurance
    SubjectSpec(
        "is.insurance_premium_earned",
        "已赚保费",
        "Premiums earned",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.insurance_revenue",
        "保险业务收入",
        "Insurance revenue",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.reinsurance_premium_income",
        "分保费收入",
        "Reinsurance premium income",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.premiums_ceded",
        "分出保费",
        "Premiums ceded",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.change_in_unearned_premium_reserve",
        "提取未到期责任准备金",
        "Increase in unearned premium reserve",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.surrender_benefits",
        "退保金",
        "Surrender benefits",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.claims_expense",
        "赔付支出",
        "Claims expense",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.reinsurance_claims_recovered",
        "摊回赔付支出",
        "Reinsurance claims recovered",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.change_in_policy_reserves",
        "提取保险责任准备金",
        "Increase in insurance contract reserves",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "is.reinsurance_policy_reserves_recovered",
        "摊回保险责任准备金",
        "Reinsurance reserves recovered",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.policy_dividend_expense",
        "保单红利支出",
        "Policy dividend expense",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.reinsurance_expense",
        "分保费用",
        "Reinsurance expense",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "is.reinsurance_expense_recovered",
        "摊回分保费用",
        "Reinsurance expense recovered",
        common_in=("insurance",),
        common=False,
    ),

    SubjectSpec(
        "is.fx_net_gain",
        "汇兑净收益",
        "Net foreign exchange gains",
        common=False,
        note="非通用科目：部分金融公司或涉外业务较多的公司会单列披露。",
    ),

    SubjectSpec(
        "is.fv_change_income",
        "公允价值变动收益",
        "Gains from fair value changes",
        aliases=("公允价值变动收益/(损失)", "公允价值变动收益/（损失）"),
    ),
    SubjectSpec("is.other_income", "其他收益", "Other income"),
    SubjectSpec("is.operating_profit", "营业利润", "Operating profit"),
    SubjectSpec("is.asset_disposal_gain", "资产处置收益", "Gains from asset disposal", aliases=("非流动资产处置利得",)),
    SubjectSpec("is.asset_disposal_loss", "资产处置损失", "Losses from asset disposal", aliases=("非流动资产处置损失",)),
    SubjectSpec("is.non_operating_income", "营业外收入", "Non-operating income"),
    SubjectSpec("is.non_operating_expense", "营业外支出", "Non-operating expense"),
    SubjectSpec("is.total_profit", "利润总额", "Total profit"),
    SubjectSpec(
        "is.income_tax",
        "所得税费用",
        "Income tax expense",
        aliases=("所得税",),
    ),
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
        aliases=("扣除非经常性损益后的利润",),
    ),
    SubjectSpec(
        "is.net_profit_parent",
        "归属于母公司所有者的净利润",
        "Net profit attributable to parent",
        aliases=("归属母公司所有者的净利润", "归属于母公司的净利润"),
    ),
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
        aliases=("归属于母公司所有者的其他综合收益",),
    ),
    SubjectSpec(
        "is.oci_minority",
        "归属于少数股东的其他综合收益",
        "Other comprehensive income attributable to minority interests",
        common=False,
        note="非通用科目：仅在披露将OCI在母公司/少数股东之间分拆时出现。",
    ),
    SubjectSpec("is.eps", "每股收益", "Earnings per share"),
    SubjectSpec("is.eps_basic", "基本每股收益", "Basic EPS"),
    SubjectSpec("is.eps_diluted", "稀释每股收益", "Diluted EPS"),
    SubjectSpec(
        "is.retained_earnings_begin",
        "年初未分配利润",
        "Retained earnings (beginning)",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.distributable_profit",
        "可供分配的利润",
        "Profit available for distribution",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.transfer_to_general_risk_reserve",
        "提取一般风险准备",
        "Transfer to general risk reserve",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.profit_available_to_shareholders",
        "可供股东分配的利润",
        "Profit available to shareholders",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.retained_earnings_end",
        "未分配利润",
        "Undistributed profit",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.transfer_to_statutory_surplus_reserve",
        "提取法定盈余公积",
        "Transfer to statutory surplus reserve",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.discretionary_surplus_reserve_appropriation",
        "提取任意盈余公积",
        "Transfer to discretionary surplus reserve",
        common_in=("bank",),
        common=False,
        note="非通用科目：部分金融公司在利润分配时才会列示。",
    ),
    SubjectSpec(
        "is.dividends_payable",
        "应付普通股股利",
        "Dividends payable",
        common=False,
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.preferred_dividend_payable",
        "应付优先股股利",
        "Preferred dividends payable",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.oci_not_reclassed",
        "以后不能重分类进损益的其他综合收益",
        "OCI not reclassified to profit or loss",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.oci_reclassed",
        "以后将重分类进损益的其他综合收益",
        "OCI reclassified to profit or loss",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.oci_fx_translation",
        "外币财务报表折算差额",
        "Foreign currency translation differences (OCI)",
        common_in=("bank",),
    ),
    SubjectSpec(
        "is.perpetual_bond_interest",
        "应付永续债利息",
        "Interest on perpetual bonds",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.other_debt_investments_fv_change",
        "其他债权投资公允价值变动",
        "Fair value changes on other debt investments",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.other_debt_investments_credit_impairment",
        "其他债权投资信用减值准备",
        "Credit impairment on other debt investments",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.other_equity_instruments_fv_change",
        "其他权益工具投资公允价值变动",
        "Fair value changes on other equity instruments",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.amortized_cost_fin_assets_gain",
        "以摊余成本计量的金融资产终止确认产生的收益",
        "Gain on derecognition of amortized cost financial assets",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.other_asset_impairment_loss",
        "其他资产减值损失",
        "Other asset impairment loss",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.minority_equity_change",
        "少数股东权益",
        "Changes in minority interests",
        common_in=("bank",),
        common=False,
    ),
    SubjectSpec(
        "is.reclassification_from_equity_method",
        "权益法下重分类进损益的其他综合收益",
        "OCI reclassified under equity method",
        common_in=("bank",),
        common=False,
    ),

    # -------------------- Balance Sheet (BS) --------------------
    SubjectSpec("bs.section.core_metrics", "报表核心指标", "Core metrics"),
    SubjectSpec("bs.section.current_assets", "流动资产", "Current assets"),
    SubjectSpec("bs.section.non_current_assets", "非流动资产", "Non-current assets"),
    SubjectSpec("bs.section.current_liabilities", "流动负债", "Current liabilities"),
    SubjectSpec("bs.section.non_current_liabilities", "非流动负债", "Non-current liabilities"),
    SubjectSpec(
        "bs.section.equity",
        "股东权益",
        "Shareholders' equity",
        aliases=("所有者权益", "所有者权益（或股东权益）"),
    ),

    SubjectSpec(
        "bs.cash",
        "货币资金",
        "Cash and cash equivalents",
        aliases=("现金",),
    ),

    # Bank-specific
    SubjectSpec(
        "bs.cash_and_deposits_with_central_bank",
        "现金及存放中央银行款项",
        "Cash and deposits with central bank",
        aliases=("存放中央银行款",),
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.deposits_with_other_banks",
        "存放同业款项",
        "Deposits with other banks",
        common_in=("bank",),
        aliases=("存放同业",),
    ),
    SubjectSpec(
        "bs.lent_funds",
        "拆出资金",
        "Lent funds",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.fin_assets_purchased_for_resale",
        "买入返售金融资产",
        "Financial assets purchased for resale",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.loans_and_advances",
        "发放贷款及垫款",
        "Loans and advances",
        common_in=("bank",),
        aliases=("发放贷款和垫款",),
    ),
    SubjectSpec(
        "bs.loans_and_advances_net",
        "发放贷款及垫款净额",
        "Loans and advances (net)",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.loan_loss_reserve",
        "贷款损失准备",
        "Allowance for loan losses",
        common=False,
        note="非通用科目：部分银行会单列贷款损失准备，口径不一。",
    ),
    SubjectSpec(
        "bs.fixed_asset_impairment_provision",
        "固定资产减值准备",
        "Allowance for impairment of fixed assets",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.debt_investments",
        "债权投资",
        "Debt investments",
        common_in=("bank", "insurance"),
    ),
    SubjectSpec(
        "bs.other_debt_investments",
        "其他债权投资",
        "Other debt investments",
        common_in=("bank", "insurance"),
    ),

    # Fixed-asset breakdown (some providers)
    SubjectSpec(
        "bs.fixed_assets_gross",
        "固定资产原值",
        "Fixed assets (gross)",
        common=False,
        note="非通用科目：部分数据源将固定资产拆分为原值/折旧/净值。",
    ),
    SubjectSpec(
        "bs.accumulated_depreciation",
        "累计折旧",
        "Accumulated depreciation",
        common=False,
        note="非通用科目：部分数据源将固定资产拆分为原值/折旧/净值。",
    ),
    SubjectSpec(
        "bs.fixed_assets_net_value",
        "固定资产净值",
        "Fixed assets (net value)",
        common=False,
        note="非通用科目：部分数据源将固定资产拆分为原值/折旧/净值。",
    ),
    SubjectSpec(
        "bs.fixed_assets_net_amount",
        "固定资产净额",
        "Fixed assets (net)",
        common=False,
        note="非通用科目：部分数据源将固定资产拆分为原值/折旧/净值。",
    ),
    SubjectSpec(
        "bs.right_of_use_assets",
        "使用权资产",
        "Right-of-use assets",
        common=False,
        note="非通用科目：新租赁准则下可能披露，部分公司不单列。",
    ),
    SubjectSpec(
        "bs.lease_liabilities",
        "租赁负债",
        "Lease liabilities",
        common=False,
        note="非通用科目：新租赁准则下可能披露，部分公司不单列。",
    ),
    SubjectSpec(
        "bs.perpetual_bonds",
        "永续债",
        "Perpetual bonds",
        aliases=("应付债券：永续债",),
        common=False,
        note="非通用科目：存在永续债融资时出现，分类口径可能为负债或权益。",
    ),
    SubjectSpec(
        "bs.long_term_receivables",
        "长期应收款",
        "Long-term receivables",
        common=False,
    ),

    SubjectSpec(
        "bs.htm_investments",
        "持有至到期投资",
        "Held-to-maturity investments",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.investments_receivable",
        "应收款项类投资",
        "Receivable investments",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.precious_metals",
        "贵金属",
        "Precious metals",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.other_assets",
        "其他资产",
        "Other assets",
        common_in=("bank",),
    ),

    SubjectSpec("bs.total_cash", "总现金", "Total cash"),
    SubjectSpec("bs.trading_fin_assets", "交易性金融资产", "Trading financial assets"),
    SubjectSpec(
        "bs.derivative_fin_assets",
        "衍生金融资产",
        "Derivative financial assets",
        aliases=("衍生金融工具资产",),
        common=False,
        note="非通用科目：衍生工具相关资产，通常仅部分公司披露。",
    ),
    SubjectSpec(
        "bs.derivative_fin_liabilities",
        "衍生金融负债",
        "Derivative financial liabilities",
        aliases=("衍生金融工具负债",),
        common=False,
        note="非通用科目：衍生工具相关负债，通常仅部分公司披露。",
    ),
    SubjectSpec(
        "bs.afs_fin_assets",
        "可供出售金融资产",
        "Available-for-sale financial assets",
        aliases=("可供出售金融资产合计",),
        common=False,
        note="非通用科目：多与旧准则/特定披露口径相关，部分公司可能不再单列。",
    ),
    SubjectSpec(
        "bs.fin_assets_amortized_cost",
        "以摊余成本计量的金融资产",
        "Financial assets measured at amortized cost",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.fin_assets_fvoci",
        "以公允价值计量且其变动计入其他综合收益的金融资产",
        "Financial assets at fair value through OCI",
        common_in=("bank",),
    ),
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
    SubjectSpec(
        "bs.biological_assets",
        "生物资产",
        "Biological assets",
        common=False,
        note="非通用科目：农业/畜牧等行业常见；其他行业通常不披露。",
    ),
    SubjectSpec("bs.contract_assets", "合同资产", "Contract assets"),

    SubjectSpec("bs.interest_receivable", "应收利息", "Interest receivable"),
    SubjectSpec("bs.fixed_assets", "固定资产", "Fixed assets", aliases=("固定资产合计", "其中：固定资产")),
    SubjectSpec(
        "bs.construction_in_progress",
        "在建工程",
        "Construction in progress",
        aliases=("在建工程合计", "其中：在建工程"),
    ),
    SubjectSpec("bs.engineering_materials", "工程物资", "Engineering materials"),
    SubjectSpec("bs.investment_property", "投资性房地产", "Investment property"),
    SubjectSpec("bs.fixed_assets_disposal", "固定资产清理", "Disposal of fixed assets"),
    SubjectSpec("bs.goodwill", "商誉", "Goodwill"),
    SubjectSpec("bs.intangible_assets", "无形资产", "Intangible assets"),
    SubjectSpec("bs.long_term_deferred_expenses", "长期待摊费用", "Long-term deferred expenses"),
    SubjectSpec("bs.long_term_equity_investment", "长期股权投资", "Long-term equity investment"),
    SubjectSpec(
        "bs.deferred_tax_assets",
        "递延所得税资产",
        "Deferred tax assets",
        aliases=("递延税款借项",),
    ),
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

    # Bank-specific liabilities
    SubjectSpec(
        "bs.borrowings_from_central_bank",
        "向中央银行借款",
        "Borrowings from central bank",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.deposits_from_other_banks",
        "同业及其他金融机构存放款项",
        "Deposits from other banks and financial institutions",
        common_in=("bank",),
        aliases=("同业存放款项", "同业存放"),
    ),
    SubjectSpec(
        "bs.borrowed_funds",
        "拆入资金",
        "Borrowed funds",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.fin_assets_sold_for_repurchase",
        "卖出回购金融资产款",
        "Financial assets sold for repurchase",
        common_in=("bank",),
        aliases=("卖出回购金融资产款项",),
    ),
    SubjectSpec(
        "bs.customer_deposits",
        "吸收存款",
        "Customer deposits",
        common_in=("bank",),
        aliases=(
            "吸收存款及同业存放",
            "吸收存款及同业存放款项",
            "客户存款(吸收存款)",
        ),
    ),
    SubjectSpec(
        "bs.interbank_deposits_and_borrowings",
        "同业存入及拆入",
        "Interbank deposits and borrowings",
        common=False,
        note="非通用科目：部分数据源将同业存放与拆入资金合并披露。",
    ),
    SubjectSpec(
        "bs.trading_fin_liabilities",
        "交易性金融负债",
        "Trading financial liabilities",
        common=False,
        note="非通用科目：主要见于金融机构或金融工具披露较完整的公司。",
    ),
    SubjectSpec(
        "bs.other_liabilities",
        "其他负债",
        "Other liabilities",
        common_in=("bank",),
    ),

    SubjectSpec("bs.short_term_borrowings", "短期借款", "Short-term borrowings"),
    SubjectSpec(
        "bs.fin_liabilities_fvpl",
        "以公允价值计量且其变动计入当期损益的金融负债",
        "Financial liabilities at fair value through profit or loss",
        aliases=(
            "公允价值计量且其变动计入当期损益的金融负债",
            "以公允价值计量且其变动计入当期损益的金融负债合计",
        ),
        common=False,
        note="非通用科目：主要见于金融工具披露较完整的公司/行业；口径以财报附注为准。",
    ),
    SubjectSpec("bs.notes_payable", "应付票据", "Notes payable", aliases=("其中：应付票据",)),
    SubjectSpec("bs.accounts_payable", "应付账款", "Accounts payable"),
    SubjectSpec(
        "bs.notes_and_accounts_payable",
        "应付票据及应付账款",
        "Notes and accounts payable",
    ),
    SubjectSpec("bs.interest_payable", "应付利息", "Interest payable", aliases=("其中：应付利息",)),
    SubjectSpec("bs.dividends_payable", "应付股利", "Dividends payable"),
    SubjectSpec(
        "bs.advance_receipts",
        "预收款项",
        "Advance receipts",
        aliases=("预收账款", "预收款", "预收款项"),
    ),
    SubjectSpec(
        "bs.contract_liabilities",
        "合同负债",
        "Contract liabilities",
    ),
    SubjectSpec("bs.payroll_payable", "应付职工薪酬", "Employee benefits payable"),
    SubjectSpec(
        "bs.taxes_payable",
        "应交税费",
        "Taxes payable",
        aliases=("应交税金",),
    ),
    SubjectSpec("bs.other_payables", "其他应付款", "Other payables", aliases=("其他应付款合计",)), 
    SubjectSpec("bs.special_payables", "专项应付款", "Special payables"),
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
        "bs.deferred_income",
        "递延收益",
        "Deferred income",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.deferred_income_non_current",
        "递延收益-非流动负债",
        "Deferred income (non-current liabilities)",
    ),
    SubjectSpec("bs.other_non_current_liabilities", "其他非流动负债", "Other non-current liabilities"),
    SubjectSpec("bs.provisions", "预计负债", "Provisions"),
    SubjectSpec(
        "bs.deferred_tax_liabilities",
        "递延所得税负债",
        "Deferred tax liabilities",
        aliases=("递延税款贷项",),
    ),
    SubjectSpec("bs.total_non_current_liabilities", "非流动负债合计", "Total non-current liabilities"),
    SubjectSpec("bs.total_liabilities", "负债合计", "Total liabilities"),

    SubjectSpec(
        "bs.share_capital",
        "实收资本（或股本）",
        "Share capital",
        aliases=("实收资本(或股本)", "股本", "实收资本净额"),
    ),
    SubjectSpec("bs.capital_reserve", "资本公积", "Capital reserve"),
    SubjectSpec("bs.surplus_reserve", "盈余公积", "Surplus reserve"),

    # Bank/insurance may disclose these equity items explicitly
    SubjectSpec(
        "bs.general_risk_reserve",
        "一般风险准备",
        "General risk reserve",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.other_equity_instruments",
        "其他权益工具",
        "Other equity instruments",
        common_in=("bank",),
    ),
    SubjectSpec(
        "bs.preferred_shares",
        "优先股",
        "Preferred shares",
        common_in=("bank", "insurance"),
    ),
    SubjectSpec(
        "bs.preferred_bonds_payable",
        "应付债券：优先股",
        "Preferred bonds payable",
        common_in=("bank",),
        note="非通用科目：主要在存在优先股/永续债融资的金融机构里单列。",
    ),

    SubjectSpec("bs.retained_earnings", "未分配利润", "Retained earnings"),
    SubjectSpec("bs.other_comprehensive_income", "其他综合收益", "Other comprehensive income"),
    SubjectSpec(
        "bs.fx_translation_difference",
        "外币报表折算差额",
        "Foreign currency translation differences",
        aliases=("外币报表折算差额(合计)",),
    ),
    SubjectSpec("bs.treasury_stock", "库存股", "Treasury stock"),
    SubjectSpec(
        "bs.total_equity_parent",
        "归属于母公司所有者权益合计",
        "Total equity attributable to parent",
        aliases=("归属于母公司股东的权益",),
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
            "负债及股东权益总计",
            "负债及股东权益合计",
        ),
    ),

    # -------------------- Securities / Insurance special BS items --------------------
    SubjectSpec(
        "bs.settlement_reserve",
        "结算备付金",
        "Settlement reserve",
        common_in=("securities", "insurance"),
    ),
    SubjectSpec(
        "bs.customer_reserve",
        "客户备付金",
        "Customer reserve",
        common_in=("securities",),
    ),
    SubjectSpec(
        "bs.margin_deposits_paid",
        "存出保证金",
        "Margin deposits paid",
        common_in=("securities",),
    ),
    SubjectSpec(
        "bs.financing_funds",
        "融出资金",
        "Financing funds",
        common_in=("securities",),
    ),
    SubjectSpec(
        "bs.securities_receivables",
        "应收款项",
        "Securities receivables",
        common_in=("securities",),
        common=False,
        note="非通用科目：部分券商会以‘应收款项’汇总披露，经常需要与应收账款/其他应收款区分。",
    ),
    SubjectSpec(
        "bs.short_term_financing_payables",
        "应付短期融资款",
        "Short-term financing payables",
        common_in=("securities",),
    ),
    SubjectSpec(
        "bs.agency_trading_payables",
        "代理买卖证券款",
        "Agency trading payables",
        common_in=("securities",),
        aliases=("代理买卖证券款项",),
    ),
    SubjectSpec(
        "bs.agency_underwriting_payables",
        "代理承销证券款",
        "Agency underwriting payables",
        common_in=("securities",),
        aliases=("代理承销证券款项",),
    ),
    SubjectSpec(
        "bs.trading_risk_reserve",
        "交易风险准备",
        "Trading risk reserve",
        common_in=("securities",),
        common=False,
        note="非通用科目：仅部分券商披露。",
    ),
    SubjectSpec(
        "bs.broker_commission_payable",
        "应付经纪人佣金",
        "Broker commission payable",
        common_in=("securities",),
        common=False,
    ),
    SubjectSpec(
        "bs.trading_seat_fees",
        "交易席位费",
        "Trading seat fees",
        common_in=("securities",),
        common=False,
    ),

    # Insurance
    SubjectSpec(
        "bs.premiums_receivable",
        "应收保费",
        "Premiums receivable",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.reinsurance_receivables",
        "应收分保账款",
        "Reinsurance receivables",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.reinsurance_unearned_premium_reserve_receivable",
        "应收分保未到期责任准备金",
        "Reinsurance unearned premium reserve receivable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.reinsurance_policy_reserve_receivable",
        "应收分保合同准备金",
        "Reinsurance policy reserve receivable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.reinsurance_outstanding_claims_reserve_receivable",
        "应收分保未决赔款准备金",
        "Reinsurance outstanding claims reserve receivable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.reinsurance_life_insurance_reserve_receivable",
        "应收分保寿险责任准备金",
        "Reinsurance life insurance reserve receivable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.reinsurance_long_term_health_insurance_reserve_receivable",
        "应收分保长期健康险责任准备金",
        "Reinsurance long-term health insurance reserve receivable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.policyholder_pledged_loans",
        "保户质押贷款",
        "Policyholder pledged loans",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.time_deposits",
        "定期存款",
        "Time deposits",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.capital_guarantee_deposits",
        "存出资本保证金",
        "Capital guarantee deposits",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.advance_premiums",
        "预收保费",
        "Advance premiums",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.reinsurance_payables",
        "应付分保账款",
        "Reinsurance payables",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "bs.claims_payable",
        "应付赔付款",
        "Claims payable",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "bs.policyholder_deposits_and_investment",
        "保户储金及投资款",
        "Policyholder deposits and investment",
        common_in=("insurance",),
        common=False,
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
        "cf.cash_equivalents_begin",
        "现金等价物的期初余额",
        "Cash equivalents at beginning of period",
    ),
    SubjectSpec(
        "cf.cash_equivalents_end",
        "现金等价物的期末余额",
        "Cash equivalents at end of period",
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
        aliases=("处置固定资产、无形资产及其他资产而收到的现金",),
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
        "cf.cash_received_other_inv",
        "收到其他与投资活动有关的现金",
        "Other cash received relating to investing activities",
    ),
    SubjectSpec(
        "cf.cash_received_from_disposal_of_subsidiaries",
        "处置子公司及其他营业单位收到的现金净额",
        "Net cash received from disposal of subsidiaries and other business units",
    ),
    SubjectSpec(
        "cf.net_cash_paid_to_acquire_subsidiaries",
        "取得子公司及其他营业单位支付的现金净额",
        "Net cash paid to acquire subsidiaries and other business units",
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
        aliases=("拆入资金现金流入",),
    ),
    SubjectSpec(
        "cf.cash_received_from_bond_issuance",
        "发行债券收到的现金",
        "Cash received from bond issuance",
        aliases=("发行债券收到现金",),
        common=False,
        note="非通用科目：仅在公司存在发债融资时出现。",
    ),
    SubjectSpec(
        "cf.cash_received_from_investments",
        "吸收投资收到的现金",
        "Cash received from investments",
        aliases=("吸收投资所收到的现金",),
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
        aliases=("偿还债务所支付的现金",),
    ),
    SubjectSpec(
        "cf.cash_paid_for_dividends_interest",
        "分配股利、利润或偿付利息支付的现金",
        "Cash paid for dividends, profit distributions and interest",
        aliases=("偿付利息所支付的现金",),
    ),
    SubjectSpec(
        "cf.dividends_paid_to_minority_interests",
        "子公司支付给少数股东的股利、利润",
        "Dividends and profit paid by subsidiaries to minority interests",
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
        "cf.cashflow_hedging_reserve",
        "现金流量套期储备",
        "Cash flow hedging reserve",
        common=False,
        note="非通用科目：仅在进行现金流量套期时披露。",
    ),
    SubjectSpec(
        "cf.cashflow_hedging_effective",
        "现金流量套期损益的有效部分",
        "Effective portion of cash flow hedging gains/losses",
        common=False,
    ),
    SubjectSpec(
        "cf.remeasurement_of_defined_benefit_plan_changes",
        "重新计量设定受益计划变动额",
        "Remeasurement of defined benefit plan changes",
        common=False,
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
    SubjectSpec(
        "cf.trading_fin_assets_net_increase",
        "为交易目的而持有的金融资产净增加额",
        "Net increase in trading financial assets",
        common_in=("bank",),
    ),

    # Financial institutions special cashflow items (bank/securities/insurance)
    SubjectSpec(
        "cf.cash_received_interest_fees_commissions",
        "收取利息、手续费及佣金的现金",
        "Cash received from interest, fees and commissions",
        common_in=("bank", "securities", "insurance"),
    ),
    SubjectSpec(
        "cf.cash_paid_interest_fees_commissions",
        "支付利息、手续费及佣金的现金",
        "Cash paid for interest, fees and commissions",
        common_in=("bank", "securities", "insurance"),
    ),

    # Bank
    SubjectSpec(
        "cf.bank.net_increase_customer_deposits_and_interbank_deposits",
        "客户存款和同业存放款项净增加额",
        "Net increase in customer deposits and interbank deposits",
        aliases=("客户存款",),
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.net_increase_borrowings_from_central_bank",
        "向中央银行借款净增加额",
        "Net increase in borrowings from central bank",
        common_in=("bank",),
        aliases=("向央行借款净增加额",),
    ),
    SubjectSpec(
        "cf.bank.net_increase_borrowed_funds_from_financial_institutions",
        "向其他金融机构拆入资金净增加额",
        "Net increase in borrowed funds from other financial institutions",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.net_increase_loans_and_advances",
        "客户贷款及垫款净增加额",
        "Net increase in customer loans and advances",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.net_increase_deposits_with_central_bank_and_other_banks",
        "存放中央银行和同业款项净增加额",
        "Net increase in deposits with central bank and other banks",
        aliases=("存放中央银行",),
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_received_from_placements",
        "收回的拆出资金净额",
        "Net cash received from placements",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_paid_for_placements",
        "拆出资金净现金流出",
        "Net cash paid for placements",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.net_increase_repo_funds",
        "吸收的卖出回购项净额",
        "Net increase in sold repo funds",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_received_from_repo",
        "收回的买入返售项净额",
        "Net cash received from reverse repos",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_paid_for_repo",
        "支付买入返售款项净额",
        "Net cash paid for reverse repos",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_paid_to_repay_central_bank_borrowings",
        "偿还中央银行借款",
        "Cash paid to repay central bank borrowings",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_paid_to_repay_repo",
        "偿还卖出回购款项净额",
        "Cash paid to repay repo borrowings",
        common_in=("bank",),
    ),
    SubjectSpec(
        "cf.bank.cash_paid_to_repay_borrowed_funds",
        "偿还同业及其他金融机构拆入净额",
        "Cash paid to repay borrowed funds from other financial institutions",
        common_in=("bank",),
    ),

    # Securities
    SubjectSpec(
        "cf.securities.net_increase_trading_fin_assets_disposal",
        "处置交易性金融资产净增加额",
        "Net increase from disposal of trading financial assets",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_increase_borrowed_funds",
        "拆入资金净增加额",
        "Net increase in borrowed funds",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_increase_repo_funds",
        "回购业务资金净增加额",
        "Net increase in repo business funds",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_decrease_financing_funds",
        "融出资金净减少额",
        "Net decrease in financing funds",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_increase_financing_funds",
        "融出资金净增加额",
        "Net increase in financing funds",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_cash_received_from_agency_trading",
        "代理买卖证券收到的现金净额",
        "Net cash received from agency trading of securities",
        common_in=("securities",),
    ),
    SubjectSpec(
        "cf.securities.net_cash_paid_for_agency_trading",
        "代理买卖证券支付的现金净额",
        "Net cash paid for agency trading of securities",
        common_in=("securities",),
    ),

    # Insurance
    SubjectSpec(
        "cf.insurance.cash_received_from_premiums",
        "收到原保险合同保费取得的现金",
        "Cash received from premiums of original insurance contracts",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "cf.insurance.net_cash_received_from_reinsurance",
        "收到再保业务现金净额",
        "Net cash received from reinsurance business",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "cf.insurance.net_increase_policyholder_deposits_and_investment",
        "保户储金及投资款净增加额",
        "Net increase in policyholder deposits and investment",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "cf.insurance.cash_paid_claims",
        "支付原保险合同赔付款项的现金",
        "Cash paid for claims of original insurance contracts",
        common_in=("insurance",),
    ),
    SubjectSpec(
        "cf.insurance.cash_paid_policy_dividends",
        "支付保单红利的现金",
        "Cash paid for policy dividends",
        common_in=("insurance",),
        common=False,
    ),
    SubjectSpec(
        "cf.insurance.net_increase_pledged_loans",
        "质押贷款净增加额",
        "Net increase in pledged loans",
        common_in=("insurance",),
        common=False,
    ),

    # Rare CF supplement lines (uncommon)
    SubjectSpec(
        "cf.debt_converted_to_capital",
        "债务转为资本",
        "Debt converted to capital",
        common=False,
    ),
    SubjectSpec(
        "cf.convertible_bonds_due_within_one_year",
        "一年内到期的可转换公司债券",
        "Convertible bonds due within one year",
        common=False,
    ),
    SubjectSpec(
        "cf.finance_leasing_fixed_assets",
        "融资租入固定资产",
        "Fixed assets acquired under finance lease",
        common=False,
    ),
    SubjectSpec(
        "cf.decrease_in_prepaid_expenses",
        "待摊费用减少",
        "Decrease in prepaid expenses",
        common=False,
    ),
    SubjectSpec(
        "cf.increase_in_accrued_expenses",
        "预提费用增加",
        "Increase in accrued expenses",
        common=False,
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
