import pandas as pd

from finreport_fetcher.mappings.enrich import enrich_statement_df


def test_balance_sheet_inserts_core_metrics_header_and_equity_header():
    df = pd.DataFrame(
        {
            "科目": [
                "所有者权益（或股东权益）合计",
                "资产合计",
                "负债合计",
                "归属于母公司所有者权益合计",
                "流动资产",
                "货币资金",
                "非流动负债合计",
                "实收资本（或股本）",
                "资本公积",
            ],
            "数值": [100.0, 300.0, 200.0, 100.0, None, 10.0, 50.0, 1.0, 2.0],
            "__level": [0, 0, 0, 0, 0, 1, 1, 1, 1],
            "__is_header": [False, False, False, False, True, False, False, False, False],
        }
    )

    out = enrich_statement_df(df, sheet_name_cn="资产负债表")

    # core header inserted
    assert out.iloc[0]["科目"] == "报表核心指标"
    assert bool(out.iloc[0]["__is_header"]) is True

    # the 4 core lines are indented under the header
    for i in range(1, 5):
        assert int(out.iloc[i]["__level"]) >= 1

    # equity header inserted before the first equity marker (实收资本)
    equity_rows = out[out["科目"].astype(str) == "股东权益"]
    assert len(equity_rows) == 1

    idx_equity_header = int(equity_rows.index[0])
    idx_share_capital = int(out[out["科目"].astype(str).str.contains("实收资本")].index[0])
    assert idx_equity_header < idx_share_capital


def test_enrich_dedup_does_not_break_lengths():
    # same canonical item repeated with same value (common in some sources)
    df = pd.DataFrame(
        {
            "科目": [
                "所有者权益合计",
                "资产总计",
                "负债合计",
                "归属于母公司所有者权益合计",
                "流动资产",
                "资产总计",  # duplicate
                "负债合计",  # duplicate
            ],
            "数值": [1.0, 3.0, 2.0, 1.0, None, 3.0, 2.0],
            "__level": [0, 0, 0, 0, 0, 1, 1],
            "__is_header": [False, False, False, False, True, False, False],
        }
    )

    out = enrich_statement_df(df, sheet_name_cn="资产负债表")

    # key/备注 columns exist and lengths match
    assert "key" in out.columns
    assert "备注" in out.columns
    assert len(out["key"].tolist()) == len(out)
