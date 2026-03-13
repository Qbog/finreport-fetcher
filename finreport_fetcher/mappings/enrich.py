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


def enrich_statement_df(df: pd.DataFrame, *, sheet_name_cn: str) -> pd.DataFrame:
    """Add template-key + EN translation columns for a statement df.

    Input df should contain at least: 科目, 数值 (and may contain __level/__is_header).

    Output adds (best-effort):
    - key: template key (e.g. is.revenue)
    - 科目_CN: original CN subject
    - 科目_EN: English translation (if known)
    - 科目: display subject "CN (EN)" when EN available, else CN

    Unknown subjects keep key/en empty.
    """

    if df is None or df.empty:
        return df

    prefix = _prefix_from_sheet(sheet_name_cn)

    out = df.copy()

    # 1) CN subject column
    if "科目_CN" not in out.columns:
        if "科目" in out.columns:
            out.insert(0, "科目_CN", out["科目"].astype(str))
        else:
            out.insert(0, "科目_CN", "")

    cn_series = out["科目_CN"].astype(str)

    # 2) Key + EN mapping
    keys: list[str] = []
    ens: list[str] = []

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
            en = cn

        keys.append(k)
        ens.append(en)

    # Insert key as the first column for readability
    if "key" not in out.columns:
        out.insert(0, "key", keys)

    # 科目_EN next to 科目_CN
    if "科目_EN" not in out.columns:
        # place after 科目_CN if possible
        try:
            idx = out.columns.get_loc("科目_CN") + 1
        except Exception:
            idx = 2
        out.insert(idx, "科目_EN", ens)

    # 3) Display subject
    # Keep old 科目 if not present, otherwise overwrite to CN (EN)
    disp = []
    for cn, en in zip(cn_series.tolist(), ens):
        disp.append(f"{cn} ({en})" if en else cn)

    out["科目"] = disp

    return out
