from __future__ import annotations

from datetime import date

from finindex_fetcher.cli import _fetch_index_tx_range


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def test_fetch_index_tx_range_parses_json_without_demjson(monkeypatch):
    sample = 'kline_dayqfq={"code":0,"msg":"","data":{"sh000001":{"day":[["2024-01-02","10","11","12","9","100"]]}}}'

    class _Req:
        @staticmethod
        def get(url, params=None, timeout=None, headers=None):
            return _Resp(sample)

    monkeypatch.setitem(__import__('sys').modules, 'requests', _Req)
    df = _fetch_index_tx_range('sh000001', date(2024, 1, 2), date(2024, 1, 2))
    assert df.iloc[0]['date'] == '2024-01-02'
    assert float(df.iloc[0]['close']) == 11.0
