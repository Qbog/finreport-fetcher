from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


class RawPriceStore:
    """Manage cached raw daily price history for a single company.

    Layout:
      output/{公司名}_{code6}/raw/price/{provider}/current/daily.pkl|csv
      output/{公司名}_{code6}/raw/price/{provider}/snapshots/{timestamp}/daily.pkl|csv
      output/{公司名}_{code6}/raw/price/{provider}/latest.json
    """

    def __init__(self, company_root: Path) -> None:
        self.company_root = company_root
        self.raw_root = company_root / "raw" / "price"

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def provider_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.raw_root / provider_name)

    def provider_current_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.provider_dir(provider_name) / "current")

    def provider_snapshots_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.provider_dir(provider_name) / "snapshots")

    def daily_price_path(self, provider_name: str) -> Path:
        return self.provider_current_dir(provider_name) / "daily.pkl"

    def daily_price_csv_path(self, provider_name: str) -> Path:
        return self.provider_current_dir(provider_name) / "daily.csv"

    def daily_meta_path(self, provider_name: str) -> Path:
        return self.provider_dir(provider_name) / "latest.json"

    def snapshot_daily_price_path(self, provider_name: str, snapshot_id: str) -> Path:
        return self._ensure_dir(self.provider_snapshots_dir(provider_name) / snapshot_id) / "daily.pkl"

    def snapshot_daily_csv_path(self, provider_name: str, snapshot_id: str) -> Path:
        return self._ensure_dir(self.provider_snapshots_dir(provider_name) / snapshot_id) / "daily.csv"

    def _write_pair(self, pkl_path: Path, csv_path: Path, df: pd.DataFrame) -> None:
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(pkl_path)
        try:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        except Exception:
            pass

    def load_daily_prices(self, provider_name: str) -> pd.DataFrame | None:
        path = self.daily_price_path(provider_name)
        legacy = self.provider_dir(provider_name) / "daily.pkl"
        for p in [path, legacy]:
            if not p.exists():
                continue
            try:
                return pd.read_pickle(p)
            except Exception:
                continue
        return None

    def save_daily_prices(self, provider_name: str, df: pd.DataFrame, metadata: dict | None = None) -> None:
        self._write_pair(self.daily_price_path(provider_name), self.daily_price_csv_path(provider_name), df)
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

    def save_daily_snapshot(self, provider_name: str, df: pd.DataFrame, metadata: dict | None = None) -> str:
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._write_pair(self.snapshot_daily_price_path(provider_name, snapshot_id), self.snapshot_daily_csv_path(provider_name, snapshot_id), df)
        meta = dict(metadata or {})
        meta.update({"provider": provider_name, "snapshot_id": snapshot_id, "saved_at": datetime.now().isoformat(timespec="seconds"), "row_count": int(len(df))})
        if "date" in df.columns and not df.empty:
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if not dates.empty:
                meta.setdefault("min_date", dates.min().strftime("%Y-%m-%d"))
                meta.setdefault("max_date", dates.max().strftime("%Y-%m-%d"))
        self._write_pair(self.daily_price_path(provider_name), self.daily_price_csv_path(provider_name), df)
        self.save_daily_metadata(provider_name, meta)
        return snapshot_id

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
            if p.is_dir() and ((p / "current" / "daily.pkl").exists() or (p / "daily.pkl").exists()):
                out.append(p.name)
        return out

    def list_provider_snapshots(self, provider_name: str) -> list[str]:
        root = self.provider_snapshots_dir(provider_name)
        if not root.exists():
            return []
        return sorted([p.name for p in root.iterdir() if p.is_dir()])

    def clear_old_snapshots(self, provider_name: str) -> list[str]:
        meta = self.load_daily_metadata(provider_name) or {}
        latest = str(meta.get("snapshot_id") or "")
        removed: list[str] = []
        for sid in self.list_provider_snapshots(provider_name):
            if sid == latest:
                continue
            try:
                snap = self.provider_snapshots_dir(provider_name) / sid
                for p in snap.rglob("*"):
                    if p.is_file():
                        p.unlink()
                for d in sorted([x for x in snap.rglob("*") if x.is_dir()], reverse=True):
                    d.rmdir()
                snap.rmdir()
                removed.append(sid)
            except Exception:
                continue
        return removed
