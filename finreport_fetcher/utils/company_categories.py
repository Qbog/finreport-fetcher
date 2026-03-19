from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .symbols import ResolvedSymbol, parse_code


@dataclass(frozen=True)
class CompanyCategoryItem:
    code6: str
    name: str | None = None


@dataclass(frozen=True)
class CompanyCategory:
    name: str
    alias: str | None
    items: list[CompanyCategoryItem]


def _toml_loads():
    try:
        import tomllib  # py>=3.11

        return tomllib.loads
    except Exception:  # py3.10 fallback
        import tomli

        return tomli.loads


def default_company_categories_path() -> Path:
    # repo_root/finreport_fetcher/utils -> repo_root
    return Path(__file__).resolve().parents[2] / "config" / "company_categories.toml"


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
            items_raw = cfg.get("items") or cfg.get("item") or []
            items = _parse_items(items_raw)
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
            items_raw = cfg.get("items") or cfg.get("item") or []
            items = _parse_items(items_raw)
            if items:
                out[name] = CompanyCategory(name=name, alias=alias, items=items)

    if not out:
        raise ValueError(f"公司分类配置未解析到任何分类: {cfg_path}")

    return out


def _parse_items(items_raw: Any) -> list[CompanyCategoryItem]:
    items: list[CompanyCategoryItem] = []
    if isinstance(items_raw, list):
        for it in items_raw:
            if isinstance(it, dict):
                code = _as_str(it.get("code") or it.get("code6") or it.get("ts_code"))
                if not code:
                    continue
                rs = _normalize_code(code)
                name = _as_str(it.get("name") or it.get("alias"))
                items.append(CompanyCategoryItem(code6=rs.code6, name=name))
            elif isinstance(it, str):
                rs = _normalize_code(it)
                items.append(CompanyCategoryItem(code6=rs.code6, name=None))
    return items


def resolve_company_category(name: str, path: Path | None = None) -> CompanyCategory:
    cfg_path = path or default_company_categories_path()
    cats = load_company_categories(cfg_path)

    key = (name or "").strip()
    if not key:
        raise ValueError("分类名不能为空")
    if key in cats:
        return cats[key]

    # try case-insensitive match
    for k, v in cats.items():
        if k.lower() == key.lower():
            return v

    avail = ", ".join(sorted(cats.keys()))
    raise KeyError(
        f"未找到分类: {name}. 可用分类: {avail}. 配置文件: {cfg_path}（可用 --category-config 指定）"
    )
