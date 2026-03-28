from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class BarBlock:
    """A bar definition.

    支持嵌套：如果只提供 children（不提供 expr），则该节点作为“分组”，不直接出柱。
    分组节点的 color/statement 会向下继承到 children（children 可覆盖）。
    """

    name: str
    expr: str | None = None
    statement: str | None = None
    color: str | None = None  # e.g. "#4E79A7"
    unit: str | None = None
    children: list["BarBlock"] | None = None
    transform: str | None = None  # DEPRECATED: legacy ttm|ytd|q|raw（run 模式会忽略）


@dataclass(frozen=True)
class Template:
    """Chart template.

    推荐：一个模板一个 TOML 文件（templates/**/*.toml），由 `finreport_charts run` 执行。
    允许按文件夹分类；文件夹名支持 `english#中文` 形式。
    """

    name: str
    alias: str | None

    # Required
    type: str  # bar|pie|combo|line
    names: list[str] | None = None  # extra lookup names, e.g. ["income_trend", "收入趋势"]

    # Common display fields
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None

    # Price-specific (mode=price)
    frequency: str | None = None  # daily|weekly|monthly|{N}d (e.g. 5d)

    # Generic series-based templates
    mode: str | None = None  # trend|structure|peer|merge (legacy: compare)
    period_end: str | None = None  # for structure/peer
    series: list[BarBlock] | None = None

    # Pie-specific
    section: str | None = None
    items: list[str] | None = None
    top_n: int | None = None

    # Legacy combo compatibility
    bar_item: str | None = None
    transform: str | None = None  # DEPRECATED: legacy transform（run 模式会忽略）
    line: str | None = None

    # Metadata from path
    category: str | None = None
    category_alias: str | None = None
    category_path: str | None = None
    source_path: str | None = None


