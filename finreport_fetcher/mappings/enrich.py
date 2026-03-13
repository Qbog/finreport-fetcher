from __future__ import annotations

import re

import pandas as pd

from .subject_glossary import lookup_subject


_STATEMENT_PREFIX = {
    "资产负债表": "bs",
    "利润表": "is",
    "现金流量表": "cf",
}


def _prefix_from_sheet(sheet_name_cn: str) -> str:
    return _STATEMENT_PREFIX.get(sheet_name_cn, "")


def _safe_key_part(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "_", s)
    # allow chinese, ascii, numbers, underscore, dash, dot
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_\-\.]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_") or "item"


def enrich_statement_df(df: pd.DataFrame, *, sheet_name_cn: str) -> pd.DataFrame:
    """Add template-key + EN translation columns for a statement df.

    Input df should contain at least: 科目, 数值 (and may contain __level/__is_header).

    Output:
    - Adds `key` column (guaranteed non-empty, unique within sheet)
    - Rewrites `科目` display to: `中文 (English)` **only when English exists**

    Notes:
    - English is best-effort from curated glossary; unknown subjects keep English empty.
    - This function does NOT output 科目_CN / 科目_EN columns (user requested to avoid duplication).
    """

    if df is None or df.empty:
        return df

    prefix = _prefix_from_sheet(sheet_name_cn)

    out = df.copy()

    if "科目" not in out.columns:
        return out

    cn_series = out["科目"].astype(str)

    # 2) Key + EN mapping (guarantee non-empty key)
    keys: list[str] = []
    ens: list[str] = []
    seen: dict[str, int] = {}

    for cn in cn_series.tolist():
        if prefix in {"is", "bs", "cf"}:
            spec = lookup_subject(prefix, cn)
        else:
            spec = None

        k = spec.key if spec else ""
        en = spec.en if spec else ""

        # For tushare provider (科目 is english field), allow a simple auto-key
        if (not k) and prefix and cn and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cn):
            k = f"{prefix}.{cn}"
            en = en or cn

        # Guarantee key for every row
        if (not k) and prefix:
            k = f"{prefix}.auto.{_safe_key_part(cn)}"

        # Ensure uniqueness within a sheet
        if k:
            n = seen.get(k, 0)
            if n:
                k2 = f"{k}__{n+1}"
                seen[k] = n + 1
                k = k2
            else:
                seen[k] = 1

        keys.append(k)
        ens.append(en)

    # Insert key as the first column for readability
    if "key" not in out.columns:
        out.insert(0, "key", keys)

    # 3) Display subject: only append (EN) when EN exists
    disp = []
    for cn, en in zip(cn_series.tolist(), ens):
        disp.append(f"{cn} ({en})" if en else cn)

    out["科目"] = disp

    return out
