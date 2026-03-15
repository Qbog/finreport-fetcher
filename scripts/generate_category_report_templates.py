#!/usr/bin/env python3
"""Generate fixed financial-statement subject templates by company category.

Why
- User wants A-share companies split into 4 categories:
  - non_financial / bank / securities / insurance
- Each category should have a *fixed* statement format (canonical subject list)
- Within a category, any non-common subjects should still be highlighted (handled by SubjectSpec.common_in/common/note)

What this script does
- It generates a TOML file per category under `report_templates/`.
- Each template contains the *common* subject keys for BS/IS/CF in a stable order,
  derived from the curated `SubjectSpec` list.

Notes
- This script does NOT fetch any online data.
- Templates are deterministic and diff-friendly.

Usage
  python3 scripts/generate_category_report_templates.py
  python3 scripts/generate_category_report_templates.py --out-dir report_templates
"""

from __future__ import annotations

import argparse
from pathlib import Path

from finreport_fetcher.mappings.subject_glossary import SUBJECT_SPECS
from finreport_fetcher.utils.company_category import ALL_CATEGORIES


def _is_common_in_category(spec, category: str) -> bool:
    common_in = tuple(getattr(spec, "common_in", ()) or ())
    if common_in:
        return category in common_in
    return bool(getattr(spec, "common", True))


def _iter_keys(prefix: str, category: str) -> list[str]:
    keys: list[str] = []
    for spec in SUBJECT_SPECS:
        k = str(spec.key)
        if not k.startswith(prefix + "."):
            continue
        if _is_common_in_category(spec, category):
            keys.append(k)
    return keys


def _to_toml_list(keys: list[str], *, indent: str = "") -> str:
    if not keys:
        return indent + "keys = []\n"
    lines = [indent + "keys = [\n"]
    for k in keys:
        lines.append(f"{indent}  \"{k}\",\n")
    lines.append(indent + "]\n")
    return "".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="report_templates", help="output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for cat in ALL_CATEGORIES:
        bs = _iter_keys("bs", cat)
        is_ = _iter_keys("is", cat)
        cf = _iter_keys("cf", cat)

        content = []
        content.append(f"# 自动生成：{cat} 类别的固定财报科目模板（common keys）\n")
        content.append("# - 由 subject_glossary.SubjectSpec(common/common_in) 推导\n")
        content.append("# - 仅包含‘通用’科目；其余科目在导出时将被视为非通用并高亮/备注\n\n")
        content.append(f"category = \"{cat}\"\n")
        content.append("version = 1\n\n")

        content.append("[balance_sheet]\n")
        content.append(_to_toml_list(bs))
        content.append("\n[income_statement]\n")
        content.append(_to_toml_list(is_))
        content.append("\n[cashflow_statement]\n")
        content.append(_to_toml_list(cf))

        out_path = out_dir / f"{cat}.toml"
        out_path.write_text("".join(content), encoding="utf-8")
        print(f"written: {out_path}")


if __name__ == "__main__":
    main()
