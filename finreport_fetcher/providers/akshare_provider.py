from __future__ import annotations

from datetime import date

import pandas as pd

from finreport_fetcher.providers.base import StatementBundle


class AkshareSinaProvider:
    """使用 akshare.stock_financial_report_sina 拉取三大表。

    优点：无需 token，覆盖面广，并包含"类型"(合并/母公司) 和 "公告日期"。
    注意：字段为中文、列很多；这里尽量做结构化清洗与统一。
    """

    name = "akshare"

    def supports(self) -> bool:
        return True

    @staticmethod
    def _fetch(stock_code6: str, symbol_cn: str) -> pd.DataFrame:
        import akshare as ak

        df = ak.stock_financial_report_sina(stock=stock_code6, symbol=symbol_cn)
        # 报告日: YYYYMMDD (int/str)
        if "报告日" in df.columns:
            df["报告日"] = df["报告日"].astype(str)
        return df

    @staticmethod
    def _pick_row(df: pd.DataFrame, period_end: date, statement_type: str) -> pd.DataFrame:
        pe = period_end.strftime("%Y%m%d")
        if "报告日" not in df.columns:
            raise RuntimeError("数据缺少'报告日'字段，无法按报告期筛选")

        sub = df[df["报告日"].astype(str) == pe]
        if sub.empty:
            raise FileNotFoundError(f"未找到报告期 {pe} 的数据")

        # 类型字段示例："合并期末"、"母公司期末"；利润表/现金流量表也会有
        if "类型" in sub.columns and statement_type in {"merged", "parent"}:
            if statement_type == "merged":
                sub2 = sub[sub["类型"].astype(str).str.contains("合并", na=False)]
                if not sub2.empty:
                    sub = sub2
            elif statement_type == "parent":
                sub2 = sub[sub["类型"].astype(str).str.contains("母", na=False)]
                if not sub2.empty:
                    sub = sub2

        # 同一报告期可能返回多行（更新/更正），优先取更新日期最大
        if "更新日期" in sub.columns:
            try:
                sub = sub.sort_values("更新日期", ascending=False)
            except Exception:
                pass
        return sub.iloc[[0]].reset_index(drop=True)

    @staticmethod
    def _row_to_kv(row_df: pd.DataFrame) -> pd.DataFrame:
        # 将“宽表一行”转为两列：科目/数值，便于 Excel 直观阅读
        row = row_df.iloc[0]
        # 排除元信息列
        meta_cols = {
            "报告日",
            "数据源",
            "是否审计",
            "公告日期",
            "币种",
            "类型",
            "更新日期",
        }
        items = []
        for k, v in row.items():
            if k in meta_cols:
                continue
            items.append((k, v))
        out = pd.DataFrame(items, columns=["科目", "数值"])
        return out

    def get_bundle(self, ts_code: str, period_end: date, statement_type: str) -> StatementBundle:
        stock_code6 = ts_code.split(".")[0]

        bs_raw = self._fetch(stock_code6, "资产负债表")
        is_raw = self._fetch(stock_code6, "利润表")
        cf_raw = self._fetch(stock_code6, "现金流量表")

        bs_row = self._pick_row(bs_raw, period_end, statement_type)
        is_row = self._pick_row(is_raw, period_end, statement_type)
        cf_row = self._pick_row(cf_raw, period_end, statement_type)

        meta = {
            "报告日": period_end.strftime("%Y%m%d"),
            "类型": bs_row.get("类型", pd.Series([None])).iloc[0] if "类型" in bs_row.columns else None,
            "公告日期": bs_row.get("公告日期", pd.Series([None])).iloc[0] if "公告日期" in bs_row.columns else None,
            "更新日期": bs_row.get("更新日期", pd.Series([None])).iloc[0] if "更新日期" in bs_row.columns else None,
            "数据源": bs_row.get("数据源", pd.Series([None])).iloc[0] if "数据源" in bs_row.columns else None,
        }

        bundle = StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=self._row_to_kv(bs_row),
            income_statement=self._row_to_kv(is_row),
            cashflow_statement=self._row_to_kv(cf_row),
            meta=meta,
        )
        return bundle
