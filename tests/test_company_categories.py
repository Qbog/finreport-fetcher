from __future__ import annotations

from pathlib import Path

import pandas as pd

from finshared.company_categories import resolve_company_category_symbols


def test_category_supports_name_or_code_and_warns_once_for_missing(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "company_categories.toml"
    cfg.write_text(
        """
[categories.gold_watch]
alias = "黄金观察"
items = [
  { name = "山东黄金" },
  { code = "600489" },
  { name = "不存在公司" },
  "中金黄金",
]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "finshared.company_categories.load_a_share_name_map",
        lambda: pd.DataFrame(
            [
                {"code": "600547", "name": "山东黄金"},
                {"code": "600489", "name": "中金黄金"},
            ]
        ),
    )

    resolved = resolve_company_category_symbols("gold_watch", cfg)
    assert [x.code6 for x in resolved.symbols] == ["600547", "600489"]
    assert len(resolved.warnings) == 1
    assert "不存在公司" in resolved.warnings[0]
