from __future__ import annotations

import os
from datetime import date

import pandas as pd

from ..providers.base import StatementBundle


class TushareProvider:
    """Tushare Pro 三大表。

    说明：
    - 需要 token（环境变量 TUSHARE_TOKEN 或运行时传入）
    - A 股三大表接口一般为 balancesheet / income / cashflow
    - comp_type：1 合并，2 母公司（若接口支持/字段一致）

    由于不同 tushare 版本/权限可能导致字段差异，这里实现为“尽力而为”，失败会抛异常供上层兜底。
    """

    name = "tushare"

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TUSHARE_TOKEN")

    def supports(self) -> bool:
        try:
            import tushare  # noqa: F401

            return True
        except Exception:
            return False

    def _pro(self):
        import tushare as ts

        if not self.token:
            raise RuntimeError("未提供 Tushare token（可设置环境变量 TUSHARE_TOKEN 或传入 --tushare-token）")
        ts.set_token(self.token)
        return ts.pro_api()

    @staticmethod
    def _comp_type(statement_type: str) -> int:
        return 2 if statement_type == "parent" else 1

    @staticmethod
    def _period(period_end: date) -> str:
        return period_end.strftime("%Y%m%d")

    @staticmethod
    def _to_items(df: pd.DataFrame, period_end: date) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["报告期末日", "科目", "数值"])

        # tushare 返回列为字段名（英文），这里不做强行中文映射，直接输出“字段名=科目”
        row = df.iloc[0].to_dict()
        items = []
        for k, v in row.items():
            if k in ("ts_code", "ann_date", "f_ann_date", "end_date", "report_type", "comp_type", "update_flag"):
                continue
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            items.append((k, v))

        out = pd.DataFrame(items, columns=["科目", "数值"])
        out["__level"] = 0
        out["__is_header"] = False
        return out

    def get_bundle(self, ts_code: str, period_end: date, statement_type: str) -> StatementBundle:
        pro = self._pro()
        end_date = self._period(period_end)
        comp_type = self._comp_type(statement_type)

        # 有些账号权限/接口会失败，交给上层兜底
        bs = pro.balancesheet(ts_code=ts_code, end_date=end_date, comp_type=comp_type)
        inc = pro.income(ts_code=ts_code, end_date=end_date, comp_type=comp_type)
        cf = pro.cashflow(ts_code=ts_code, end_date=end_date, comp_type=comp_type)

        if bs is None or inc is None or cf is None:
            raise RuntimeError("tushare 返回 None")

        bs_items = self._to_items(pd.DataFrame(bs), period_end)
        inc_items = self._to_items(pd.DataFrame(inc), period_end)
        cf_items = self._to_items(pd.DataFrame(cf), period_end)

        if bs_items.empty or inc_items.empty or cf_items.empty:
            raise RuntimeError("tushare 获取到的三大表存在空表")

        meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "comp_type": comp_type,
        }

        return StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=bs_items,
            income_statement=inc_items,
            cashflow_statement=cf_items,
            meta=meta,
        )
