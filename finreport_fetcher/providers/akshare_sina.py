from __future__ import annotations

from datetime import date
import re

import pandas as pd

from ..providers.base import StatementBundle
from ..raw_store import RawReportStore


class AkshareSinaProvider:
    """使用 akshare.stock_financial_report_sina 抓取三大表。

    优点：无需 token，覆盖面广。
    注意：字段较多，且口径字段以“类型”列标注（常见：合并期末/母公司期末 等）。
    """

    name = "akshare"

    _RAW_TABLES = {
        "bs": "资产负债表",
        "is": "利润表",
        "cf": "现金流量表",
    }

    def __init__(self) -> None:
        # cache: (code6, table_cn) -> raw df (包含多期数据)
        # 同一轮 fetch 多个报告期时，避免重复拉取宽表。
        self._df_cache: dict[tuple[str, str], pd.DataFrame] = {}

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
        k = (code6, table_cn)
        cached = self._df_cache.get(k)
        if cached is not None:
            return cached

        import akshare as ak

        # symbol 参数叫 stock；table 叫 symbol（中文）
        df = ak.stock_financial_report_sina(stock=code6, symbol=table_cn)
        if not isinstance(df, pd.DataFrame) or df.empty:
            df = pd.DataFrame()

        self._df_cache[k] = df
        return df

    def _extract_period(
        self,
        df: pd.DataFrame,
        period_end: date,
        statement_type: str,
        statement_name: str,
    ) -> tuple[pd.DataFrame, dict]:
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

        def is_section_header(name: str) -> bool:
            # 经验规则：只把少量“确定是分组标题”的列当作标题；避免把大量缺失科目当成标题。
            header_exact = {
                "流动资产",
                "非流动资产",
                "流动负债",
                "非流动负债",
                "所有者权益",
                "股东权益",
                "经营活动产生的现金流量",
                "投资活动产生的现金流量",
                "筹资活动产生的现金流量",
                "补充资料",
            }
            if name in header_exact:
                return True
            # 利润表常见分段：一、二、三…（通常有数值，不一定为空）
            if re.match(r"^[一二三四五六七八九十]、", name):
                return True
            # 细分段： （一）（二）…
            if re.match(r"^（[一二三四五六七八九十]）", name):
                return True
            return False

        profit_sentinels = {
            "营业总收入": "收入",
            "营业总成本": "成本费用",
            "营业利润": "利润",
            "其他综合收益": "其他综合收益",
            "综合收益总额": "综合收益",
        }

        items = []
        in_section = False
        current_section = None

        def add_section(title: str):
            nonlocal in_section, current_section
            if current_section == title:
                return
            items.append((title, None, 0, True))
            in_section = True
            current_section = title

        for col in data_cols:
            if col in ("报告日",):
                continue
            name = str(col)
            val = row[col]

            # 利润表：按关键哨兵插入分类标题
            if statement_name == "利润表" and name in profit_sentinels:
                add_section(profit_sentinels[name])

            # 原始分段标题（如现金流量表/资产负债表分段）
            if is_section_header(name):
                if pd.isna(val):
                    items.append((name, None, 0, True))
                else:
                    items.append((name, val, 0, True))
                in_section = True
                current_section = name
                continue

            # 丢掉全空的普通科目
            if pd.isna(val):
                continue

            # 缩进规则
            level = 1 if in_section else 0
            if name.startswith(("其中", "其中：", "加：", "减：")):
                level = max(level, 2)

            items.append((name, val, level, False))

        out = pd.DataFrame(items, columns=["科目", "数值", "__level", "__is_header"])
        return out, meta

    def _load_raw_tables(self, raw_store: RawReportStore) -> dict[str, pd.DataFrame] | None:
        tables: dict[str, pd.DataFrame] = {}
        for key in self._RAW_TABLES:
            df = raw_store.load_provider_table(self.name, key)
            if df is None or df.empty:
                return None
            tables[key] = df
        return tables

    def _persist_raw_tables(self, raw_store: RawReportStore, code6: str, tables: dict[str, pd.DataFrame]) -> None:
        for key, df in tables.items():
            if df is None or df.empty:
                continue
            raw_store.save_provider_table(self.name, key, df)

    def refresh_raw_history(self, ts_code: str, statement_type: str, raw_store: RawReportStore) -> str:
        code6 = self._to_code6(ts_code)
        bs_raw = self._fetch_one(code6, "资产负债表")
        is_raw = self._fetch_one(code6, "利润表")
        cf_raw = self._fetch_one(code6, "现金流量表")
        return raw_store.save_provider_snapshot(
            self.name,
            {"bs": bs_raw, "is": is_raw, "cf": cf_raw},
            metadata={
                "scope": "full_history",
                "ts_code": ts_code,
                "statement_type": statement_type,
                "provider": self.name,
            },
        )

    def _build_bundle_from_raw(
        self,
        ts_code: str,
        code6: str,
        period_end: date,
        statement_type: str,
        tables: dict[str, pd.DataFrame],
    ) -> StatementBundle | None:
        try:
            bs, meta_bs = self._extract_period(tables["bs"], period_end, statement_type, "资产负债表")
            inc, meta_inc = self._extract_period(tables["is"], period_end, statement_type, "利润表")
            cf, meta_cf = self._extract_period(tables["cf"], period_end, statement_type, "现金流量表")
        except Exception:
            return None

        detected_type = None
        for meta in (meta_bs, meta_inc, meta_cf):
            t = meta.get("类型")
            if t:
                detected_type = str(t)
                break

        st = statement_type
        if detected_type and "母" in detected_type:
            st = "parent"
        elif detected_type and "合并" in detected_type:
            st = "merged"

        bundle_meta = {
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "requested_statement_type": statement_type,
            "detected_type": detected_type,
            "meta_balance": meta_bs,
            "meta_income": meta_inc,
            "meta_cashflow": meta_cf,
        }

        return StatementBundle(
            period_end=period_end,
            statement_type=st,
            provider=self.name,
            balance_sheet=bs,
            income_statement=inc,
            cashflow_statement=cf,
            meta=bundle_meta,
            raw_data=tables,
        )

    def get_bundle(
        self,
        ts_code: str,
        period_end: date,
        statement_type: str,
        raw_store: RawReportStore | None = None,
    ) -> StatementBundle:
        code6 = self._to_code6(ts_code)

        if raw_store:
            cached_tables = self._load_raw_tables(raw_store)
            if cached_tables:
                cached = self._build_bundle_from_raw(
                    ts_code=ts_code,
                    code6=code6,
                    period_end=period_end,
                    statement_type=statement_type,
                    tables=cached_tables,
                )
                if cached:
                    return cached
                meta = raw_store.load_provider_metadata(self.name) or {}
                if meta.get("scope") == "full_history":
                    raise RuntimeError(f"原始数据中没有 {period_end.strftime('%Y-%m-%d')} 日期的财报")

        bs_raw = self._fetch_one(code6, "资产负债表")
        is_raw = self._fetch_one(code6, "利润表")
        cf_raw = self._fetch_one(code6, "现金流量表")

        bs, meta_bs = self._extract_period(bs_raw, period_end, statement_type, "资产负债表")
        inc, meta_inc = self._extract_period(is_raw, period_end, statement_type, "利润表")
        cf, meta_cf = self._extract_period(cf_raw, period_end, statement_type, "现金流量表")

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

        bundle = StatementBundle(
            period_end=period_end,
            statement_type=st,
            provider=self.name,
            balance_sheet=bs,
            income_statement=inc,
            cashflow_statement=cf,
            meta=bundle_meta,
            raw_data={"bs": bs_raw, "is": is_raw, "cf": cf_raw},
        )

        if raw_store:
            raw_store.save_provider_snapshot(
                self.name,
                {"bs": bs_raw, "is": is_raw, "cf": cf_raw},
                metadata={
                    "scope": "full_history",
                    "ts_code": ts_code,
                    "statement_type": statement_type,
                    "provider": self.name,
                },
            )

        return bundle
