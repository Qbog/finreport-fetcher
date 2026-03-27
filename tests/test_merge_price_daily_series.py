from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from finreport_charts.cli import CommonOpts, _build_price_expr_daily_df
from finshared.symbols import ResolvedSymbol


class _DummyEval:
    def eval(self, expr: str, *, current_pe: date, default_statement: str):
        raise AssertionError(f"unexpected quarterly eval: {expr} @ {current_pe} / {default_statement}")

    def _global_series_value_on_or_before(self, kind: str, symbol: str, when: date, field: str):
        raise AssertionError(f"unexpected global series lookup: {kind}.{symbol}.{field} @ {when}")


def test_build_price_expr_daily_df_keeps_all_trading_dates(tmp_path: Path, monkeypatch):
    price_csv = tmp_path / "600519.csv"
    pd.DataFrame(
        [
            {"date": "2025-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.1, "volume": 100},
            {"date": "2025-01-03", "open": 10.2, "high": 10.8, "low": 10.0, "close": 10.6, "volume": 120},
            {"date": "2025-01-06", "open": 10.7, "high": 11.0, "low": 10.5, "close": 10.9, "volume": 140},
        ]
    ).to_csv(price_csv, index=False)

    monkeypatch.setattr("finreport_charts.cli._maybe_fetch_price_missing", lambda *args, **kwargs: price_csv)

    opts = CommonOpts(
        rs=ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"),
        start=date(2025, 1, 1),
        end=date(2025, 1, 6),
        data_dir=tmp_path,
        out_dir=tmp_path / "charts",
        provider="auto",
        statement_type="merged",
        pdf=False,
        tushare_token=None,
    )

    df = _build_price_expr_daily_df(
        opts,
        _DummyEval(),
        expr="px.close",
        default_statement="资产负债表",
        base_frequency="daily",
    )

    assert df["date"].tolist() == [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
    assert df["value"].tolist() == [10.1, 10.6, 10.9]
