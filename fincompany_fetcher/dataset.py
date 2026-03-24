from __future__ import annotations

from pathlib import Path

from finshared.global_datasets import (
    CompanyBasicsProvider,
    DatasetPaths,
    fetch_company_basics_dataset,
    load_company_basics_csv,
)

__all__ = [
    "CompanyBasicsProvider",
    "DatasetPaths",
    "fetch_company_basics_dataset",
    "load_company_basics_csv",
]


def load_csv(data_dir: Path):
    return load_company_basics_csv(data_dir)
