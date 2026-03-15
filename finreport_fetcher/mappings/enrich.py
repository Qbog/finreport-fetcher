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
    # 标记：结构性重复行（例如“报表核心指标”只是聚焦展示，但对应科目仍应在原区块里保留一份）
    if "__dup_keep" not in out.columns:
        out["__dup_keep"] = False

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

        # ---- duplicate core metrics into their native sections ----
        # “报表核心指标”只是聚焦展示；核心科目在资产/负债/权益区块底部也应存在一份（同花顺/东方财富/雪球风格）。
        subj2 = out["科目"].astype(str).tolist()
        norm2 = [_normalize_subject(s) for s in subj2]

        # find core header idx
        core_hdr_idx = None
        for i, n in enumerate(norm2):
            if n == "报表核心指标" and bool(out.iloc[i].get("__is_header")):
                core_hdr_idx = i
                break

        if core_hdr_idx is not None and (core_hdr_idx + 4) < len(out):
            core_end = core_hdr_idx + 4
            core_rows: dict[str, dict] = {}
            for j in range(core_hdr_idx + 1, core_end + 1):
                n = _normalize_subject(str(out.iloc[j].get("科目", "")))
                if n in core_set:
                    core_rows[n] = out.iloc[j].to_dict()

            def _has_later(nm: str) -> bool:
                return any(x == nm for x in norm2[core_end + 1 :])

            def _insert_dup(at_idx: int, row_dict: dict) -> None:
                nonlocal out, subj2, norm2
                row2 = {c: None for c in out.columns}
                row2.update(row_dict)
                row2["__level"] = 0
                row2["__is_header"] = False
                row2["__dup_keep"] = True
                top = out.iloc[:at_idx].copy()
                bot = out.iloc[at_idx:].copy()
                out = pd.concat([top, pd.DataFrame([row2]), bot], ignore_index=True)
                subj2 = out["科目"].astype(str).tolist()
                norm2 = [_normalize_subject(s) for s in subj2]

            # 1) 资产总计：放在负债开始之前（资产区块末尾）
            asset_nm = "资产总计" if "资产总计" in core_rows else ("资产合计" if "资产合计" in core_rows else None)
            if asset_nm and not _has_later(_normalize_subject(asset_nm)):
                liab_markers = {
                    "流动负债",
                    "非流动负债",
                    "流动负债合计",
                    "非流动负债合计",
                    "负债合计",
                }
                liab_start = None
                for i in range(core_end + 1, len(norm2)):
                    if norm2[i] in liab_markers:
                        liab_start = i
                        break
                if liab_start is not None:
                    _insert_dup(liab_start, core_rows[_normalize_subject(asset_nm)])

            # 2) 负债合计：放在非流动负债合计之后（若无则放在股东权益标题之前）
            liab_nm = "负债合计" if "负债合计" in core_rows else None
            if liab_nm and not _has_later("负债合计"):
                idx_after = None
                for i in range(len(norm2)):
                    if i <= core_end:
                        continue
                    if norm2[i] == "非流动负债合计":
                        idx_after = i + 1
                        break
                if idx_after is None:
                    for i in range(len(norm2)):
                        if i <= core_end:
                            continue
                        if norm2[i] == "股东权益" and bool(out.iloc[i].get("__is_header")):
                            idx_after = i
                            break
                if idx_after is not None:
                    _insert_dup(idx_after, core_rows["负债合计"])

            # 3) 所有者权益合计：放在表末尾
            eq_nm = None
            for cand in ["所有者权益合计", "所有者权益总计", "股东权益合计", "股东权益总计"]:
                k2 = _normalize_subject(cand)
                if k2 in core_rows:
                    eq_nm = k2
                    break
            if eq_nm and not _has_later(eq_nm):
                _insert_dup(len(out), core_rows[eq_nm])

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
    """Add stable template key + notes + English for a statement df.

    Input df should contain at least: 科目, 数值 (and may contain __level/__is_header).

    Output:
    - Adds `key` column: stable, unique, **ASCII-only**.
    - Adds `备注` column: CN note / explanation (from curated glossary; may be blank).
    - Adds `英文` column: English translation (from curated glossary).
    - Adds `__uncommon` flag: mark non-common subjects (for Excel highlighting).
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
    notes: list[str] = []
    ens: list[str] = []
    cn_canon: list[str] = []
    uncommon_flags: list[bool] = []
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
            note = (spec.note or "").strip()
            uncommon = not bool(getattr(spec, "common", True))
            if uncommon and not note:
                note = "非通用科目：仅少数公司/行业披露，口径以财报附注为准。"
        else:
            # 未映射科目：生成可读英文 key（不允许 hash）。
            # 质量更高/更稳定的做法：把该科目补进 subject_glossary.py。
            cn_base = cn_norm
            note = ""
            uncommon = True

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
                note = (spec2.note or "").strip()
                uncommon = not bool(getattr(spec2, "common", True))
                if uncommon and not note:
                    note = "非通用科目：仅少数公司/行业披露，口径以财报附注为准。"

        cn_disp = f"{tag_prefix}{cn_base}" if tag_prefix else cn_base

        canon_k = k
        v = out.iloc[i]["数值"] if "数值" in out.columns else None
        force_keep_dup = bool(out.iloc[i].get("__dup_keep")) if "__dup_keep" in out.columns else False

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
            # 结构性重复（例如：核心指标在资产/负债/权益区块也要保留一份）必须保留，
            # 即便数值与首个 canonical 行相同。
            if not force_keep_dup and _is_redundant_duplicate_value(v, canon_first_value[canon_k]):
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
        notes.append(note)
        ens.append(en)
        cn_canon.append(cn_disp)
        uncommon_flags.append(bool(uncommon))

    # Drop rows we decided to skip (duplicate placeholders/totals)
    out = out.iloc[keep_rows].copy().reset_index(drop=True)

    # key（稳定 ASCII-only）
    if "key" not in out.columns:
        out.insert(0, "key", keys)

    # 备注（中文说明）
    if "备注" not in out.columns:
        out.insert(2, "备注", notes)
    else:
        out["备注"] = notes

    # 英文（翻译）
    if "英文" not in out.columns:
        out.insert(3, "英文", ens)
    else:
        out["英文"] = ens

    # 是否非通用科目（用于 Excel 上色）
    if "__uncommon" not in out.columns:
        out["__uncommon"] = uncommon_flags
    else:
        out["__uncommon"] = uncommon_flags

    # Canonical CN subject
    out["科目"] = cn_canon

    return out
