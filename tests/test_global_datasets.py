from __future__ import annotations

from pathlib import Path

import pandas as pd

from finreport_fetcher.global_datasets import (
    CompanyBasicsProvider,
    FinancialMetricsProvider,
    fetch_company_basics_dataset,
    fetch_financial_metrics_dataset,
    load_company_basics_csv,
    load_financial_metrics_csv,
)


class FakeBasicsProvider(CompanyBasicsProvider):
    def fetch(self, tushare_token=None):
        return "fake", pd.DataFrame([
            {"symbol": "600519", "name": "贵州茅台", "industry": "白酒", "list_date": "20010827"},
            {"symbol": "300454", "name": "深信服", "industry": "网络安全", "list_date": "20180516"},
        ])


class FakeMetricsProvider(FinancialMetricsProvider):
    def fetch_company_list(self, tushare_token=None):
        return pd.DataFrame([
            {"ts_code": "600519.SH", "code6": "600519", "name": "贵州茅台"},
            {"ts_code": "300454.SZ", "code6": "300454", "name": "深信服"},
        ])

    def fetch_company_metrics(self, ts_code: str, tushare_token=None):
        return pd.DataFrame([
            {"ts_code": ts_code, "ann_date": "20250328", "end_date": "20241231", "roe": 22.5, "roa": 17.2, "roic": 18.6, "ev": None, "ebitda": 123.4},
        ])


def test_fetch_company_basics_dataset(tmp_path: Path):
    paths = fetch_company_basics_dataset(data_dir=tmp_path, provider=FakeBasicsProvider())
    assert paths.csv_path.exists()
    df = load_company_basics_csv(tmp_path)
    assert sorted([str(x).zfill(6) for x in df["code6"]]) == ["300454", "600519"]


def test_fetch_financial_metrics_dataset(tmp_path: Path):
    paths = fetch_financial_metrics_dataset(data_dir=tmp_path, provider=FakeMetricsProvider())
    assert paths.csv_path.exists()
    df = load_financial_metrics_csv(tmp_path)
    assert list(df.columns) == ["ts_code", "code6", "name", "end_date", "ann_date", "roe", "roa", "roic", "ev", "ebitda"]
    assert len(df.index) == 2
    assert (paths.raw_dir / "600519.csv").exists()
