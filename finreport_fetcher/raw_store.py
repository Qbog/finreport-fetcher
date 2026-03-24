from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


class RawReportStore:
    """Manage cached raw data + downloaded PDFs for a single company.

    Layout:
      {company}/raw/report/{provider}/current/{table}.pkl|csv
      {company}/raw/report/{provider}/snapshots/{timestamp}/{table}.pkl|csv
      {company}/raw/report/{provider}/latest.json
    """

    def __init__(self, company_root: Path) -> None:
        self.company_root = company_root
        self.raw_root = company_root / "raw"
        self.report_root = self.raw_root / "report"

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _provider_dir_noensure(self, provider_name: str) -> Path:
        return self.report_root / provider_name

    def _legacy_provider_dir(self, provider_name: str) -> Path:
        return self.raw_root / provider_name

    def provider_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self._provider_dir_noensure(provider_name))

    def provider_current_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.provider_dir(provider_name) / "current")

    def provider_snapshots_dir(self, provider_name: str, *, ensure: bool = True) -> Path:
        p = self.provider_dir(provider_name) / "snapshots" if ensure else self._provider_dir_noensure(provider_name) / "snapshots"
        return self._ensure_dir(p) if ensure else p

    def provider_latest_meta_path(self, provider_name: str) -> Path:
        return self.provider_dir(provider_name) / "latest.json"

    def provider_snapshot_dir(self, provider_name: str, snapshot_id: str) -> Path:
        return self._ensure_dir(self.provider_snapshots_dir(provider_name) / snapshot_id)

    def provider_table_path(self, provider_name: str, table_key: str) -> Path:
        return self.provider_current_dir(provider_name) / f"{table_key}.pkl"

    def provider_table_csv_path(self, provider_name: str, table_key: str) -> Path:
        return self.provider_current_dir(provider_name) / f"{table_key}.csv"

    def provider_snapshot_table_path(self, provider_name: str, snapshot_id: str, table_key: str) -> Path:
        return self.provider_snapshot_dir(provider_name, snapshot_id) / f"{table_key}.pkl"

    def provider_snapshot_table_csv_path(self, provider_name: str, snapshot_id: str, table_key: str) -> Path:
        return self.provider_snapshot_dir(provider_name, snapshot_id) / f"{table_key}.csv"

    def _write_table_pair(self, pkl_path: Path, csv_path: Path, df: pd.DataFrame) -> None:
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(pkl_path)
        try:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        except Exception:
            pass

    def save_provider_table(self, provider_name: str, table_key: str, df: pd.DataFrame) -> None:
        self._write_table_pair(
            self.provider_table_path(provider_name, table_key),
            self.provider_table_csv_path(provider_name, table_key),
            df,
        )

    def load_provider_table(self, provider_name: str, table_key: str) -> pd.DataFrame | None:
        path = self.provider_table_path(provider_name, table_key)
        legacy_path = self._legacy_provider_dir(provider_name) / f"{table_key}.pkl"
        for p in [path, legacy_path]:
            if not p.exists():
                continue
            try:
                return pd.read_pickle(p)
            except Exception:
                continue
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
            legacy = self.load_provider_table(provider_name, table_key)
            combined = pd.concat([legacy, df_new], ignore_index=True) if legacy is not None else df_new
        if subset:
            combined = combined.drop_duplicates(subset=list(subset), keep="last")
        self.save_provider_table(provider_name, table_key, combined)

    def save_provider_snapshot(self, provider_name: str, tables: dict[str, pd.DataFrame], metadata: dict | None = None) -> str:
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = self.provider_snapshot_dir(provider_name, snapshot_id)
        for table_key, df in tables.items():
            if df is None:
                continue
            self._write_table_pair(
                self.provider_snapshot_table_path(provider_name, snapshot_id, table_key),
                self.provider_snapshot_table_csv_path(provider_name, snapshot_id, table_key),
                df,
            )
            self._write_table_pair(
                self.provider_table_path(provider_name, table_key),
                self.provider_table_csv_path(provider_name, table_key),
                df,
            )
        meta = dict(metadata or {})
        meta.update({"snapshot_id": snapshot_id, "saved_at": datetime.now().isoformat(timespec="seconds")})
        (snap_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.provider_latest_meta_path(provider_name).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot_id

    def load_provider_metadata(self, provider_name: str) -> dict | None:
        p = self.provider_latest_meta_path(provider_name)
        legacy = self._legacy_provider_dir(provider_name) / "latest.json"
        for cand in [p, legacy]:
            if not cand.exists():
                continue
            try:
                return json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                continue
        return None

    def available_providers(self) -> list[str]:
        names: set[str] = set()
        if self.report_root.exists():
            names |= {p.name for p in self.report_root.iterdir() if p.is_dir()}
        if self.raw_root.exists():
            names |= {p.name for p in self.raw_root.iterdir() if p.is_dir() and p.name not in {"price", "pdf", "report"}}
        return sorted(names)

    def list_provider_snapshots(self, provider_name: str) -> list[str]:
        root = self.provider_snapshots_dir(provider_name, ensure=False)
        if not root.exists():
            return []
        return sorted([p.name for p in root.iterdir() if p.is_dir()])

    def clear_old_provider_snapshots(self, provider_name: str) -> list[str]:
        keep = self.load_provider_metadata(provider_name) or {}
        latest = str(keep.get("snapshot_id") or "")
        removed: list[str] = []
        for sid in self.list_provider_snapshots(provider_name):
            if sid == latest:
                continue
            try:
                snap = self.provider_snapshots_dir(provider_name, ensure=False) / sid
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
