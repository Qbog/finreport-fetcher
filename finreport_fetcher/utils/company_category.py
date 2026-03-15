from __future__ import annotations

from dataclasses import dataclass


# 四类（按用户定义）
CATEGORY_NON_FINANCIAL = "non_financial"  # 非金融企业
CATEGORY_BANK = "bank"  # 银行
CATEGORY_SECURITIES = "securities"  # 证券
CATEGORY_INSURANCE = "insurance"  # 保险

ALL_CATEGORIES = (
    CATEGORY_NON_FINANCIAL,
    CATEGORY_BANK,
    CATEGORY_SECURITIES,
    CATEGORY_INSURANCE,
)


@dataclass(frozen=True)
class CompanyCategoryInfo:
    category: str
    industry: str | None = None
    source: str | None = None  # tushare|heuristic


def _category_from_industry(industry: str | None) -> str | None:
    ind = (industry or "").strip()
    if not ind:
        return None

    # tushare 常见行业：银行/证券/保险/多元金融/资本市场服务...
    if "银行" in ind:
        return CATEGORY_BANK
    if "保险" in ind:
        return CATEGORY_INSURANCE
    if "证券" in ind or "资本市场" in ind or "多元金融" in ind or "金融服务" in ind:
        return CATEGORY_SECURITIES
    return CATEGORY_NON_FINANCIAL


def detect_company_category(
    *,
    ts_code: str,
    name: str | None = None,
    tushare_token: str | None = None,
) -> CompanyCategoryInfo:
    """Detect company category.

    Priority:
    1) tushare stock_basic industry (if token provided)
    2) heuristic by name

    NOTE: token is NOT stored.
    """

    # 1) tushare
    token = (tushare_token or "").strip()
    if token:
        try:
            import tushare as ts

            pro = ts.pro_api(token)
            df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name,industry")
            if df is not None and not df.empty:
                industry = str(df.iloc[0].get("industry") or "").strip() or None
                cat = _category_from_industry(industry)
                if cat:
                    return CompanyCategoryInfo(category=cat, industry=industry, source="tushare")
        except Exception:
            pass

    # 2) heuristic fallback
    code6 = (ts_code or "").split(".")[0].strip()

    # 少量金融行业公司简称不含“银行/证券/保险”，用 code 白名单兜底。
    # 说明：A 股保险公司数量很少，维护成本低；同时能显著提升分类准确性。
    if code6 in {"601318", "601628", "601336", "601601", "601319"}:
        return CompanyCategoryInfo(category=CATEGORY_INSURANCE, industry=None, source="heuristic")

    nm = (name or "").strip()
    if "银行" in nm:
        return CompanyCategoryInfo(category=CATEGORY_BANK, industry=None, source="heuristic")
    if "证券" in nm:
        return CompanyCategoryInfo(category=CATEGORY_SECURITIES, industry=None, source="heuristic")
    if "保险" in nm:
        return CompanyCategoryInfo(category=CATEGORY_INSURANCE, industry=None, source="heuristic")

    return CompanyCategoryInfo(category=CATEGORY_NON_FINANCIAL, industry=None, source="heuristic")
