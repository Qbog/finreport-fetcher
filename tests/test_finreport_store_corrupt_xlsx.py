from __future__ import annotations

from pathlib import Path

import pytest

from finreport_charts.data.finreport_store import read_statement_df


def test_read_statement_df_raises_clear_error_on_corrupt_xlsx(tmp_path: Path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not-a-real-xlsx")

    with pytest.raises(RuntimeError, match="财报文件已损坏"):
        read_statement_df(p, "利润表")
