from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Template:
    """Chart template.

    支持两种加载方式：
    1) 单文件多模板（legacy）：charts.toml 里 [templates.xxx]
    2) 单模板单文件（推荐）：templates/*.toml
    """

    name: str
    alias: str | None
    chart: str  # bar|pie|combo
    statement: str | None = None
    item: str | None = None
    section: str | None = None
    items: list[str] | None = None
    transform: str | None = None  # ttm|ytd|q|raw
    top_n: int | None = None
    bar_item: str | None = None
    line: str | None = None  # price.close etc.


def _toml_loads():
    try:
        import tomllib  # py>=3.11

        return tomllib.loads
    except Exception:  # py3.10 fallback
        import tomli

        return tomli.loads


def load_templates(path: Path) -> dict[str, Template]:
    """Legacy loader for charts.toml (single file with [templates.*])."""

    loads = _toml_loads()
    cfg = loads(path.read_text(encoding="utf-8"))
    troot = cfg.get("templates") or {}
    out: dict[str, Template] = {}
    for name, v in troot.items():
        if not isinstance(v, dict):
            continue
        out[name] = Template(
            name=name,
            alias=v.get("alias"),
            chart=v.get("chart"),
            statement=v.get("statement"),
            item=v.get("item"),
            section=v.get("section"),
            items=v.get("items"),
            transform=v.get("transform"),
            top_n=v.get("top_n"),
            bar_item=v.get("bar_item"),
            line=v.get("line"),
        )
    return out


def load_template_file(path: Path) -> Template:
    """Load a single-template TOML file.

    支持格式：
    - 顶层键：chart/statement/item/transform/...（推荐）
    - 或 [template] 表

    name 默认取文件名 stem，也可在 TOML 里显式指定 name。
    """

    loads = _toml_loads()
    cfg = loads(path.read_text(encoding="utf-8"))

    v = cfg.get("template") if isinstance(cfg, dict) else None
    if isinstance(v, dict):
        data = v
    else:
        data = cfg if isinstance(cfg, dict) else {}

    name = str(data.get("name") or path.stem)
    chart = data.get("chart")
    if not chart:
        raise ValueError(f"template 缺少 chart 字段: {path}")

    return Template(
        name=name,
        alias=data.get("alias"),
        chart=str(chart),
        statement=data.get("statement"),
        item=data.get("item"),
        section=data.get("section"),
        items=data.get("items"),
        transform=data.get("transform"),
        top_n=data.get("top_n"),
        bar_item=data.get("bar_item"),
        line=data.get("line"),
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
