from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CategoryReportTemplate:
    category: str
    balance_sheet_keys: list[str]
    income_statement_keys: list[str]
    cashflow_statement_keys: list[str]
    source_path: str | None = None


def _project_root() -> Path:
    # finreport_fetcher/mappings/category_report_templates.py -> finreport_fetcher/mappings -> finreport_fetcher -> project root
    return Path(__file__).resolve().parents[2]


def load_category_report_template(category: str) -> CategoryReportTemplate | None:
    """Load fixed report template for a category.

    Template files are stored in repo-level `report_templates/{category}.toml`.

    Returns None if template file is missing.
    """

    cat = (category or "").strip() or "non_financial"

    root = _project_root()
    path = root / "report_templates" / f"{cat}.toml"
    if not path.exists():
        # fallback to non_financial if category-specific not found
        path2 = root / "report_templates" / "non_financial.toml"
        if not path2.exists():
            return None
        path = path2
        cat = "non_financial"

    try:
        import tomllib  # py>=3.11
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore

    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))

    def _keys(section: str) -> list[str]:
        sec = data.get(section) or {}
        keys = sec.get("keys") or []
        return [str(x) for x in keys if str(x).strip()]

    return CategoryReportTemplate(
        category=str(data.get("category") or cat),
        balance_sheet_keys=_keys("balance_sheet"),
        income_statement_keys=_keys("income_statement"),
        cashflow_statement_keys=_keys("cashflow_statement"),
        source_path=str(path),
    )
