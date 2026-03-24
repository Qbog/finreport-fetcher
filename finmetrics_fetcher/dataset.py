from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_company_metric_files(data_dir: Path) -> list[Path]:
    return sorted(data_dir.resolve().glob("*_*/metrics/*_financial_metrics.csv"))


def load_all_metrics(data_dir: Path) -> pd.DataFrame:
    frames = []
    for p in load_company_metric_files(data_dir):
        try:
            frames.append(pd.read_csv(p))
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
