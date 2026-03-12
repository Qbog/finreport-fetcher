from __future__ import annotations

from datetime import date

import pandas as pd

from ..providers.base import StatementBundle


class AkshareSinaProvider:
    """使用 akshare.stock_financial_report_sina 抓取三大表。

    优点：无需 token，覆盖面广。
    注意：字段较多，且口径字段以“类型”列标注（常见：合并期末/母公司期末 等）。
    """

    name = "akshare"

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
    def _normalize_report_date(v) -> str:
        # Sina 返回 '报告日' 为 YYYYMMDD（int/str 混合）
        s = str(v).strip()
        if s.isdigit() and len(s) == 8:
            return s
        # 兜底：去掉 '-' '/'
        s2 = s.replace("-", "").replace("/", "")
        return s2

    @staticmethod
    def _pick_statement_type_mask(df: pd.DataFrame, statement_type: str) -> pd.Series:
        # statement_type: merged|parent
        if "类型" not in df.columns:
            return pd.Series([True] * len(df), index=df.index)

        typ = df["类型"].astype(str)
        if statement_type == "parent":
            return typ.str.contains("母", na=False)
        # merged default
        return typ.str.contains("合并", na=False)

    def _fetch_one(self, code6: str, table_cn: str) -> pd.DataFrame:
        import akshare as ak

        # symbol 参数叫 stock；table 叫 symbol（中文）
        df = ak.stock_financial_report_sina(stock=code6, symbol=table_cn)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        return df

    def _extract_period(self, df: pd.DataFrame, period_end: date, statement_type: str) -> tuple[pd.DataFrame, dict]:
        if df.empty:
            raise ValueError("空数据")

        period_key = period_end.strftime("%Y%m%d")

        df2 = df.copy()
        if "报告日" not in df2.columns:
            raise ValueError("缺少报告日字段")

        df2["__report_date"] = df2["报告日"].map(self._normalize_report_date)

        # 先按报告期末日过滤
        dfp = df2[df2["__report_date"] == period_key].copy()
        if dfp.empty:
            raise ValueError(f"未找到报告期 {period_key} 的数据")

        # 再按口径过滤（合并/母公司）。如果该口径不存在，则退化为“拿到能用的数据并说明”。
        meta_note = None
        if "类型" in dfp.columns and statement_type in {"merged", "parent"}:
            mask = self._pick_statement_type_mask(dfp, statement_type)
            dfp2 = dfp[mask].copy()
            if not dfp2.empty:
                dfp = dfp2
            else:
                meta_note = f"未找到请求口径({statement_type})对应的类型行，已回退为该报告期的可用数据（请在META查看类型字段）"

        # 同期多行时，优先取更新日期较新的一条
        if "更新日期" in dfp.columns:
            try:
                dfp = dfp.sort_values("更新日期", ascending=False)
            except Exception:
                pass

        # 按列展开为两列：科目/数值；保留少量 meta
        keep_meta_cols = [c for c in ["报告日", "公告日期", "是否审计", "币种", "类型", "数据源", "更新日期"] if c in dfp.columns]
        meta: dict = {}
        if keep_meta_cols:
            row0 = dfp.iloc[0]
            meta = {c: row0[c] for c in keep_meta_cols}
        if meta_note:
            meta["口径回退说明"] = meta_note

        # 取第一行作为该期数据
        row = dfp.iloc[0]
        data_cols = [c for c in dfp.columns if c not in set(keep_meta_cols + ["__report_date"]) ]

        items = []
        for col in data_cols:
            if col in ("报告日",):
                continue
            val = row[col]
            # 丢掉全空
            if pd.isna(val):
                continue
            items.append((col, val))

        out = pd.DataFrame(items, columns=["科目", "数值"])
        out.insert(0, "报告期末日", period_end.strftime("%Y-%m-%d"))
        return out, meta

    def get_bundle(self, ts_code: str, period_end: date, statement_type: str) -> StatementBundle:
        code6 = self._to_code6(ts_code)

        bs_raw = self._fetch_one(code6, "资产负债表")
        is_raw = self._fetch_one(code6, "利润表")
        cf_raw = self._fetch_one(code6, "现金流量表")

        bs, meta_bs = self._extract_period(bs_raw, period_end, statement_type)
        inc, meta_inc = self._extract_period(is_raw, period_end, statement_type)
        cf, meta_cf = self._extract_period(cf_raw, period_end, statement_type)

        # 口径说明
        detected_type = None
        for m in (meta_bs, meta_inc, meta_cf):
            t = m.get("类型")
            if t:
                detected_type = str(t)
                break

        bundle_meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "requested_statement_type": statement_type,
            "detected_type": detected_type,
            "meta_balance": meta_bs,
            "meta_income": meta_inc,
            "meta_cashflow": meta_cf,
        }

        # statement_type 标注
        st = statement_type
        if detected_type and "母" in detected_type:
            st = "parent"
        elif detected_type and "合并" in detected_type:
            st = "merged"

        return StatementBundle(
            period_end=period_end,
            statement_type=st,
            provider=self.name,
            balance_sheet=bs,
            income_statement=inc,
            cashflow_statement=cf,
            meta=bundle_meta,
        )
