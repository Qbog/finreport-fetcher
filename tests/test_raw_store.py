from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from finreport_fetcher.raw_store import RawReportStore
from finreport_charts.data.finreport_store import expected_pdf_path


def test_raw_store_save_load_and_update_provider_table(tmp_path: Path):
    store = RawReportStore(tmp_path / "贵州茅台_600519")

    df0 = pd.DataFrame(
        [
            {"ts_code": "600519.SH", "end_date": "20241231", "comp_type": 1, "revenue": 100.0},
        ]
    )
    store.save_provider_table("tushare", "is", df0)

    loaded = store.load_provider_table("tushare", "is")
    assert loaded is not None
    assert loaded.shape == (1, 4)
    assert float(loaded.iloc[0]["revenue"]) == 100.0

    df1 = pd.DataFrame(
        [
            {"ts_code": "600519.SH", "end_date": "20241231", "comp_type": 1, "revenue": 101.0},
            {"ts_code": "600519.SH", "end_date": "20240930", "comp_type": 1, "revenue": 88.0},
        ]
    )
    store.update_provider_table(
        "tushare",
        "is",
        df1,
        subset=["ts_code", "end_date", "comp_type"],
    )

    updated = store.load_provider_table("tushare", "is")
    assert updated is not None
    assert len(updated) == 2

    updated = updated.sort_values("end_date").reset_index(drop=True)
    assert updated["end_date"].tolist() == ["20240930", "20241231"]
    assert float(updated.iloc[1]["revenue"]) == 101.0


def test_raw_store_pdf_metadata_and_expected_pdf_path_prefers_raw_dir(tmp_path: Path):
    company_root = tmp_path / "贵州茅台_600519"
    store = RawReportStore(company_root)
    period_end = date(2024, 12, 31)

    pdf_path = store.pdf_path("600519", period_end)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")

    store.save_pdf_metadata(
        "600519",
        period_end,
        {
            "ok": True,
            "url": "https://example.com/report.pdf",
            "title": "2024年年度报告",
            "note": None,
        },
    )

    meta = store.load_pdf_metadata("600519", period_end)
    assert meta is not None
    assert meta["ok"] is True
    assert meta["title"] == "2024年年度报告"

    resolved = expected_pdf_path(tmp_path, "600519", period_end, name="贵州茅台")
    assert resolved == pdf_path
    assert resolved.exists()
