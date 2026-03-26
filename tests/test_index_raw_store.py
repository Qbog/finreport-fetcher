from __future__ import annotations

from pathlib import Path

import pandas as pd

from finindex_fetcher.raw_store import RawIndexStore


def test_index_raw_store_uses_raw_provider_without_redundant_index_folder(tmp_path: Path):
    store = RawIndexStore(tmp_path / "global" / "indexes" / "sh000001")
    df = pd.DataFrame([
        {"date": "2024-01-02", "open": 1.0, "close": 1.1, "high": 1.2, "low": 0.9, "amount": 100.0}
    ])
    store.save("tencent", df, snapshot=False, metadata={"scope": "full_history"})

    assert (tmp_path / "global" / "indexes" / "sh000001" / "raw" / "tencent" / "current" / "daily.pkl").exists()
    assert not (tmp_path / "global" / "indexes" / "sh000001" / "raw" / "index" / "tencent" / "current" / "daily.pkl").exists()
