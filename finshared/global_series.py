from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pandas as pd

INDEX_ALIAS_MAP = {
    "上证": "sh000001",
    "上证综指": "sh000001",
    "sh000001": "sh000001",
    "深证": "sz399001",
    "深证成指": "sz399001",
    "sz399001": "sz399001",
    "创业板": "sz399006",
    "创业板指": "sz399006",
    "sz399006": "sz399006",
    "北证": "bj899050",
    "北证50": "bj899050",
    "bj899050": "bj899050",
}

COMMODITY_ALIAS_MAP = {
    "gold": "gold",
    "黄金": "gold",
    "silver": "silver",
    "白银": "silver",
    "oil": "oil",
    "石油": "oil",
}


def normalize_index_symbol(symbol: str) -> str | None:
    key = str(symbol or "").strip().lower()
    if not key:
        return None
    return INDEX_ALIAS_MAP.get(symbol) or INDEX_ALIAS_MAP.get(key)


def normalize_commodity_symbol(symbol: str) -> str | None:
    key = str(symbol or "").strip().lower()
    if not key:
        return None
    return COMMODITY_ALIAS_MAP.get(symbol) or COMMODITY_ALIAS_MAP.get(key)


def parse_global_series_ident(ident: str) -> tuple[str, str, str] | None:
    parts = str(ident or "").strip().split(".")
    if len(parts) < 3:
        return None
    ns = parts[0].lower()
    field = parts[-1]
    symbol = ".".join(parts[1:-1])
    if ns in {"idx", "index"}:
        code = normalize_index_symbol(symbol)
        if code:
            return "index", code, field
    if ns in {"com", "commodity"}:
        slug = normalize_commodity_symbol(symbol)
        if slug:
            return "commodity", slug, field
    return None


def resolve_global_series_csv(data_dir: Path, kind: str, symbol: str) -> Path | None:
    root = data_dir.resolve() / "_global"
    candidates: list[Path] = []
    if kind == "commodity":
        slug = normalize_commodity_symbol(symbol)
        if not slug:
            return None
        candidates = [
            root / "commodities" / slug / "price" / f"{slug}.csv",
            root / "commodities" / slug / f"{slug}.csv",
        ]
    elif kind == "index":
        code = normalize_index_symbol(symbol)
        if not code:
            return None
        candidates = [
            root / "indexes" / code / f"{code}.csv",
            root / "indexes" / code / "index" / f"{code}.csv",
        ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else None


def load_global_series_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        return pd.DataFrame(columns=["date"])
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    for col in out.columns:
        if col == "date":
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.reset_index(drop=True)


def global_series_value_on_or_before(df: pd.DataFrame, when: date, field: str) -> float | None:
    if df is None or df.empty or field not in df.columns:
        return None
    sub = df[df["date"] <= when]
    if sub.empty:
        return None
    val = sub.iloc[-1][field]
    if pd.isna(val):
        return None
    return float(val)
