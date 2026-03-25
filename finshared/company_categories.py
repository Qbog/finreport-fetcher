from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finshared.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code


@dataclass(frozen=True)
class CompanyCategoryItem:
    code6: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class CompanyCategory:
    name: str
    alias: str | None
    items: list[CompanyCategoryItem]


@dataclass(frozen=True)
class ResolvedCompanyCategory:
    category: CompanyCategory
    symbols: list[ResolvedSymbol]
    warnings: list[str]


def _toml_loads():
    try:
        import tomllib

        return tomllib.loads
    except Exception:
        import tomli

        return tomli.loads


def default_company_categories_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "company_categories.toml"


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _normalize_code(code: str) -> ResolvedSymbol:
    rs = parse_code(code)
    if not rs:
        raise ValueError(f"无法解析公司代码: {code}")
    return rs


def _parse_items(items_raw: Any) -> list[CompanyCategoryItem]:
    items: list[CompanyCategoryItem] = []
    if isinstance(items_raw, list):
        for it in items_raw:
            if isinstance(it, dict):
                code = _as_str(it.get("code") or it.get("code6") or it.get("ts_code"))
                name = _as_str(it.get("name") or it.get("alias"))
                if code:
                    rs = _normalize_code(code)
                    items.append(CompanyCategoryItem(code6=rs.code6, name=name))
                elif name:
                    items.append(CompanyCategoryItem(code6=None, name=name))
            elif isinstance(it, str):
                s = _as_str(it)
                if not s:
                    continue
                rs = parse_code(s)
                if rs:
                    items.append(CompanyCategoryItem(code6=rs.code6, name=None))
                else:
                    items.append(CompanyCategoryItem(code6=None, name=s))
    return items


def load_company_categories(path: Path | None = None) -> dict[str, CompanyCategory]:
    cfg_path = path or default_company_categories_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"公司分类配置文件不存在: {cfg_path}")

    data = _toml_loads()(cfg_path.read_text(encoding="utf-8"))
    raw = data.get("categories") or data.get("category") or data.get("groups")
    if not raw:
        raise ValueError(f"公司分类配置为空或缺少 [categories] 段: {cfg_path}")

    out: dict[str, CompanyCategory] = {}
    if isinstance(raw, dict):
        for name, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            alias = _as_str(cfg.get("alias") or cfg.get("label"))
            items = _parse_items(cfg.get("items") or cfg.get("item") or [])
            if items:
                out[str(name)] = CompanyCategory(name=str(name), alias=alias, items=items)
    elif isinstance(raw, list):
        for cfg in raw:
            if not isinstance(cfg, dict):
                continue
            name = _as_str(cfg.get("name"))
            if not name:
                continue
            alias = _as_str(cfg.get("alias") or cfg.get("label"))
            items = _parse_items(cfg.get("items") or cfg.get("item") or [])
            if items:
                out[name] = CompanyCategory(name=name, alias=alias, items=items)

    if not out:
        raise ValueError(f"公司分类配置未解析到任何分类: {cfg_path}")
    return out


def resolve_company_category(name: str, path: Path | None = None) -> CompanyCategory:
    cfg_path = path or default_company_categories_path()
    cats = load_company_categories(cfg_path)

    key = (name or "").strip()
    if not key:
        raise ValueError("分类名不能为空")
    if key in cats:
        return cats[key]
    for k, v in cats.items():
        if k.lower() == key.lower():
            return v
    avail = ", ".join(sorted(cats.keys()))
    raise KeyError(f"未找到分类: {name}. 可用分类: {avail}. 配置文件: {cfg_path}（可用 --category-config 指定）")


def _resolve_by_code(code6: str, *, hinted_name: str | None, df_map) -> ResolvedSymbol:
    rs0 = _normalize_code(code6)
    name0 = hinted_name
    if df_map is not None:
        try:
            m = df_map["code"].astype(str).str.zfill(6) == rs0.code6
            if m.any():
                name0 = str(df_map[m].iloc[0]["name"])
        except Exception:
            pass
    return ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=name0)


def _resolve_by_name(name: str, df_map) -> tuple[ResolvedSymbol | None, str | None]:
    if df_map is None:
        return None, f"分类项 {name} 仅填写了名称，但当前无法加载 A 股名称映射，已跳过。"

    cand = df_map[df_map["name"].astype(str).str.strip() == str(name).strip()].reset_index(drop=True)
    if cand.empty:
        try:
            cand = fuzzy_match_name(df_map, name)
        except Exception:
            cand = df_map.iloc[0:0].copy()
    if cand.empty:
        return None, f"分类项 {name} 未匹配到 A 股公司，已跳过。"

    row = cand.iloc[0]
    rs = parse_code(str(row["code"]))
    if not rs:
        return None, f"分类项 {name} 匹配到的代码无法解析：{row['code']}，已跳过。"

    warning = None
    if len(cand) > 1:
        warning = f"分类项 {name} 匹配到多个公司，默认使用 {rs.code6} {row['name']}。"
    return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=str(row["name"])), warning


def resolve_company_category_symbols(name: str, path: Path | None = None) -> ResolvedCompanyCategory:
    category = resolve_company_category(name, path)
    try:
        df_map = load_a_share_name_map()
    except Exception:
        df_map = None

    seen: set[str] = set()
    warnings: list[str] = []
    symbols: list[ResolvedSymbol] = []

    for item in category.items:
        code6 = _as_str(item.code6)
        item_name = _as_str(item.name)
        rs: ResolvedSymbol | None = None
        warning: str | None = None

        if code6:
            try:
                rs = _resolve_by_code(code6, hinted_name=item_name, df_map=df_map)
            except Exception as exc:
                warning = f"分类项 {item_name or code6} 代码无效：{exc}，已跳过。"
        elif item_name:
            rs, warning = _resolve_by_name(item_name, df_map)
        else:
            warning = "分类项缺少 name/code，已跳过。"

        if warning:
            warnings.append(warning)
        if rs is None:
            continue
        if rs.code6 in seen:
            continue
        seen.add(rs.code6)
        symbols.append(rs)

    if not symbols:
        raise ValueError(f"分类 {category.name} 未解析到任何有效公司")

    deduped_warnings: list[str] = []
    seen_warn: set[str] = set()
    for msg in warnings:
        if msg in seen_warn:
            continue
        seen_warn.add(msg)
        deduped_warnings.append(msg)

    return ResolvedCompanyCategory(category=category, symbols=symbols, warnings=deduped_warnings)
