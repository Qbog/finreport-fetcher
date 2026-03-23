from __future__ import annotations

from datetime import date
from pathlib import Path

from finreport_fetcher.providers.tushare_provider import TushareProvider
from finreport_fetcher.raw_store import RawReportStore


class _FakePro:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def balancesheet(self, **kwargs):
        self.calls.append(("balancesheet", dict(kwargs)))
        return [
            {"ts_code": "600519.SH", "end_date": "20241231", "comp_type": 1, "money_cap": 10.0},
            {"ts_code": "600519.SH", "end_date": "20240930", "comp_type": 1, "money_cap": 9.0},
        ]

    def income(self, **kwargs):
        self.calls.append(("income", dict(kwargs)))
        return [
            {"ts_code": "600519.SH", "end_date": "20241231", "comp_type": 1, "revenue": 100.0},
            {"ts_code": "600519.SH", "end_date": "20240930", "comp_type": 1, "revenue": 80.0},
        ]

    def cashflow(self, **kwargs):
        self.calls.append(("cashflow", dict(kwargs)))
        return [
            {"ts_code": "600519.SH", "end_date": "20241231", "comp_type": 1, "n_cashflow_act": 50.0},
            {"ts_code": "600519.SH", "end_date": "20240930", "comp_type": 1, "n_cashflow_act": 40.0},
        ]


def test_tushare_raw_store_fetches_full_history_and_reuses_cache(tmp_path: Path, monkeypatch):
    provider = TushareProvider(token="dummy")
    fake = _FakePro()
    monkeypatch.setattr(provider, "_pro", lambda: fake)

    store = RawReportStore(tmp_path / "贵州茅台_600519")

    bundle_2024q4 = provider.get_bundle(
        ts_code="600519.SH",
        period_end=date(2024, 12, 31),
        statement_type="merged",
        raw_store=store,
    )

    assert bundle_2024q4.meta["raw_scope"] == "full_history"
    assert not bundle_2024q4.balance_sheet.empty
    assert not bundle_2024q4.income_statement.empty
    assert not bundle_2024q4.cashflow_statement.empty

    # raw_store 下应保存整家公司多期历史，而不是单期切片。
    bs_raw = store.load_provider_table("tushare", "bs")
    inc_raw = store.load_provider_table("tushare", "is")
    cf_raw = store.load_provider_table("tushare", "cf")
    assert bs_raw is not None and sorted(bs_raw["end_date"].astype(str).tolist()) == ["20240930", "20241231"]
    assert inc_raw is not None and sorted(inc_raw["end_date"].astype(str).tolist()) == ["20240930", "20241231"]
    assert cf_raw is not None and sorted(cf_raw["end_date"].astype(str).tolist()) == ["20240930", "20241231"]

    # 全历史抓取不应带 end_date；否则只会缓存单一期末。
    assert len(fake.calls) == 3
    for _api, kwargs in fake.calls:
        assert kwargs["ts_code"] == "600519.SH"
        assert kwargs["comp_type"] == 1
        assert "end_date" not in kwargs

    # 第二次请求另一报告期应直接命中缓存，不再触发 API。
    bundle_2024q3 = provider.get_bundle(
        ts_code="600519.SH",
        period_end=date(2024, 9, 30),
        statement_type="merged",
        raw_store=store,
    )
    assert bundle_2024q3.meta["raw_scope"] == "full_history"
    assert len(fake.calls) == 3
