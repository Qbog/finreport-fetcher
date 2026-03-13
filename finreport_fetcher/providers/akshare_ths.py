from __future__ import annotations

import re
from datetime import date

import pandas as pd

from ..providers.base import StatementBundle


class AkshareThsProvider:
    """Akshare + 同花顺(10jqka) 财报三大表。

    使用 akshare 的以下接口：
    - stock_financial_debt_ths    (资产负债表)
    - stock_financial_benefit_ths (利润表)
    - stock_financial_cash_ths    (现金流量表)

    相比 Sina 接口，该来源通常更稳定（且不依赖 Tushare token）。

    注意：该来源返回的数值经常带单位后缀（如 1.23亿 / 456万 / 12.3%），
    这里会尽力解析为 float。
    """

    name = "akshare_ths"

    def supports(self) -> bool:
        try:
            import akshare  # noqa: F401

            return True
        except Exception:
            return False

    @staticmethod
    def _to_code6(ts_code: str) -> str:
        return ts_code.split(".")[0]

    @staticmethod
    def _parse_num(v) -> float | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            try:
                if pd.isna(v):
                    return None
            except Exception:
                pass
            return float(v)

        s = str(v).strip()
        if not s or s in {"--", "-", "nan", "None"}:
            return None

        # remove commas and spaces
        s = s.replace(",", "").replace(" ", "")

        # common unit suffixes
        # examples: 2657.05亿, 123.4万, 1.2%, 3.4元, 2.1亿股
        m = re.match(r"^(-?\d+(?:\.\d+)?)(.*)$", s)
        if not m:
            return None

        num = float(m.group(1))
        unit = (m.group(2) or "").strip()

        # percent
        if unit == "%":
            # keep '12.3%' as 12.3 (not 0.123)
            return num

        # share/unit variants
        if unit in {"亿", "亿元"}:
            return num * 1e8
        if unit in {"万", "万元"}:
            return num * 1e4
        if unit in {"元", ""}:
            return num

        # shares
        if unit in {"万股"}:
            return num * 1e4
        if unit in {"亿股"}:
            return num * 1e8

        # fallback: try parse numeric prefix
        return num

    @staticmethod
    def _row_to_items(df: pd.DataFrame, *, period_end: date, sheet_cn: str) -> tuple[pd.DataFrame, dict]:
        if df is None or df.empty:
            raise ValueError(f"空数据: {sheet_cn}")

        # THS uses YYYY-MM-DD
        key = period_end.strftime("%Y-%m-%d")
        if "报告期" not in df.columns:
            raise ValueError(f"缺少报告期列: {sheet_cn}")

        dfx = df.copy()
        dfx["报告期"] = dfx["报告期"].astype(str)
        sub = dfx[dfx["报告期"] == key]
        if sub.empty:
            raise ValueError(f"未找到报告期 {key} 的数据: {sheet_cn}")

        row = sub.iloc[0]

        # meta: keep a few known columns if present
        meta = {"report_date": key, "source": "10jqka"}

        drop_cols = {"报告期", "报表核心指标", "报表全部指标"}

        def is_section_header(name: str) -> bool:
            header_exact = {
                # BS
                "流动资产",
                "非流动资产",
                "流动负债",
                "非流动负债",
                "所有者权益",
                "股东权益",
                # CF
                "经营活动产生的现金流量",
                "投资活动产生的现金流量",
                "筹资活动产生的现金流量",
                "补充资料",
            }
            if name in header_exact:
                return True
            # IS headers like: 一、二、三…
            if sheet_cn == "利润表" and re.match(r"^[一二三四五六七八九十]、", name):
                return True
            # nested headers like: （一）（二）…
            if sheet_cn == "利润表" and re.match(r"^（[一二三四五六七八九十]）", name):
                return True
            return False

        items: list[tuple[str, float | None, int, bool]] = []
        in_section = False

        for col in dfx.columns:
            if col in drop_cols:
                continue
            name = str(col).strip()
            if not name:
                continue

            # clean leading markers
            name_clean = name.lstrip("*").strip()

            val = row.get(col)
            num = AkshareThsProvider._parse_num(val)

            # section header
            if is_section_header(name_clean):
                items.append((name_clean, float(num) if num is not None else None, 0, True))
                in_section = True
                continue

            # keep only non-empty normal items
            if num is None:
                continue

            level = 1 if in_section else 0
            if name_clean.startswith(("其中", "其中：", "加：", "减：")):
                level = max(level, 2)

            items.append((name_clean, float(num), level, False))

        out = pd.DataFrame(items, columns=["科目", "数值", "__level", "__is_header"])
        return out, meta

    def get_bundle(self, ts_code: str, period_end: date, statement_type: str) -> StatementBundle:
        import akshare as ak

        code6 = self._to_code6(ts_code)

        # 按报告期：通常为累计(YTD)口径，更适配我们后续的 TTM/单季差分转换
        bs_raw = ak.stock_financial_debt_ths(symbol=code6, indicator="按报告期")
        is_raw = ak.stock_financial_benefit_ths(symbol=code6, indicator="按报告期")
        cf_raw = ak.stock_financial_cash_ths(symbol=code6, indicator="按报告期")

        bs, meta_bs = self._row_to_items(bs_raw, period_end=period_end, sheet_cn="资产负债表")
        inc, meta_inc = self._row_to_items(is_raw, period_end=period_end, sheet_cn="利润表")
        cf, meta_cf = self._row_to_items(cf_raw, period_end=period_end, sheet_cn="现金流量表")

        meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "statement_type_requested": statement_type,
            "note": "THS 数据源通常不区分合并/母公司口径，实际口径以来源为准",
            "meta_balance": meta_bs,
            "meta_income": meta_inc,
            "meta_cashflow": meta_cf,
        }

        return StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=bs,
            income_statement=inc,
            cashflow_statement=cf,
            meta=meta,
        )
