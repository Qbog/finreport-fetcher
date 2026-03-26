from __future__ import annotations

from pathlib import Path

import pandas as pd

from finreport_fetcher.cli import fetch
from finreport_fetcher.utils.symbols import ResolvedSymbol


class _DummyProvider:
    name = "dummy"

    def refresh_raw_history(self, ts_code: str, statement_type: str, raw_store):
        return "report-snapshot-1"


def test_finreport_update_raw_also_updates_metrics_raw(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("finreport_fetcher.cli._resolve_symbol", lambda code=None, name=None: ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"))
    monkeypatch.setattr("finreport_fetcher.cli.build_providers", lambda cfg: [_DummyProvider()])

    def _fake_update_metrics(c, store):
        calls.append((c.provider, str(store.company_root)))
        return "akshare", pd.DataFrame(), "metrics-snapshot-1"

    monkeypatch.setattr("finreport_fetcher.cli.update_raw_metrics", _fake_update_metrics)

    fetch(
        code="600519",
        name=None,
        category=None,
        category_config=None,
        date_=None,
        start=None,
        end=None,
        provider="auto",
        statement_type="merged",
        pdf=False,
        out_dir=tmp_path,
        no_clean=False,
        update_raw=True,
        clear_raw=False,
        tushare_token=None,
    )

    assert calls and calls[0][0] == "auto"
    assert calls[0][1].endswith("贵州茅台_600519")


def test_finreport_clear_raw_also_clears_metrics_raw(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr("finreport_fetcher.cli._resolve_symbol", lambda code=None, name=None: ResolvedSymbol(code6="600519", ts_code="600519.SH", market="SH", name="贵州茅台"))
    monkeypatch.setattr("finreport_fetcher.cli.build_providers", lambda cfg: [_DummyProvider()])
    monkeypatch.setattr("finreport_fetcher.cli.clear_raw_metrics", lambda store: calls.append(str(store.company_root)))

    fetch(
        code="600519",
        name=None,
        category=None,
        category_config=None,
        date_=None,
        start=None,
        end=None,
        provider="auto",
        statement_type="merged",
        pdf=False,
        out_dir=tmp_path,
        no_clean=False,
        update_raw=False,
        clear_raw=True,
        tushare_token=None,
    )

    assert calls and calls[0].endswith("贵州茅台_600519")
