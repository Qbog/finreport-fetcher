from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


class RawMetricsStore:
    """Per-company raw metrics store.

    Layout:
      output/{公司名}_{code6}/raw/metrics/{provider}/current/source.pkl|csv
      output/{公司名}_{code6}/raw/metrics/{provider}/current/metrics.pkl|csv
      output/{公司名}_{code6}/raw/metrics/{provider}/snapshots/{timestamp}/...
      output/{公司名}_{code6}/raw/metrics/{provider}/latest.json
    """

    def __init__(self, company_root: Path) -> None:
        self.company_root = company_root
        self.raw_root = company_root / "raw" / "metrics"

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def provider_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.raw_root / provider_name)

    def provider_current_dir(self, provider_name: str) -> Path:
        return self._ensure_dir(self.provider_dir(provider_name) / "current")

    def provider_snapshots_dir(self, provider_name: str, ensure: bool = True) -> Path:
        p = self.provider_dir(provider_name) / "snapshots"
        return self._ensure_dir(p) if ensure else p

    def latest_meta_path(self, provider_name: str) -> Path:
        return self.provider_dir(provider_name) / "latest.json"

    def _current_path(self, provider_name: str, name: str, ext: str) -> Path:
        return self.provider_current_dir(provider_name) / f"{name}.{ext}"

    def _snapshot_path(self, provider_name: str, snapshot_id: str, name: str, ext: str) -> Path:
        return self._ensure_dir(self.provider_snapshots_dir(provider_name) / snapshot_id) / f"{name}.{ext}"

    def _write_df(self, pkl_path: Path, csv_path: Path, df: pd.DataFrame) -> None:
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(pkl_path)
        try:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        except Exception:
            pass

    def save(self, provider_name: str, source_df: pd.DataFrame, metrics_df: pd.DataFrame, metadata: dict | None = None, *, snapshot: bool) -> str | None:
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S") if snapshot else None
        self._write_df(self._current_path(provider_name, "source", "pkl"), self._current_path(provider_name, "source", "csv"), source_df)
        self._write_df(self._current_path(provider_name, "metrics", "pkl"), self._current_path(provider_name, "metrics", "csv"), metrics_df)
        if snapshot_id:
            self._write_df(self._snapshot_path(provider_name, snapshot_id, "source", "pkl"), self._snapshot_path(provider_name, snapshot_id, "source", "csv"), source_df)
            self._write_df(self._snapshot_path(provider_name, snapshot_id, "metrics", "pkl"), self._snapshot_path(provider_name, snapshot_id, "metrics", "csv"), metrics_df)
        meta = dict(metadata or {})
        meta.update({
            "provider": provider_name,
            "snapshot_id": snapshot_id,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "rows": int(len(metrics_df.index)),
            "scope": meta.get("scope") or "full_history",
        })
        self.latest_meta_path(provider_name).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot_id

    def load_source(self, provider_name: str) -> pd.DataFrame | None:
        p = self._current_path(provider_name, "source", "pkl")
        if not p.exists():
            return None
        try:
            return pd.read_pickle(p)
        except Exception:
            return None

    def load_metrics(self, provider_name: str) -> pd.DataFrame | None:
        p = self._current_path(provider_name, "metrics", "pkl")
        if not p.exists():
            return None
        try:
            return pd.read_pickle(p)
        except Exception:
            return None

    def load_metadata(self, provider_name: str) -> dict | None:
        p = self.latest_meta_path(provider_name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def available_providers(self) -> list[str]:
        if not self.raw_root.exists():
            return []
        return sorted([p.name for p in self.raw_root.iterdir() if p.is_dir()])

    def list_snapshots(self, provider_name: str) -> list[str]:
        root = self.provider_snapshots_dir(provider_name, ensure=False)
        if not root.exists():
            return []
        return sorted([p.name for p in root.iterdir() if p.is_dir()])

    def clear_old_snapshots(self, provider_name: str) -> list[str]:
        meta = self.load_metadata(provider_name) or {}
        latest = str(meta.get("snapshot_id") or "")
        removed: list[str] = []
        for sid in self.list_snapshots(provider_name):
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
