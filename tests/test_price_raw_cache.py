from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from finprice_fetcher.cli import CommonOpts, _ensure_raw_daily_price
from finprice_fetcher.raw_store import RawPriceStore
from finshared.symbols import ResolvedSymbol


def _sample_daily_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100, "amount": 1050},
            {"date": "2024-01-03", "open": 10.6, "high": 11.2, "low": 10.1, "close": 11.0, "volume": 120, "amount": 1320},
            {"date": "2025-01-02", "open": 20.0, "high": 21.0, "low": 19.5, "close": 20.8, "volume": 200, "amount": 4160},
        ]
    )


def test_price_raw_cache_fetches_full_history_once_and_reuses_cache(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def _fake_fetch(code6: str) -> pd.DataFrame:
        calls.append(code6)
        return _sample_daily_df()

    monkeypatch.setattr("finprice_fetcher.cli._fetch_full_history_akshare", _fake_fetch)

    opts = CommonOpts(
        rs=ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"),
        start=date(2024, 1, 1),
        end=date(2025, 1, 2),
        out_dir=tmp_path,
        provider="akshare",
        frequency="daily",
        tushare_token=None,
    )
    company_root = tmp_path / "贵州茅台_600519"

    raw1, src1 = _ensure_raw_daily_price(opts, company_root)
    assert src1 == "akshare"
    assert calls == ["600519"]
    assert raw1["date"].tolist() == ["2024-01-02", "2024-01-03", "2025-01-02"]

    store = RawPriceStore(company_root)
    cached = store.load_daily_prices("akshare")
    assert cached is not None
    assert cached["date"].tolist() == ["2024-01-02", "2024-01-03", "2025-01-02"]

    raw2, src2 = _ensure_raw_daily_price(opts, company_root)
    assert src2 == "akshare"
    assert calls == ["600519"]
    assert raw2["date"].tolist() == raw1["date"].tolist()


def test_price_raw_cache_auto_mode_prefers_existing_cache(tmp_path: Path, monkeypatch):
    company_root = tmp_path / "贵州茅台_600519"
    store = RawPriceStore(company_root)
    store.save_daily_prices("akshare", _sample_daily_df(), metadata={"scope": "full_history_daily"})

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not hit remote fetch when raw cache already exists")

    monkeypatch.setattr("finprice_fetcher.cli._fetch_full_history_akshare", _boom)
    monkeypatch.setattr("finprice_fetcher.cli._fetch_full_history_tushare", _boom)

    opts = CommonOpts(
        rs=ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"),
        start=date(2024, 1, 1),
        end=date(2025, 1, 2),
        out_dir=tmp_path,
        provider="auto",
        frequency="weekly",
        tushare_token="dummy-token",
    )

    raw, src = _ensure_raw_daily_price(opts, company_root)
    assert src == "akshare"
    assert raw["date"].tolist() == ["2024-01-02", "2024-01-03", "2025-01-02"]
