from __future__ import annotations

import re

import pandas as pd

from .subject_glossary import lookup_subject, lookup_subject_by_key


_STATEMENT_PREFIX = {
    "资产负债表": "bs",
    "利润表": "is",
    "现金流量表": "cf",
}


# Minimal CN->EN hints for auto-generated remark/key when glossary is missing.
# Prefer filling `subject_glossary.py` for high-quality, stable mappings.
_CN_EN_OVERRIDES: dict[str, str] = {
    "负债和所有者权益合计": "Total liabilities and equity",
    "负债和所有者权益总计": "Total liabilities and equity",
    "所有者权益合计": "Total equity",
    "所有者权益总计": "Total equity",
    "资产合计": "Total assets",
    "资产总计": "Total assets",
}


def _auto_en_from_cn(cn: str) -> str:
    c = (cn or "").strip()
    if not c:
        return ""
    if c in _CN_EN_OVERRIDES:
        return _CN_EN_OVERRIDES[c]

    # very small heuristic: keep it readable, not perfect
    s = c
    s = s.replace("现金流入", "cash inflow")
    s = s.replace("现金流出", "cash outflow")
    s = s.replace("现金", "cash")
    s = s.replace("净额", "net")
    s = s.replace("小计", "subtotal")
    s = s.replace("合计", "total")
    s = s.replace("总计", "total")
    s = s.replace("经营活动", "operating activities")
    s = s.replace("投资活动", "investing activities")
    s = s.replace("筹资活动", "financing activities")
    s = s.replace("资产", "assets")
    s = s.replace("负债", "liabilities")
    s = s.replace("所有者权益", "equity")
    s = s.replace("股东权益", "equity")

    # If still contains CJK, return empty (force user to add glossary later)
    if re.search(r"[\u4e00-\u9fff]", s):
        return ""

    return s


def _slugify_en(en: str) -> str:
    ss = (en or "").strip().lower()
    ss = re.sub(r"[^a-z0-9]+", "_", ss)
    ss = re.sub(r"_+", "_", ss).strip("_")
    return ss


def _prefix_from_sheet(sheet_name_cn: str) -> str:
    return _STATEMENT_PREFIX.get(sheet_name_cn, "")


_RE_NUM_PREFIX = re.compile(r"^\s*([一二三四五六七八九十]+|\d+)[、\.．]\s*")
_RE_PREFIX_TAG = re.compile(r"^\s*(其中|加|减)[:：]\s*")


def _leading_tag_prefix(raw: str) -> str:
    """Return the leading tag prefix for display.

    Examples:
    - "其中：应收票据" -> "其中："
    - "加：资产减值准备" -> "加："
    - "减：所得税费用" -> "减："
    """

    s = (raw or "").strip()
    if s.startswith(("其中：", "其中:")):
        return "其中："
    if s.startswith(("加：", "加:")):
        return "加："
    if s.startswith(("减：", "减:")):
        return "减："
    # Some sources use "其中" without colon
    if s.startswith("其中"):
        return "其中："
    return ""
_RE_ROMAN_PREFIX = re.compile(r"^\s*[（\(]?[一二三四五六七八九十]+[）\)]\s*")


def _normalize_subject(s: str) -> str:
    """Normalize subject text to improve cross-provider consistency.

    目标：将不同数据源里“同一科目”的显示差异归一化，便于 lookup_subject 命中。

    典型处理：
    - 去掉编号前缀："一、" / "1." / "（一）" 等
    - 去掉提示前缀："其中：" / "加：" / "减："
    - 去掉部分括号提示："（或股东权益）" 这种可选说明
    - 去掉结尾冒号
    """

    ss = (s or "").strip()

    # If already like "中文 (English)", keep CN only for lookup
    if " (" in ss and ss.endswith(")"):
        ss = ss.split(" (", 1)[0].strip()

    # Remove common numbering prefixes: "一、" / "1." etc.
    ss = _RE_NUM_PREFIX.sub("", ss)

    # Remove "（一）" / "(I)" like prefixes
    ss = _RE_ROMAN_PREFIX.sub("", ss)

    # Remove tags like "其中：" / "加：" / "减："
    ss = _RE_PREFIX_TAG.sub("", ss)

    # Remove some verbose end-notes that appear in certain sources
    ss = re.sub(r"（净亏损以.*?填列）", "", ss)

    # Remove optional hints like "（或股东权益）" / "（或股本）" etc.
    ss = re.sub(r"（或[^）]+）", "", ss)

    # Strip trailing ':'
    ss = ss.rstrip("：:")

    # Normalize whitespace
    ss = re.sub(r"\s+", " ", ss).strip()

    return ss


