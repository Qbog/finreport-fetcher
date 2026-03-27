from __future__ import annotations

import warnings
from datetime import date as dt_date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console

from finreport_fetcher.utils.dates import parse_date as _parse_date
from finshared.cli_entry import run_typer_app_with_default_command

from .raw_store import RawIndexStore

app = typer.Typer(add_completion=False)
console = Console()

INDEX_MAP = {
    "上证": ("sh000001", "上证综指"),
    "上证综指": ("sh000001", "上证综指"),
    "sh000001": ("sh000001", "上证综指"),
    "深证": ("sz399001", "深证成指"),
    "深证成指": ("sz399001", "深证成指"),
    "sz399001": ("sz399001", "深证成指"),
    "创业板": ("sz399006", "创业板指"),
    "创业板指": ("sz399006", "创业板指"),
    "sz399006": ("sz399006", "创业板指"),
    "北证": ("bj899050", "北证50"),
    "北证50": ("bj899050", "北证50"),
    "bj899050": ("bj899050", "北证50"),
}
DEFAULT_INDEXES = ["上证", "深证", "创业板", "北证"]
_PROVIDER = "tencent"


def log_info(msg: str):
    console.print(msg)


def parse_date_local(s: str):
    return _parse_date(s)


def resolve_indexes(items: list[str] | None) -> list[tuple[str, str]]:
    out = []
    seen = set()
    for raw in (items or DEFAULT_INDEXES):
        key = str(raw).strip()
        if key not in INDEX_MAP:
            raise typer.BadParameter(f"不支持的指数：{raw}（当前支持：上证/深证/创业板/北证）")
        code, label = INDEX_MAP[key]
        if code in seen:
            continue
        seen.add(code)
        out.append((code, label))
    return out


def _coerce_index_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "amount"])
    out = df.copy()
    if "date" not in out.columns:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "amount"])
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    for col in ["open", "close", "high", "low", "amount"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.reset_index(drop=True)


def _merge_index_df(old_df: pd.DataFrame | None, new_df: pd.DataFrame | None) -> pd.DataFrame:
    frames = []
    if old_df is not None and not old_df.empty:
        frames.append(old_df)
    if new_df is not None and not new_df.empty:
        frames.append(new_df)
    if not frames:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "amount"])
    return _coerce_index_df(pd.concat(frames, ignore_index=True))


def _fetch_index_tx_range(symbol: str, start: dt_date, end: dt_date) -> pd.DataFrame:
    if start > end:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "amount"])

    import json
    import requests

    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    frames: list[pd.DataFrame] = []
    for year in range(start.year, end.year + 1):
        seg_start = max(start, dt_date(year, 1, 1))
        seg_end = min(end, dt_date(year, 12, 31))
        params = {
            "_var": "kline_dayqfq",
            "param": f"{symbol},day,{seg_start.strftime('%Y-%m-%d')},{seg_end.strftime('%Y-%m-%d')},640,qfq",
            "r": "0.8205512681390605",
        }
        res = requests.get(url, params=params, timeout=(10, 20), headers={"User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
        text = res.text.strip()
        json_text = text.split("=", 1)[1] if "=" in text else text
        payload = json.loads(json_text)
        data = payload.get("data", {}).get(symbol, {}) if isinstance(payload, dict) else {}
        rows = data.get("day") or data.get("qfqday") or []
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "amount"])
    out = pd.concat(frames, ignore_index=True)
    if out.shape[1] >= 6:
        out = out.iloc[:, :6]
        out.columns = ["date", "open", "close", "high", "low", "amount"]
    return _coerce_index_df(out)


def fetch_index_full_history(symbol: str) -> pd.DataFrame:
    return _fetch_index_tx_range(symbol, dt_date(1990, 1, 1), dt_date.today())


