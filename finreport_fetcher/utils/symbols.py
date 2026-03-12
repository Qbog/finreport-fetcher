from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ResolvedSymbol:
    code6: str  # 6-digit
    ts_code: str  # 000001.SZ
    market: str  # SZ/SH
    name: str | None = None


_CODE6_RE = re.compile(r"^(\d{6})$")
_TS_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_AK_RE = re.compile(r"^(sh|sz|bj)(\d{6})$", re.IGNORECASE)


def normalize_code_like(s: str) -> str:
    return s.strip().upper()


def parse_code(s: str) -> ResolvedSymbol | None:
    s0 = normalize_code_like(s)

    m = _CODE6_RE.match(s0)
    if m:
        code6 = m.group(1)
        market = "SH" if code6.startswith("6") else ("BJ" if code6.startswith("8") or code6.startswith("9") else "SZ")
        return ResolvedSymbol(code6=code6, ts_code=f"{code6}.{market}", market=market)

    m = _TS_RE.match(s0)
    if m:
        code6, market = m.group(1), m.group(2).upper()
        return ResolvedSymbol(code6=code6, ts_code=f"{code6}.{market}", market=market)

    m = _AK_RE.match(s0)
    if m:
        market, code6 = m.group(1).upper(), m.group(2)
        market = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}[market]
        return ResolvedSymbol(code6=code6, ts_code=f"{code6}.{market}", market=market)

    return None


def load_a_share_name_map() -> pd.DataFrame:
    # 用 akshare 做名称-代码映射（容错强一些）
    import akshare as ak

    df = ak.stock_info_a_code_name()
    # 兼容不同版本字段
    # 常见: code, name
    cols = {c.lower(): c for c in df.columns}
    code_col = cols.get("code") or cols.get("股票代码")
    name_col = cols.get("name") or cols.get("股票简称")
    if not code_col or not name_col:
        raise RuntimeError(f"无法识别 stock_info_a_code_name 返回字段: {list(df.columns)}")

    out = df[[code_col, name_col]].rename(columns={code_col: "code", name_col: "name"})
    out["code"] = out["code"].astype(str).str.zfill(6)
    out["name"] = out["name"].astype(str)
    return out


def fuzzy_match_name(df_map: pd.DataFrame, keyword: str) -> pd.DataFrame:
    kw = keyword.strip()
    if not kw:
        raise ValueError("名称关键词不能为空")

    # 简单包含匹配；需要更复杂可再升级（拼音/相似度）
    m = df_map["name"].str.contains(kw, case=False, na=False)
    return df_map[m].sort_values(["name", "code"]).reset_index(drop=True)
