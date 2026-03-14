from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BarBlock:
    name: str
    expr: str
    statement: str | None = None
    transform: str | None = None  # ttm|ytd|q|raw


@dataclass(frozen=True)
class Template:
    """Chart template.

    推荐：一个模板一个 TOML 文件（templates/*.toml），由 `finreport_charts run` 执行。

    兼容：旧的 charts.toml（[templates.xxx]）仍可被 load_templates() 读取。
    """

    name: str
    alias: str | None

    # Required
    type: str  # bar|pie|combo|line

    # Common display fields
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None

    # Bar-specific
    mode: str | None = None  # trend|compare
    statement: str | None = None
    period_end: str | None = None  # for compare
    bars: list[BarBlock] | None = None

    # Pie-specific
    section: str | None = None
    items: list[str] | None = None
    top_n: int | None = None

    # Combo-specific
    bar_item: str | None = None
    transform: str | None = None
    line: str | None = None


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


def _parse_bar_blocks(data: dict[str, Any]) -> list[BarBlock] | None:
    # New style: [[bars]]
    bars = data.get("bars")
    if isinstance(bars, list):
        out: list[BarBlock] = []
        for b in bars:
            if not isinstance(b, dict):
                continue
            name = _as_str(b.get("name") or b.get("label"))
            expr = _as_str(b.get("expr") or b.get("item"))
            if not expr:
                continue
            out.append(
                BarBlock(
                    name=name or expr,
                    expr=expr,
                    statement=_as_str(b.get("statement")),
                    transform=_as_str(b.get("transform")),
                )
            )
        return out

    # Legacy style: item + optional alias
    item = _as_str(data.get("item"))
    if item:
        return [BarBlock(name=item, expr=item, statement=_as_str(data.get("statement")), transform=_as_str(data.get("transform")))]

    return None


def load_templates(path: Path) -> dict[str, Template]:
    """Legacy loader for charts.toml (single file with [templates.*])."""

    loads = _toml_loads()
    cfg = loads(path.read_text(encoding="utf-8"))
    troot = cfg.get("templates") or {}
    out: dict[str, Template] = {}
    for name, v in troot.items():
        if not isinstance(v, dict):
            continue
        # legacy chart -> type
        type_ = _as_str(v.get("type") or v.get("chart"))
        if not type_:
            continue

        out[name] = Template(
            name=name,
            alias=_as_str(v.get("alias")),
            type=type_,
            title=_as_str(v.get("title")),
            x_label=_as_str(v.get("x_label")),
            y_label=_as_str(v.get("y_label")),
            mode=_as_str(v.get("mode")),
            statement=_as_str(v.get("statement")),
            period_end=_as_str(v.get("period_end")),
            bars=_parse_bar_blocks(v),
            section=_as_str(v.get("section")),
            items=v.get("items") if isinstance(v.get("items"), list) else None,
            top_n=v.get("top_n"),
            bar_item=_as_str(v.get("bar_item")),
            transform=_as_str(v.get("transform")),
            line=_as_str(v.get("line")),
        )
    return out


def load_template_file(path: Path) -> Template:
    """Load a single-template TOML file.

    支持格式：
    - 顶层键（推荐）：type/title/x_label/y_label/mode/[[bars]]...
    - 或 [template] 表

    name 默认取文件名 stem，也可在 TOML 里显式指定 name。
    """

    loads = _toml_loads()
    cfg = loads(path.read_text(encoding="utf-8"))

    v = cfg.get("template") if isinstance(cfg, dict) else None
    data: dict[str, Any]
    if isinstance(v, dict):
        data = v
    else:
        data = cfg if isinstance(cfg, dict) else {}

    name = str(data.get("name") or path.stem)
    alias = _as_str(data.get("alias"))

    type_ = _as_str(data.get("type") or data.get("chart"))
    if not type_:
        raise ValueError(f"template 缺少 type/chart 字段: {path}")

    return Template(
        name=name,
        alias=alias,
        type=type_,
        title=_as_str(data.get("title")),
        x_label=_as_str(data.get("x_label")),
        y_label=_as_str(data.get("y_label")),
        mode=_as_str(data.get("mode")),
        statement=_as_str(data.get("statement")),
        period_end=_as_str(data.get("period_end")),
        bars=_parse_bar_blocks(data),
        section=_as_str(data.get("section")),
        items=data.get("items") if isinstance(data.get("items"), list) else None,
        top_n=data.get("top_n"),
        bar_item=_as_str(data.get("bar_item")),
        transform=_as_str(data.get("transform")),
        line=_as_str(data.get("line")),
    )


def load_template_dir(dir_path: Path) -> dict[str, Template]:
    """Load all *.toml templates under a directory."""

    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"模板目录不存在: {dir_path}")

    out: dict[str, Template] = {}
    for p in sorted(dir_path.glob("*.toml")):
        tpl = load_template_file(p)
        out[tpl.name] = tpl
    return out
