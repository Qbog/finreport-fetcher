from __future__ import annotations

from pathlib import Path

from finshared.global_datasets import (
    DatasetPaths,
    FinancialMetricsProvider,
    fetch_financial_metrics_dataset,
    load_financial_metrics_csv,
)

__all__ = [
    "DatasetPaths",
    "FinancialMetricsProvider",
    "fetch_financial_metrics_dataset",
    "load_financial_metrics_csv",
]


def load_csv(data_dir: Path):
    return load_financial_metrics_csv(data_dir)