def _ensure_raw_history(store: RawIndexStore, symbol: str, label: str, *, upto: dt_date) -> pd.DataFrame:
    cached = _coerce_index_df(store.load(_PROVIDER))
    meta = store.load_metadata(_PROVIDER) or {}
    if cached.empty or meta.get("scope") != "full_history":
        fresh = fetch_index_full_history(symbol)
        store.save(_PROVIDER, fresh, snapshot=False, metadata={"scope": "full_history", "symbol": symbol, "label": label, "provider": _PROVIDER, "update_mode": "bootstrap_full"})
        return fresh

    dates = pd.to_datetime(cached["date"], errors="coerce").dropna()
    if dates.empty:
        fresh = fetch_index_full_history(symbol)
        store.save(_PROVIDER, fresh, snapshot=False, metadata={"scope": "full_history", "symbol": symbol, "label": label, "provider": _PROVIDER, "update_mode": "rebuild_full"})
        return fresh

    max_date = dates.max().date()
    if max_date >= upto:
        return cached

    inc = _fetch_index_tx_range(symbol, max_date + timedelta(days=1), upto)
    merged = _merge_index_df(cached, inc)
    store.save(
        _PROVIDER,
        merged,
        snapshot=False,
        metadata={
            "scope": "full_history",
            "symbol": symbol,
            "label": label,
            "provider": _PROVIDER,
            "update_mode": "incremental_append",
            "added_rows": max(int(len(merged.index)) - int(len(cached.index)), 0),
            "from_date": (max_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "to_date": upto.strftime("%Y-%m-%d"),
        },
    )
    return merged


def _update_raw_history(store: RawIndexStore, symbol: str, label: str) -> tuple[pd.DataFrame, str | None, int]:
    cached = _coerce_index_df(store.load(_PROVIDER))
    meta = store.load_metadata(_PROVIDER) or {}
    if cached.empty or meta.get("scope") != "full_history":
        fresh = fetch_index_full_history(symbol)
        sid = store.save(_PROVIDER, fresh, snapshot=True, metadata={"scope": "full_history", "symbol": symbol, "label": label, "provider": _PROVIDER, "update_mode": "bootstrap_full"})
        return fresh, sid, int(len(fresh.index))

    dates = pd.to_datetime(cached["date"], errors="coerce").dropna()
    if dates.empty:
        fresh = fetch_index_full_history(symbol)
        sid = store.save(_PROVIDER, fresh, snapshot=True, metadata={"scope": "full_history", "symbol": symbol, "label": label, "provider": _PROVIDER, "update_mode": "rebuild_full"})
        return fresh, sid, int(len(fresh.index))

    max_date = dates.max().date()
    today = dt_date.today()
    if max_date >= today:
        sid = store.save(_PROVIDER, cached, snapshot=True, metadata={"scope": "full_history", "symbol": symbol, "label": label, "provider": _PROVIDER, "update_mode": "noop", "added_rows": 0})
        return cached, sid, 0

    inc = _fetch_index_tx_range(symbol, max_date + timedelta(days=1), today)
    merged = _merge_index_df(cached, inc)
    added = max(int(len(merged.index)) - int(len(cached.index)), 0)
    sid = store.save(
        _PROVIDER,
        merged,
        snapshot=True,
        metadata={
            "scope": "full_history",
            "symbol": symbol,
            "label": label,
            "provider": _PROVIDER,
            "update_mode": "incremental_append",
            "added_rows": added,
            "from_date": (max_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "to_date": today.strftime("%Y-%m-%d"),
        },
    )
    return merged, sid, added


@app.callback()
def _root():
    """大盘指数抓取程序。"""


@app.command("fetch")
def fetch(
    index: list[str] = typer.Option(None, "--index", "-i", help="可重复：上证/深证/创业板/北证 或对应代码"),
    start: str | None = typer.Option(None, "--start", "-s"),
    end: str | None = typer.Option(None, "--end", "-e"),
    out: Path = typer.Option(Path("output"), "--out", "-o"),
    no_clean: bool = typer.Option(False, "--no-clean", "-N"),
    update_raw: bool = typer.Option(False, "--update-raw", "-u"),
    clear_raw: bool = typer.Option(False, "--clear-raw", "-x"),
):
    maintenance_only = (update_raw or clear_raw) and not start and not end
    if not maintenance_only and ((start and not end) or (end and not start)):
        raise typer.BadParameter("--start 与 --end 必须同时提供")
    if not maintenance_only and not start and not end:
        raise typer.BadParameter("必须提供 --start/--end；若仅维护 raw，可使用 --update-raw/--clear-raw")
    targets = resolve_indexes(index)
    for code, label in targets:
        root = out.resolve() / "global" / "indexes" / code
        out_dir = root / "index"
        out_dir.mkdir(parents=True, exist_ok=True)
        store = RawIndexStore(root)
        if maintenance_only and clear_raw and not update_raw:
            providers = store.available_providers()
            if not providers:
                log_info(f"未发现可清理的指数原始数据：{label}")
                continue
            for p in providers:
                removed = store.clear_old_snapshots(p)
                log_info(f"{label} 指数 provider={p} 清理旧快照 {len(removed)} 个")
            continue
        if update_raw:
            df_raw, sid, added = _update_raw_history(store, code, label)
            log_info(f"已更新指数原始数据：{label} snapshot={sid} 新增 {added} 行")
        else:
            upto = parse_date_local(end) if end else dt_date.today()
            df_raw = _ensure_raw_history(store, code, label, upto=upto)
        if clear_raw:
            removed = store.clear_old_snapshots(_PROVIDER)
            log_info(f"{label} 指数清理旧快照 {len(removed)} 个")
        if maintenance_only:
            continue
        s = parse_date_local(start)
        e = parse_date_local(end)
        sub = df_raw[(pd.to_datetime(df_raw["date"]) >= pd.Timestamp(s)) & (pd.to_datetime(df_raw["date"]) <= pd.Timestamp(e))].copy()
        out_csv = out_dir / f"{code}.csv"
        out_xlsx = out_dir / f"{code}.xlsx"
        if no_clean and out_csv.exists():
            log_info(f"已存在，跳过重生成：{out_csv}")
            continue
        sub.to_csv(out_csv, index=False, encoding="utf-8-sig")
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            sub.to_excel(w, sheet_name="index", index=False)
        log_info(f"已输出: {out_csv} / {out_xlsx} (rows={len(sub)}, raw=full_history_incremental)")


def main():
    run_typer_app_with_default_command(app, default_command="fetch")


if __name__ == "__main__":
    main()