def _toml_loads():
    try:
        import tomllib  # py>=3.11

        return tomllib.loads
    except Exception:  # py3.10 fallback
        import tomli

        return tomli.loads


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _as_str_list(v: Any) -> list[str] | None:
    if not isinstance(v, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for x in v:
        s = _as_str(x)
        if not s:
            continue
        k = s.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out or None


def _normalize_lookup_name(s: str | None) -> str:
    return str(s or "").strip().lower()


def safe_template_filename_component(text: str, *, allow_cjk: bool = False) -> str:
    s = str(text or "").strip()
    if not s:
        return "item"
    pattern = r"[^0-9A-Za-z_\-]+" if not allow_cjk else r"[^0-9A-Za-z_\-\u4e00-\u9fff]+"
    s = re.sub(pattern, "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def template_filename(name: str, alias: str | None = None) -> str:
    en = safe_template_filename_component(name, allow_cjk=False)
    zh = safe_template_filename_component(alias or "", allow_cjk=True)
    return f"{en}#{zh}.toml" if zh else f"{en}.toml"


def split_named_component(name: str) -> tuple[str, str | None]:
    s = str(name or "").strip()
    if not s:
        return "", None
    if "#" not in s:
        return s, None
    left, right = s.split("#", 1)
    return left.strip(), (right.strip() or None)


def category_lookup_names(category: str | None, alias: str | None, raw_name: str | None = None) -> list[str]:
    vals = [category, alias, raw_name]
    out: list[str] = []
    seen: set[str] = set()
    for s in vals:
        if not s:
            continue
        k = _normalize_lookup_name(s)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(str(s))
    return out


def template_lookup_names(tpl: Template) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in [tpl.name, tpl.alias, *(tpl.names or [])]:
        if not s:
            continue
        k = _normalize_lookup_name(s)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(str(s))
    return out


def _iter_template_files(dir_path: Path) -> list[Path]:
    files = sorted([p for p in dir_path.rglob("*.toml") if p.is_file()], key=lambda p: (p.is_symlink(), str(p)))
    out: list[Path] = []
    seen_real: set[str] = set()
    for p in files:
        try:
            real = str(p.resolve())
        except Exception:
            real = str(p)
        if real in seen_real:
            continue
        seen_real.add(real)
        out.append(p)
    return out


def _template_path_meta(path: Path, root: Path) -> tuple[str | None, str | None, str | None]:
    try:
        rel = path.relative_to(root)
    except Exception:
        return None, None, None
    if len(rel.parts) <= 1:
        return None, None, None
    cat_raw = rel.parts[-2]
    cat_key, cat_alias = split_named_component(cat_raw)
    cat_path = rel.parent.as_posix()
    return cat_key or None, cat_alias, cat_path


def find_template_file(dir_path: Path, spec: str) -> Path | None:
    want = _normalize_lookup_name(spec)
    if not want:
        return None
    want_stem = want[:-5] if want.endswith(".toml") else want
    for p in sorted([x for x in dir_path.rglob("*.toml") if x.is_file()]):
        tpl = load_template_file(p, root=dir_path)
        keys = {_normalize_lookup_name(x) for x in template_lookup_names(tpl)}
        file_stem = _normalize_lookup_name(p.stem)
        file_name = _normalize_lookup_name(p.name)
        rel_name = _normalize_lookup_name(p.relative_to(dir_path).as_posix())
        file_stem_base = file_stem.split("#", 1)[0]
        if want in keys or want_stem in keys:
            return p
        if want in {file_stem, file_name, rel_name} or want_stem in {file_stem, file_stem_base, rel_name}:
            return p
        if not want.endswith(".toml") and f"{want}.toml" == file_name:
            return p
    return None


def _parse_bar_blocks(data: dict[str, Any]) -> list[BarBlock] | None:
    def _parse_one(b: dict[str, Any], *, parent_statement: str | None = None, parent_color: str | None = None) -> BarBlock | None:
        name = _as_str(b.get("name") or b.get("label"))
        expr = _as_str(b.get("expr") or b.get("item"))
        statement = _as_str(b.get("statement")) or parent_statement
        color = _as_str(b.get("color") or b.get("颜色")) or parent_color
        unit = _as_str(b.get("unit") or b.get("单位"))
        transform = _as_str(b.get("transform"))

        # children (nested)
        children_raw = b.get("children")
        children: list[BarBlock] | None = None
        if isinstance(children_raw, list):
            tmp: list[BarBlock] = []
            for c in children_raw:
                if not isinstance(c, dict):
                    continue
                cc = _parse_one(c, parent_statement=statement, parent_color=color)
                if cc:
                    tmp.append(cc)
            children = tmp or None

        # group node
        if not expr and children:
            return BarBlock(name=name or "group", expr=None, statement=statement, color=color, unit=unit, children=children, transform=transform)

        # leaf node
        if not expr:
            return None

        return BarBlock(
            name=name or expr,
            expr=expr,
            statement=statement,
            color=color,
            unit=unit,
            children=children,
            transform=transform,
        )

    # New style: [[series]] (preferred) or [[bars]] (legacy compatibility)
    blocks = data.get("series") if isinstance(data.get("series"), list) else data.get("bars")
    if isinstance(blocks, list):
        out: list[BarBlock] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bb = _parse_one(b)
            if bb:
                out.append(bb)
        return out or None

    # Legacy style: item + optional alias
    item = _as_str(data.get("item"))
    if item:
        return [BarBlock(name=item, expr=item, statement=_as_str(data.get("statement")), transform=_as_str(data.get("transform")))]

    return None


def _resolve_template_link_path(path: Path) -> Path:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return path
    if ('=' in text) or ('[[' in text) or text.startswith('name') or text.startswith('type'):
        return path
    target = (path.parent / text).resolve()
    return target if target.exists() else path


def _canonical_template_source(path: Path) -> Path:
    if path.is_symlink():
        try:
            return path.resolve()
        except Exception:
            return path
    try:
        return _resolve_template_link_path(path).resolve()
    except Exception:
        return path.resolve() if path.exists() else path


def load_template_file(path: Path, *, root: Path | None = None) -> Template:
    """Load a single-template TOML file.

    支持格式：
    - 顶层键（推荐）：type/title/x_label/y_label/mode/[[series]]...
    - 或 [template] 表

    name 默认取文件名 stem，也可在 TOML 里显式指定 name。
    """

    source = path
    if (not path.is_symlink()) and path.suffix.lower() == '.toml':
        try:
            source = _resolve_template_link_path(path)
        except Exception:
            source = path

    loads = _toml_loads()
    cfg = loads(source.read_text(encoding="utf-8"))

    v = cfg.get("template") if isinstance(cfg, dict) else None
    data: dict[str, Any]
    if isinstance(v, dict):
        data = v
    else:
        data = cfg if isinstance(cfg, dict) else {}

    name = str(data.get("name") or source.stem)
    alias = _as_str(data.get("alias"))
    names = _as_str_list(data.get("names") or data.get("template_names") or data.get("aliases"))

    type_ = _as_str(data.get("type") or data.get("chart"))
    if not type_:
        raise ValueError(f"template 缺少 type/chart 字段: {path}")

    cat_key, cat_alias, cat_path = _template_path_meta(path, root or path.parent)
    source_path_str = None
    try:
        source_path_str = path.relative_to(root).as_posix() if root else path.name
    except Exception:
        source_path_str = path.name

    return Template(
        name=name,
        alias=alias,
        type=type_,
        names=names,
        title=_as_str(data.get("title")),
        x_label=_as_str(data.get("x_label")),
        y_label=_as_str(data.get("y_label")),
        frequency=_as_str(data.get("frequency")),
        mode=_as_str(data.get("mode")),
        period_end=_as_str(data.get("period_end")),
        series=_parse_bar_blocks(data),
        section=_as_str(data.get("section")),
        items=data.get("items") if isinstance(data.get("items"), list) else None,
        top_n=data.get("top_n"),
        bar_item=_as_str(data.get("bar_item")),
        transform=_as_str(data.get("transform")),
        line=_as_str(data.get("line")),
        category=cat_key,
        category_alias=cat_alias,
        category_path=cat_path,
        source_path=source_path_str,
    )


def load_template_dir(dir_path: Path) -> dict[str, Template]:
    """Load all *.toml templates under a directory recursively."""

    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"模板目录不存在: {dir_path}")

    out: dict[str, Template] = {}
    seen_canonical: dict[str, str] = {}
    for p in _iter_template_files(dir_path):
        can = str(_canonical_template_source(p))
        if can in seen_canonical:
            continue
        tpl = load_template_file(p, root=dir_path)
        if tpl.name in out:
            prev = out[tpl.name]
            raise ValueError(f"模板 name 重复: {tpl.name} ({prev.source_path} / {tpl.source_path})")
        out[tpl.name] = tpl
        seen_canonical[can] = tpl.name
    return out


def list_template_categories(dir_path: Path) -> list[dict[str, str]]:
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"模板目录不存在: {dir_path}")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for p in _iter_template_files(dir_path):
        cat_key, cat_alias, cat_path = _template_path_meta(p, dir_path)
        if not cat_key or not cat_path or cat_path in seen:
            continue
        seen.add(cat_path)
        out.append({"key": cat_key, "alias": cat_alias or cat_key, "path": cat_path, "raw": Path(cat_path).name})
    out.sort(key=lambda x: (x["path"], x["alias"]))
    return out
