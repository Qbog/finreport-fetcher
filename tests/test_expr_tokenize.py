from __future__ import annotations

from finreport_charts.utils.expr import tokenize


def test_tokenize_supports_chinese_identifiers_in_global_series():
    assert tokenize("commodity.黄金.close") == ["commodity.黄金.close"]
    assert tokenize("idx.sh000001.close / commodity.黄金.close") == [
        "idx.sh000001.close",
        "/",
        "commodity.黄金.close",
    ]
