from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from finprice_fetcher.cli import CommonOpts, _update_raw_daily_price
from finshared.symbols import ResolvedSymbol


def test_price_raw_update_appends_only_missing_tail(tmp_path: Path, monkeypatch):
    calls: list[tuple[date, date]] = []

    def _fake_full(code6: str) -> pd.DataFrame:
        raise AssertionError("should not refetch full history when cache already exists")

    def _fake_inc(code6: str, start: date, end: date, frequency: str) -> pd.DataFrame:
        calls.append((start, end))
        return pd.DataFrame([
            {"date": start.strftime("%Y-%m-%d"), "open": 3.0, "high": 3.2, "low": 2.9, "close": 3.1, "volume": 300, "amount": 930},
        ])

    monkeypatch.setattr("finprice_fetcher.cli._fetch_full_history_akshare", _fake_full)
    monkeypatch.setattr("finprice_fetcher.cli._fetch_price_akshare", _fake_inc)
    monkeypatch.setattr("finprice_fetcher.cli.date", type("_D", (), {"today": staticmethod(lambda: date(2025, 1, 3))}))

    company_root = tmp_path / "贵州茅台_600519"
    from finprice_fetcher.raw_store import RawPriceStore

    store = RawPriceStore(company_root)
    store.save_daily_prices(
        "akshare",
        pd.DataFrame([
            {"date": "2025-01-01", "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "volume": 100, "amount": 110},
            {"date": "2025-01-02", "open": 2.0, "high": 2.2, "low": 1.9, "close": 2.1, "volume": 200, "amount": 420},
        ]),
        metadata={"scope": "full_history_daily"},
    )

    opts = CommonOpts(
        rs=ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"),
        start=date(2025, 1, 1),
        end=date(2025, 1, 3),
        out_dir=tmp_path,
        provider="akshare",
        frequency="daily",
        tushare_token=None,
    )

    df, provider = _update_raw_daily_price(opts, company_root)
    assert provider == "akshare"
    assert calls == [(date(2025, 1, 3), date(2025, 1, 3))]
    assert df["date"].tolist() == ["2025-01-01", "2025-01-02", "2025-01-03"]
