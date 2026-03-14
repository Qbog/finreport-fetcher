from __future__ import annotations

import hashlib
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


_RE_NUM_PREFIX = re.compile(r"^\s*([一二三四五六七八九十]+|\d+)[、\.．]\s*")


def _normalize_subject(s: str) -> str:
    """Normalize subject display text to improve cross-provider consistency."""

    ss = (s or "").strip()

    # If already like "中文 (English)", keep CN only for lookup
    if " (" in ss and ss.endswith(")"):
        ss = ss.split(" (", 1)[0].strip()

    # Remove common numbering prefixes: "一、" / "1." etc.
    ss = _RE_NUM_PREFIX.sub("", ss)

    # Remove some verbose end-notes that appear in certain sources
    ss = re.sub(r"（净亏损以.*?填列）", "", ss)

    # Normalize whitespace
    ss = re.sub(r"\s+", " ", ss).strip()

    return ss


def _fallback_key(prefix: str, subj_norm: str) -> str:
    """Generate ASCII-only stable key for unknown subjects.

    Requirements:
    - key must be fully ASCII (no CN chars)
    - should be stable across providers as long as normalized subject string matches
    """

    token = f"{prefix}:{subj_norm}".encode("utf-8")
    h10 = hashlib.sha1(token).hexdigest()[:10]
    return f"{prefix}.unk.{h10}"


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

    cn_series_raw = out["科目"].astype(str)

    # 2) Key + EN mapping (guarantee key, ASCII-only)
    keys: list[str] = []
    ens: list[str] = []
    cn_canon: list[str] = []
    seen: dict[str, int] = {}

    for cn_raw in cn_series_raw.tolist():
        cn_norm = _normalize_subject(cn_raw)

        if prefix in {"is", "bs", "cf"}:
            # try raw first, then normalized
            spec = lookup_subject(prefix, cn_raw.strip()) or lookup_subject(prefix, cn_norm)
        else:
            spec = None

        if spec:
            k = spec.key
            en = spec.en
            cn_disp = spec.cn  # canonical CN for cross-provider consistency
        else:
            # For providers that return pure-English identifiers in 科目 (rare): keep as EN display.
            if prefix and cn_norm and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cn_norm):
                k = f"{prefix}.raw.{cn_norm.lower()}"
                en = cn_norm
                cn_disp = cn_norm
            else:
                k = _fallback_key(prefix, cn_norm) if prefix else _fallback_key("unk", cn_norm)
                en = ""
                cn_disp = cn_norm

        # Ensure uniqueness within a sheet
        n = seen.get(k, 0)
        if n:
            k = f"{k}__{n+1}"
            seen[k] = n + 1
        else:
            seen[k] = 1

        # Enforce ASCII-only key
        try:
            k.encode("ascii")
        except Exception:
            k = _fallback_key(prefix or "unk", cn_norm)

        keys.append(k)
        ens.append(en)
        cn_canon.append(cn_disp)

    # Insert key as the first column for readability
    if "key" not in out.columns:
        out.insert(0, "key", keys)

    # 3) Display subject: only append (EN) when EN exists
    disp: list[str] = []
    for cn, en in zip(cn_canon, ens):
        disp.append(f"{cn} ({en})" if en else cn)

    out["科目"] = disp

    return out
