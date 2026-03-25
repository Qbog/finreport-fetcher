from __future__ import annotations

import re
from datetime import date

import pandas as pd

from ..providers.base import StatementBundle
from ..raw_store import RawReportStore


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

    _RAW_TABLES = {
        "bs": "资产负债表",
        "is": "利润表",
        "cf": "现金流量表",
    }

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

        def header_kind(name: str) -> tuple[bool, int]:
            """Return (is_header, next_item_level).

            next_item_level controls indentation for following normal items.
            """

            # exact section headers (mainly for BS)
            header_exact = {
                # BS
                "流动资产",
                "非流动资产",
                "流动负债",
                "非流动负债",
                "所有者权益",
                "股东权益",
            }
            if name in header_exact:
                return True, 1

            # IS headers like: 一、二、三…
            if sheet_cn == "利润表" and re.match(r"^[一二三四五六七八九十]、", name):
                return True, 1
            # nested headers like: （一）（二）…
            if sheet_cn == "利润表" and re.match(r"^（[一二三四五六七八九十]）", name):
                return True, 2

            # CF headers
            if sheet_cn == "现金流量表":
                # top sections: 一、二、三、四、五、六…
                if re.match(r"^[一二三四五六七八九十]、", name):
                    return True, 1
                # supplement sections like: 补充资料：
                if name.startswith("补充资料"):
                    return True, 1
                # numbered sub-sections: 1、2、3、... （通常以冒号结尾）
                if re.match(r"^[0-9]+、", name):
                    return True, 2
                if name.endswith("："):
                    return True, 2

            return False, 0

        items: list[tuple[str, float | None, int, bool]] = []
        cur_level = 0

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

            is_hdr, next_level = header_kind(name_clean)
            if is_hdr:
                # header rows should exist even without numeric value
                items.append((name_clean, float(num) if num is not None else None, 0, True))
                cur_level = next_level
                continue

            # keep only non-empty normal items
            if num is None:
                continue

            level = cur_level
            if name_clean.startswith(("其中", "其中：", "加：", "减：")):
                level = cur_level + 1

            items.append((name_clean, float(num), level, False))

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
            subset = [c for c in ["报告期"] if c in df.columns]
            if subset:
                raw_store.update_provider_table(self.name, key, df, subset=subset)
            else:
                raw_store.save_provider_table(self.name, key, df)

    def refresh_raw_history(self, ts_code: str, statement_type: str, raw_store: RawReportStore) -> str:
        import akshare as ak

        code6 = self._to_code6(ts_code)
        bs_raw = ak.stock_financial_debt_ths(symbol=code6, indicator="按报告期")
        is_raw = ak.stock_financial_benefit_ths(symbol=code6, indicator="按报告期")
        cf_raw = ak.stock_financial_cash_ths(symbol=code6, indicator="按报告期")
        self._persist_raw_tables(raw_store, code6, {"bs": bs_raw, "is": is_raw, "cf": cf_raw})
        merged = self._load_raw_tables(raw_store) or {"bs": bs_raw, "is": is_raw, "cf": cf_raw}
        return raw_store.save_provider_snapshot(
            self.name,
            merged,
            metadata={
                "scope": "full_history",
                "ts_code": ts_code,
                "statement_type": statement_type,
                "provider": self.name,
                "update_mode": "merge_full_source",
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
            bs, meta_bs = self._row_to_items(tables["bs"], period_end=period_end, sheet_cn="资产负债表")
            bs = self._postprocess_balance_sheet(bs)
            inc, meta_inc = self._row_to_items(tables["is"], period_end=period_end, sheet_cn="利润表")
            cf, meta_cf = self._row_to_items(tables["cf"], period_end=period_end, sheet_cn="现金流量表")
        except Exception:
            return None

        bundle_meta = {
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
            meta=bundle_meta,
            raw_data=tables,
        )

    @staticmethod
    def _postprocess_balance_sheet(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize THS balance sheet structure.

        目标（用户约束）：
        - 将表头前的若干“汇总行”归类到【报表核心指标】下。
        - 在负债段结束后插入【股东权益】标题行。

        说明：不依赖具体公司科目名称细节，仅做结构性整理。
        """

        if df is None or df.empty:
            return df
        if "科目" not in df.columns:
            return df

        out = df.copy().reset_index(drop=True)

        def _hdr_row(name: str) -> pd.DataFrame:
            # 用 np.nan 明确数值列 dtype 为 float，避免 pandas concat 的 FutureWarning（all-NA dtype 推断变化）
            import numpy as np

            return pd.DataFrame(
                [{"科目": name, "数值": np.nan, "__level": 0, "__is_header": True}],
                columns=["科目", "数值", "__level", "__is_header"],
            )

        # 1) Core metrics: leading non-header rows before the first header.
        try:
            first_hdr_idx = int(out.index[out["__is_header"] == True][0])  # noqa: E712
        except Exception:
            first_hdr_idx = None

        if first_hdr_idx is not None and first_hdr_idx > 0:
            leading = out.iloc[:first_hdr_idx].copy()
            rest = out.iloc[first_hdr_idx:].copy()
            # indent these summary lines
            leading["__level"] = leading["__level"].astype(int).map(lambda x: max(0, x) + 1)
            out = pd.concat([
                _hdr_row("报表核心指标"),
                leading,
                rest,
            ], ignore_index=True)

        # 2) Equity header: insert after the (later) total liabilities line.
        names = out["科目"].astype(str)
        # prefer the last exact match of "负债合计" (there is usually a summary one at the top too)
        liab_idx = None
        try:
            liab_idx = int(out.index[(names == "负债合计") & (out["__is_header"] == False)][-1])  # noqa: E712
        except Exception:
            liab_idx = None

        if liab_idx is not None and liab_idx + 1 < len(out):
            # If next row is already an equity header, skip
            next_name = str(out.iloc[liab_idx + 1]["科目"]).strip()
            has_equity_hdr = (names == "股东权益").any() or (names == "所有者权益").any()
            if (not has_equity_hdr) and next_name not in {"股东权益", "所有者权益"}:
                top = out.iloc[: liab_idx + 1].copy()
                bottom = out.iloc[liab_idx + 1 :].copy()
                out = pd.concat([
                    top,
                    _hdr_row("股东权益"),
                    bottom,
                ], ignore_index=True)

        return out

    def get_bundle(
        self,
        ts_code: str,
        period_end: date,
        statement_type: str,
        raw_store: RawReportStore | None = None,
    ) -> StatementBundle:
        import akshare as ak

        code6 = self._to_code6(ts_code)

        if raw_store:
            tables = self._load_raw_tables(raw_store)
            if tables:
                cached = self._build_bundle_from_raw(
                    ts_code=ts_code,
                    code6=code6,
                    period_end=period_end,
                    statement_type=statement_type,
                    tables=tables,
                )
                if cached:
                    return cached
                try:
                    self.refresh_raw_history(ts_code, statement_type, raw_store)
                    tables = self._load_raw_tables(raw_store)
                    if tables:
                        cached = self._build_bundle_from_raw(
                            ts_code=ts_code,
                            code6=code6,
                            period_end=period_end,
                            statement_type=statement_type,
                            tables=tables,
                        )
                        if cached:
                            cached.meta["raw_update_mode"] = "merge_full_source"
                            return cached
                except Exception:
                    pass

        # 按报告期：通常为累计(YTD)口径，更适配我们后续的 TTM/单季差分转换
        bs_raw = ak.stock_financial_debt_ths(symbol=code6, indicator="按报告期")
        is_raw = ak.stock_financial_benefit_ths(symbol=code6, indicator="按报告期")
        cf_raw = ak.stock_financial_cash_ths(symbol=code6, indicator="按报告期")

        bs, meta_bs = self._row_to_items(bs_raw, period_end=period_end, sheet_cn="资产负债表")
        bs = self._postprocess_balance_sheet(bs)

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

        bundle = StatementBundle(
            period_end=period_end,
            statement_type=statement_type,
            provider=self.name,
            balance_sheet=bs,
            income_statement=inc,
            cashflow_statement=cf,
            meta=meta,
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
