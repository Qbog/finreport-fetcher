from __future__ import annotations

import os
from datetime import date

import pandas as pd

from ..providers.base import StatementBundle
from ..raw_store import RawReportStore


class TushareProvider:
    """Tushare Pro 三大表。

    说明：
    - 需要 token（环境变量 TUSHARE_TOKEN 或运行时传入）
    - A 股三大表接口一般为 balancesheet / income / cashflow
    - comp_type：1 合并，2 母公司（若接口支持/字段一致）

    由于不同 tushare 版本/权限可能导致字段差异，这里实现为“尽力而为”，失败会抛异常供上层兜底。
    """

    name = "tushare"

    _RAW_TABLES = {
        "bs": "balancesheet",
        "is": "income",
        "cf": "cashflow",
    }

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

    def _load_raw_tables(self, raw_store: RawReportStore) -> dict[str, pd.DataFrame] | None:
        tables: dict[str, pd.DataFrame] = {}
        for key in self._RAW_TABLES:
            df = raw_store.load_provider_table(self.name, key)
            if df is None or df.empty:
                return None
            tables[key] = df
        return tables

    def _find_cached_row(
        self,
        df: pd.DataFrame,
        ts_code: str,
        period_end: date,
        statement_type: str,
    ) -> pd.Series | None:
        if df is None or df.empty:
            return None
        if "end_date" not in df.columns or "comp_type" not in df.columns:
            return None

        key = period_end.strftime("%Y%m%d")
        comp_type = str(self._comp_type(statement_type))

        df2 = df.copy()
        df2["__end_norm"] = df2["end_date"].astype(str).str.replace(r"[^0-9]", "", regex=True)
        df2["__comp_norm"] = df2["comp_type"].astype(str).str.replace(r"[^0-9]", "", regex=True)

        mask = (
            (df2["ts_code"].astype(str) == ts_code)
            & (df2["__end_norm"] == key)
            & (df2["__comp_norm"] == comp_type)
        )
        matched = df2[mask]
        if matched.empty:
            return None
        return matched.iloc[0]

    def _build_bundle_from_raw(
        self,
        ts_code: str,
        period_end: date,
        statement_type: str,
        tables: dict[str, pd.DataFrame],
    ) -> StatementBundle | None:
        bs_row = self._find_cached_row(tables.get("bs"), ts_code, period_end, statement_type)
        inc_row = self._find_cached_row(tables.get("is"), ts_code, period_end, statement_type)
        cf_row = self._find_cached_row(tables.get("cf"), ts_code, period_end, statement_type)
        if any(row is None for row in (bs_row, inc_row, cf_row)):
            return None

        bs_items = self._to_items(pd.DataFrame([bs_row]), period_end)
        inc_items = self._to_items(pd.DataFrame([inc_row]), period_end)
        cf_items = self._to_items(pd.DataFrame([cf_row]), period_end)

        meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "comp_type": self._comp_type(statement_type),
        }

        return StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=bs_items,
            income_statement=inc_items,
            cashflow_statement=cf_items,
            meta=meta,
            raw_data={"bs": pd.DataFrame([bs_row]), "is": pd.DataFrame([inc_row]), "cf": pd.DataFrame([cf_row])},
        )

    def _persist_raw_tables(
        self,
        raw_store: RawReportStore,
        bs_df: pd.DataFrame,
        inc_df: pd.DataFrame,
        cf_df: pd.DataFrame,
    ) -> None:
        subset = ["ts_code", "end_date", "comp_type"]
        raw_store.update_provider_table(self.name, "bs", bs_df, subset=subset)
        raw_store.update_provider_table(self.name, "is", inc_df, subset=subset)
        raw_store.update_provider_table(self.name, "cf", cf_df, subset=subset)

    def _fetch_full_history_tables(self, ts_code: str, statement_type: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Fetch one company's full raw history (listing -> current) from Tushare.

        这里刻意不传 end_date：用户要求 raw 缓存里保存整家公司完整历史，而不是单一期末切片。
        单公司三大表的全量返回通常体量可控，后续再从缓存中按期抽取。
        """

        pro = self._pro()
        comp_type = self._comp_type(statement_type)

        bs = pro.balancesheet(ts_code=ts_code, comp_type=comp_type)
        inc = pro.income(ts_code=ts_code, comp_type=comp_type)
        cf = pro.cashflow(ts_code=ts_code, comp_type=comp_type)

        if bs is None or inc is None or cf is None:
            raise RuntimeError("tushare 返回 None")

        return pd.DataFrame(bs), pd.DataFrame(inc), pd.DataFrame(cf)

    def get_bundle(
        self,
        ts_code: str,
        period_end: date,
        statement_type: str,
        raw_store: RawReportStore | None = None,
    ) -> StatementBundle:
        if raw_store:
            tables = self._load_raw_tables(raw_store)
            if tables:
                cached = self._build_bundle_from_raw(
                    ts_code=ts_code,
                    period_end=period_end,
                    statement_type=statement_type,
                    tables=tables,
                )
                if cached:
                    cached.meta["raw_scope"] = "full_history"
                    return cached

            # raw 缓存缺失/不完整时，拉取整家公司全历史宽表后再回填缓存。
            bs_df, inc_df, cf_df = self._fetch_full_history_tables(ts_code, statement_type)
            self._persist_raw_tables(raw_store, bs_df, inc_df, cf_df)

            tables = self._load_raw_tables(raw_store)
            if tables:
                cached = self._build_bundle_from_raw(
                    ts_code=ts_code,
                    period_end=period_end,
                    statement_type=statement_type,
                    tables=tables,
                )
                if cached:
                    cached.meta["raw_scope"] = "full_history"
                    return cached

            raise RuntimeError(f"tushare 全历史原始表中未找到报告期 {period_end.strftime('%Y-%m-%d')}")

        # 未启用 raw_store 时，保持旧逻辑：按单个报告期请求，减少无关数据。
        pro = self._pro()
        end_date = self._period(period_end)
        comp_type = self._comp_type(statement_type)

        # 有些账号权限/接口会失败，交给上层兜底
        bs = pro.balancesheet(ts_code=ts_code, end_date=end_date, comp_type=comp_type)
        inc = pro.income(ts_code=ts_code, end_date=end_date, comp_type=comp_type)
        cf = pro.cashflow(ts_code=ts_code, end_date=end_date, comp_type=comp_type)

        if bs is None or inc is None or cf is None:
            raise RuntimeError("tushare 返回 None")

        bs_df = pd.DataFrame(bs)
        inc_df = pd.DataFrame(inc)
        cf_df = pd.DataFrame(cf)

        bs_items = self._to_items(bs_df, period_end)
        inc_items = self._to_items(inc_df, period_end)
        cf_items = self._to_items(cf_df, period_end)

        if bs_items.empty or inc_items.empty or cf_items.empty:
            raise RuntimeError("tushare 获取到的三大表存在空表")

        meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "comp_type": comp_type,
            "raw_scope": "single_period",
        }

        bundle = StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=bs_items,
            income_statement=inc_items,
            cashflow_statement=cf_items,
            meta=meta,
            raw_data={"bs": bs_df, "is": inc_df, "cf": cf_df},
        )

        return bundle
