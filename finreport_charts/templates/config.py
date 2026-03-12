from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Template:
    name: str
    alias: str | None
    chart: str  # bar|pie|combo
    statement: str | None = None
    item: str | None = None
    section: str | None = None
    items: list[str] | None = None
    transform: str | None = None  # ttm|raw
    top_n: int | None = None
    bar_item: str | None = None
    line: str | None = None  # price.close etc.


def load_templates(path: Path) -> dict[str, Template]:
    try:
        import tomllib  # py>=3.11

        loads = tomllib.loads
    except Exception:  # py3.10 fallback
        import tomli

        loads = tomli.loads

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