def _as_float(v) -> float | None:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _is_redundant_duplicate_value(v, first) -> bool:
    """Heuristic to drop obvious duplicated lines.

    Many providers repeat totals or placeholder 0 lines. If a canonical key repeats and
    the later value is empty/0 or equals the first value, we can safely drop it.
    """

    fv = _as_float(v)
    f1 = _as_float(first)

    if fv is None:
        return True
    if abs(fv) < 1e-12:
        return True
    if f1 is None:
        return False
    return abs(fv - f1) < 1e-9


def _patch_balance_sheet_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Patch balance sheet hierarchy to make it consistent across providers.

    Goals:
    - Add a header row "报表核心指标" for the first 4 core metrics.
    - Add a header row "股东权益" before equity detail items (some sources omit it).

    This operates on provider-native columns: 科目/数值 and optional __level/__is_header.
    """

    out = df.copy()

    if "__level" not in out.columns:
        out["__level"] = 0
    if "__is_header" not in out.columns:
        out["__is_header"] = False

    # ---- core metrics header (first 4 lines) ----
    subj0 = out["科目"].astype(str).tolist()
    norm0 = [_normalize_subject(s) for s in subj0]

    core_set = {
        "资产合计",
        "资产总计",
        "负债合计",
        "所有者权益合计",
        "所有者权益总计",
        "归属于母公司所有者权益合计",
        "归属于母公司所有者权益总计",
    }

    if len(norm0) >= 4 and all((n in core_set) for n in norm0[:4]):
        if norm0[0] != "报表核心指标":
            header = {c: None for c in out.columns}
            header.update({"科目": "报表核心指标", "数值": None, "__level": 0, "__is_header": True})
            out = pd.concat([pd.DataFrame([header]), out], ignore_index=True)
            # indent the 4 core lines under the header
            for r in range(1, 5):
                out.at[r, "__level"] = 1
                out.at[r, "__is_header"] = False

    # ---- equity header ----
    subj = out["科目"].astype(str).tolist()
    norm = [_normalize_subject(s) for s in subj]

    has_equity_header = False
    for i, n in enumerate(norm):
        if n in {"所有者权益", "股东权益"} and bool(out.iloc[i].get("__is_header")):
            has_equity_header = True
            break

    if not has_equity_header:
        equity_markers = {
            "实收资本（或股本）",
            "实收资本(或股本)",
            "实收资本",
            "股本",
            "资本公积",
            "盈余公积",
            "未分配利润",
        }
        eq_idx = None
        for i, n in enumerate(norm):
            if n in equity_markers:
                eq_idx = i
                break

        if eq_idx is not None:
            header = {c: None for c in out.columns}
            header.update({"科目": "股东权益", "数值": None, "__level": 0, "__is_header": True})
            top = out.iloc[:eq_idx].copy()
            bot = out.iloc[eq_idx:].copy()
            out = pd.concat([top, pd.DataFrame([header]), bot], ignore_index=True)

            # ensure equity detail items are indented
            # (some sources already give __level=1; keep the max)
            for r in range(eq_idx + 1, len(out)):
                try:
                    lvl = int(out.at[r, "__level"])
                except Exception:
                    lvl = 0
                if lvl < 1 and not bool(out.at[r, "__is_header"]):
                    out.at[r, "__level"] = 1

    return out


def enrich_statement_df(df: pd.DataFrame, *, sheet_name_cn: str) -> pd.DataFrame:
    """Add stable template key + English remark for a statement df.

    Input df should contain at least: 科目, 数值 (and may contain __level/__is_header).

    Output:
    - Adds `key` column: stable, unique, **ASCII-only**.
    - Adds `备注` column: English name (from curated glossary; if missing, leave blank).
    - Canonicalizes `科目` to the glossary CN name when available (cross-provider consistency).

    约束：
    - key 不能包含中文或任何非 ASCII 字符。
    - 不同数据源导出的同一科目，尽可能输出同一 key。
    """

    if df is None or df.empty:
        return df

    prefix = _prefix_from_sheet(sheet_name_cn)

    out = df.copy()

    if "科目" not in out.columns:
        return out

    # 结构修补：不同数据源的资产负债表经常缺少“报表核心指标/股东权益”等分组标题。
    # 在 enrich 层统一补齐，确保跨 provider 输出结构一致。
    if sheet_name_cn == "资产负债表":
        out = _patch_balance_sheet_structure(out)

    cn_series_raw = out["科目"].astype(str)

    # 2) Key + English remark mapping
    keys: list[str] = []
    ens: list[str] = []
    cn_canon: list[str] = []
    # seen: used keys inside this sheet (for uniqueness)
    seen: dict[str, int] = {}

    # canonical key tracking (for duplicate handling)
    canon_first_value: dict[str, object] = {}
    canon_dup_count: dict[str, int] = {}

    keep_rows: list[int] = []

    for i, cn_raw in enumerate(cn_series_raw.tolist()):
        tag_prefix = _leading_tag_prefix(cn_raw)
        cn_norm = _normalize_subject(cn_raw)

        if prefix in {"is", "bs", "cf"}:
            # try raw first, then normalized
            spec = lookup_subject(prefix, cn_raw.strip()) or lookup_subject(prefix, cn_norm)
        else:
            spec = None

        if spec:
            k = spec.key
            en = spec.en
            cn_base = spec.cn  # canonical CN for cross-provider consistency
        else:
            # 未映射科目：生成可读英文 key（不允许 hash）。
            # 质量更高/更稳定的做法：把该科目补进 subject_glossary.py。
            cn_base = cn_norm

            # 1) If looks like an English identifier (e.g. tushare fields), derive from it.
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cn_base):
                en = cn_base.replace("_", " ").strip().title()
            else:
                en = _auto_en_from_cn(cn_base)

            if not en:
                raise RuntimeError(f"未映射科目缺少英文名称，请补齐 subject_glossary 映射：{cn_base}")

            slug = _slugify_en(en)
            if not slug:
                raise RuntimeError(f"未能从英文名称生成 key：{cn_base} -> {en}")

            k = f"{prefix}.{slug}" if prefix else slug

            # If the auto-generated key matches a curated spec, upgrade to canonical CN/EN.
            spec2 = lookup_subject_by_key(k)
            if spec2:
                cn_base = spec2.cn
                en = spec2.en

        cn_disp = f"{tag_prefix}{cn_base}" if tag_prefix else cn_base

        canon_k = k
        v = out.iloc[i]["数值"] if "数值" in out.columns else None

        # 1) Tagged sub-lines: derive stable sub-key when base exists.
        if tag_prefix and canon_k in canon_first_value:
            if tag_prefix == "其中：":
                k = f"{canon_k}.sub"
            elif tag_prefix == "加：":
                k = f"{canon_k}.add"
            elif tag_prefix == "减：":
                k = f"{canon_k}.minus"
            else:
                k = canon_k

        # 2) Repeated canonical lines: drop obvious duplicates; otherwise keep with stable suffix.
        elif canon_k in canon_first_value:
            if _is_redundant_duplicate_value(v, canon_first_value[canon_k]):
                continue
            canon_dup_count[canon_k] = canon_dup_count.get(canon_k, 1) + 1
            k = f"{canon_k}.dup{canon_dup_count[canon_k]}"

        else:
            canon_first_value[canon_k] = v
            canon_dup_count[canon_k] = 1
            k = canon_k

        # Ensure uniqueness within this sheet
        if k:
            base = k
            n = seen.get(base, 0) + 1
            seen[base] = n
            if n > 1:
                k = f"{base}__{n}"

            # Enforce ASCII-only key
            try:
                k.encode("ascii")
            except Exception:
                raise RuntimeError(f"key 必须为 ASCII：{k} ({cn_disp})")
        else:
            raise RuntimeError(f"未能为科目生成 key：{cn_disp}")

        keep_rows.append(i)
        keys.append(k)
        ens.append(en)
        cn_canon.append(cn_disp)

    # Drop rows we decided to skip (duplicate placeholders/totals)
    out = out.iloc[keep_rows].copy().reset_index(drop=True)

    # Insert key as the first column for readability
    if "key" not in out.columns:
        out.insert(0, "key", keys)

    # Add English remark column (always present for stable format)
    if "备注" not in out.columns:
        out.insert(2, "备注", ens)
    else:
        out["备注"] = ens

    # Canonical CN subject
    out["科目"] = cn_canon

    return out
