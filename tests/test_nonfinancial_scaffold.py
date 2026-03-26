from __future__ import annotations

import pandas as pd

from finreport_fetcher.mappings.enrich import enrich_statement_df


def test_nonfinancial_statement_scaffold_is_unified():
    df1 = pd.DataFrame([
        {"科目": "资产总计", "数值": 100.0},
        {"科目": "可供出售金融资产", "数值": 10.0},
    ])
    df2 = pd.DataFrame([
        {"科目": "资产总计", "数值": 200.0},
        {"科目": "衍生金融负债", "数值": 3.0},
    ])
    out1 = enrich_statement_df(df1, sheet_name_cn="资产负债表", company_category="non_financial")
    out2 = enrich_statement_df(df2, sheet_name_cn="资产负债表", company_category="non_financial")
    assert out1["key"].astype(str).tolist() == out2["key"].astype(str).tolist()
    assert "bs.afs_fin_assets" in out1["key"].astype(str).tolist()
    assert "bs.derivative_fin_liabilities" in out1["key"].astype(str).tolist()
