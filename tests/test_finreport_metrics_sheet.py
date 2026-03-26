from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from finreport_fetcher.exporter.excel import export_bundle_to_excel
from finreport_fetcher.metrics_sheet import build_metrics_sheet


def test_build_metrics_sheet_and_export(tmp_path: Path):
    metrics_df = pd.DataFrame(
        [
            {
                "end_date": "20241231",
                "ann_date": "20250328",
                "roe": 22.5,
                "roa": 17.2,
                "roic": 18.6,
                "ev": 1234.0,
                "ebitda": 234.5,
            }
        ]
    )
    sheet = build_metrics_sheet(metrics_df, date(2024, 12, 31))
    assert not sheet.empty
    assert "metrics.roe" in sheet["key"].astype(str).tolist()

    bs = pd.DataFrame({"科目": ["资产总计"], "数值": [100.0], "__level": [0], "__is_header": [False]})
    is_ = pd.DataFrame({"科目": ["营业总收入"], "数值": [50.0], "__level": [0], "__is_header": [False]})
    cf = pd.DataFrame({"科目": ["经营活动产生的现金流量净额"], "数值": [20.0], "__level": [0], "__is_header": [False]})
    out = tmp_path / "demo.xlsx"
    export_bundle_to_excel(
        out,
        balance_sheet=bs,
        income_statement=is_,
        cashflow_statement=cf,
        metrics_statement=sheet,
        meta={},
        title_info={"code6": "600519", "period_end": "2024-12-31", "provider": "akshare", "metrics_provider": "akshare"},
    )
    wb = load_workbook(out)
    assert "财报指标" in wb.sheetnames
    ws = wb["财报指标"]
    headers = [ws.cell(3, c).value for c in range(1, ws.max_column + 1)]
    assert headers == ["科目", "数值", " ", "key", "备注", "英文"]
    keys = [ws.cell(r, 4).value for r in range(4, ws.max_row + 1) if ws.cell(r, 4).value]
    assert "metrics.roe" in keys
    wb.close()
