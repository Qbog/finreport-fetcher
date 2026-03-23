from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


class RawPriceStore:
    """Manage cached raw daily price history for a single company.

    Layout:
      output/{公司名}_{code6}/raw/price/{provider}/daily.pkl
      output/{公司名}_{code6}/raw/price/{provider}/daily.json
    """

    def __init__(self, company_root: Path) -> None:
        self.company_root = company_root
        self.raw_root = company_root / "raw" / "price"

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def provider_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.raw_root / provider_name)

    def daily_price_path(self, provider_name: str) -> Path:
        return self.provider_dir(provider_name) / "daily.pkl"

    def daily_meta_path(self, provider_name: str) -> Path:
        return self.provider_dir(provider_name) / "daily.json"

    def load_daily_prices(self, provider_name: str) -> pd.DataFrame | None:
        path = self.daily_price_path(provider_name)
        if not path.exists():
            return None
        try:
            return pd.read_pickle(path)
        except Exception:
            return None

    def save_daily_prices(self, provider_name: str, df: pd.DataFrame, metadata: dict | None = None) -> None:
        path = self.daily_price_path(provider_name)
        df.to_pickle(path)

        meta = dict(metadata or {})
        meta.setdefault("provider", provider_name)
        meta.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
        meta.setdefault("row_count", int(len(df)))
        if "date" in df.columns and not df.empty:
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if not dates.empty:
                meta.setdefault("min_date", dates.min().strftime("%Y-%m-%d"))
                meta.setdefault("max_date", dates.max().strftime("%Y-%m-%d"))
        self.save_daily_metadata(provider_name, meta)

    def load_daily_metadata(self, provider_name: str) -> dict | None:
        path = self.daily_meta_path(provider_name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_daily_metadata(self, provider_name: str, metadata: dict | None) -> None:
        if metadata is None:
            return
        path = self.daily_meta_path(provider_name)
        try:
            path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def available_providers(self) -> list[str]:
        if not self.raw_root.exists():
            return []
        out: list[str] = []
        for p in sorted(self.raw_root.iterdir()):
            if p.is_dir() and (p / "daily.pkl").exists():
                out.append(p.name)
        return out
