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
    """加载 A 股 code<->name 映射。

    为了让“按名称查询”更稳定：
    - 优先使用 cninfo 的 stockList（网络更稳，且不依赖 token）
    - 带本地缓存（避免每次都拉取全量列表）
    - cninfo 失败时回退到 akshare / tushare（若可用）
    """

    from pathlib import Path
    import time
    import requests

    cache_dir = Path.home() / ".cache" / "finreport_fetcher"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "a_share_name_map.csv"

    # 7 天缓存
    if cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < 7 * 24 * 3600:
                dfc = pd.read_csv(cache_path)
                if {"code", "name"}.issubset(dfc.columns):
                    dfc["code"] = dfc["code"].astype(str).str.zfill(6)
                    dfc["name"] = dfc["name"].astype(str)
                    return dfc[["code", "name"]]
        except Exception:
            pass

    # 1) cninfo
    try:
        j = requests.get("http://www.cninfo.com.cn/new/data/szse_stock.json", timeout=20).json()
        stock_list = j.get("stockList") or []
        rows = []
        for s in stock_list:
            code = str(s.get("code", "")).zfill(6)
            name = str(s.get("zwjc", ""))
            if not code.isdigit() or len(code) != 6:
                continue
            if not name:
                continue
            rows.append((code, name))
        df = pd.DataFrame(rows, columns=["code", "name"]).drop_duplicates()
        df.to_csv(cache_path, index=False)
        return df
    except Exception:
        # cninfo 不可用时，如果有旧缓存就用旧缓存
        if cache_path.exists():
            dfc = pd.read_csv(cache_path)
            if {"code", "name"}.issubset(dfc.columns):
                dfc["code"] = dfc["code"].astype(str).str.zfill(6)
                dfc["name"] = dfc["name"].astype(str)
                return dfc[["code", "name"]]

    # 2) akshare fallback
    try:
        import akshare as ak

        df = ak.stock_info_a_code_name()
        cols = {c.lower(): c for c in df.columns}
        code_col = cols.get("code") or cols.get("股票代码") or cols.get("证券代码")
        name_col = cols.get("name") or cols.get("股票简称") or cols.get("证券简称")
        if not code_col or not name_col:
            raise RuntimeError(f"无法识别 stock_info_a_code_name 返回字段: {list(df.columns)}")
        out = df[[code_col, name_col]].rename(columns={code_col: "code", name_col: "name"})
        out["code"] = out["code"].astype(str).str.zfill(6)
        out["name"] = out["name"].astype(str)
        out[["code", "name"]].drop_duplicates().to_csv(cache_path, index=False)
        return out[["code", "name"]]
    except Exception:
        pass

    # 3) tushare fallback（有 token 时）
    try:
        import os
        import tushare as ts

        token = os.getenv("TUSHARE_TOKEN")
        if token:
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name")
            if df is not None and not df.empty:
                out = df[["symbol", "name"]].rename(columns={"symbol": "code", "name": "name"})
                out["code"] = out["code"].astype(str).str.zfill(6)
                out["name"] = out["name"].astype(str)
                out[["code", "name"]].drop_duplicates().to_csv(cache_path, index=False)
                return out[["code", "name"]]
    except Exception:
        pass

    raise RuntimeError("无法加载 A 股名称映射（cninfo/akshare/tushare 均失败）")


def fuzzy_match_name(df_map: pd.DataFrame, keyword: str) -> pd.DataFrame:
    kw = keyword.strip()
    if not kw:
        raise ValueError("名称关键词不能为空")

    # 简单包含匹配；需要更复杂可再升级（拼音/相似度）
    m = df_map["name"].str.contains(kw, case=False, na=False)
    return df_map[m].sort_values(["name", "code"]).reset_index(drop=True)
