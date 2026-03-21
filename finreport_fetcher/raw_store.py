from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


class RawReportStore:
    """Manage cached raw data + downloaded PDFs for a single company."""

    def __init__(self, company_root: Path) -> None:
        self.company_root = company_root
        self.raw_root = company_root / "raw"

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def provider_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.raw_root / provider_name)

    def provider_table_path(self, provider_name: str, table_key: str) -> Path:
        filename = f"{table_key}.pkl"
        return self.provider_dir(provider_name) / filename

    def save_provider_table(self, provider_name: str, table_key: str, df: pd.DataFrame) -> None:
        path = self.provider_table_path(provider_name, table_key)
        df.to_pickle(path)

    def load_provider_table(self, provider_name: str, table_key: str) -> pd.DataFrame | None:
        path = self.provider_table_path(provider_name, table_key)
        if not path.exists():
            return None
        try:
            return pd.read_pickle(path)
        except Exception:
            return None

    def update_provider_table(
        self,
        provider_name: str,
        table_key: str,
        df_new: pd.DataFrame,
        subset: Iterable[str] | None = None,
    ) -> None:
        path = self.provider_table_path(provider_name, table_key)
        if df_new is None or df_new.empty:
            return
        if path.exists():
            try:
                df_old = pd.read_pickle(path)
                combined = pd.concat([df_old, df_new], ignore_index=True)
            except Exception:
                combined = df_new
        else:
            combined = df_new
        if subset:
            combined = combined.drop_duplicates(subset=list(subset), keep="last")
        combined.to_pickle(path)

    def pdf_dir(self) -> Path:
        return self._ensure_dir(self.raw_root / "pdf")

    def pdf_path(self, code6: str, period_end: date) -> Path:
        fname = f"{code6}_{period_end.strftime('%Y%m%d')}.pdf"
        return self.pdf_dir() / fname

    def pdf_meta_path(self, code6: str, period_end: date) -> Path:
        fname = f"{code6}_{period_end.strftime('%Y%m%d')}.json"
        return self.pdf_dir() / fname

    def save_pdf_metadata(self, code6: str, period_end: date, metadata: dict | None) -> None:
        path = self.pdf_meta_path(code6, period_end)
        if metadata is None:
            return
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(metadata, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_pdf_metadata(self, code6: str, period_end: date) -> dict | None:
        path = self.pdf_meta_path(code6, period_end)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None
