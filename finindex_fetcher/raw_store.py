from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


class RawIndexStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw_root = root / "raw" / "index"

    def _ensure_dir(self, p: Path) -> Path:
        p.mkdir(parents=True, exist_ok=True)
        return p

    def provider_dir(self, provider: str) -> Path:
        return self._ensure_dir(self.raw_root / provider)

    def current_dir(self, provider: str) -> Path:
        return self._ensure_dir(self.provider_dir(provider) / "current")

    def snapshots_dir(self, provider: str, ensure: bool = True) -> Path:
        p = self.provider_dir(provider) / "snapshots"
        return self._ensure_dir(p) if ensure else p

    def latest_meta(self, provider: str) -> Path:
        return self.provider_dir(provider) / "latest.json"

    def _write(self, pkl_path: Path, csv_path: Path, df: pd.DataFrame) -> None:
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(pkl_path)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    def load(self, provider: str) -> pd.DataFrame | None:
        p = self.current_dir(provider) / "daily.pkl"
        if not p.exists():
            return None
        try:
            return pd.read_pickle(p)
        except Exception:
            return None

    def save(self, provider: str, df: pd.DataFrame, *, snapshot: bool, metadata: dict | None = None) -> str | None:
        sid = datetime.now().strftime("%Y%m%d_%H%M%S") if snapshot else None
        self._write(self.current_dir(provider) / "daily.pkl", self.current_dir(provider) / "daily.csv", df)
        if sid:
            d = self._ensure_dir(self.snapshots_dir(provider) / sid)
            self._write(d / "daily.pkl", d / "daily.csv", df)
        meta = dict(metadata or {})
        meta.update({"snapshot_id": sid, "saved_at": datetime.now().isoformat(timespec="seconds"), "rows": int(len(df.index))})
        self.latest_meta(provider).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return sid

    def available_providers(self) -> list[str]:
        if not self.raw_root.exists():
            return []
        return sorted([p.name for p in self.raw_root.iterdir() if p.is_dir()])

    def clear_old_snapshots(self, provider: str) -> list[str]:
        meta = {}
        try:
            meta = json.loads(self.latest_meta(provider).read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        latest = str(meta.get("snapshot_id") or "")
        root = self.snapshots_dir(provider, ensure=False)
        if not root.exists():
            return []
        removed = []
        for p in root.iterdir():
            if not p.is_dir() or p.name == latest:
                continue
            for f in p.rglob('*'):
                if f.is_file():
                    f.unlink()
            for d in sorted([x for x in p.rglob('*') if x.is_dir()], reverse=True):
                d.rmdir()
            p.rmdir()
            removed.append(p.name)
        return removed
