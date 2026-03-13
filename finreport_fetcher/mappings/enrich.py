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


_ROMAN = {"一": "I", "二": "II", "三": "III", "四": "IV", "五": "V", "六": "VI", "七": "VII", "八": "VIII", "九": "IX", "十": "X"}


def _fallback_en(prefix: str, cn: str) -> str:
    """Rule-based fallback English for unmapped CN subjects.

    This is *not* a full translation; it just helps readability and keeps EN non-empty.
    """

    s = (cn or "").strip()
    if not s:
        return "Item"

    m = re.match(r"^([一二三四五六七八九十])、(.*)$", s)
    if m:
        rn = _ROMAN.get(m.group(1), m.group(1))
        tail = m.group(2).strip()
        return f"{rn}. {tail}"  # tail may stay CN

    m = re.match(r"^（([一二三四五六七八九十])）(.*)$", s)
    if m:
        rn = _ROMAN.get(m.group(1), m.group(1))
        tail = m.group(2).strip()
        return f"({rn}) {tail}"

    for pfx_cn, pfx_en in [("其中：", "Of which: "), ("其中", "Of which: "), ("加：", "Add: "), ("减：", "Less: ")]:
        if s.startswith(pfx_cn):
            return pfx_en + s[len(pfx_cn):].strip()

    # sheet-based hints
    if prefix == "bs":
        return f"BS item: {s}"
    if prefix == "is":
        return f"IS item: {s}"
    if prefix == "cf":
        return f"CF item: {s}"

    return s


def enrich_statement_df(df: pd.DataFrame, *, sheet_name_cn: str) -> pd.DataFrame:
    """Add template-key + EN translation columns for a statement df.

    Input df should contain at least: 科目, 数值 (and may contain __level/__is_header).

    Output adds:
    - key: template key (e.g. is.revenue)
    - 科目_CN: original CN subject
    - 科目_EN: English translation (best-effort)
    - 科目: display subject "CN (EN)" (always)

    Notes:
    - We guarantee every row has a non-empty `key` so it can be referenced in template expressions.
    - EN is best-effort: known subjects use curated glossary; others use rule-based fallback.
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

        # Guarantee EN (best-effort)
        if not en:
            en = _fallback_en(prefix, cn)

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
    disp = []
    for cn, en in zip(cn_series.tolist(), ens):
        disp.append(f"{cn} ({en})")

    out["科目"] = disp

    return out
