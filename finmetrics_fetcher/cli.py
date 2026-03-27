from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console

from finreport_fetcher.utils.dates import parse_date as _parse_date
from finshared.company_categories import default_company_categories_path, resolve_company_category_symbols
from finshared.global_datasets import (
    DEFAULT_METRIC_COLUMNS,
    FinancialMetricsProvider,
    fetch_company_metrics_akshare,
    normalize_rows,
    METRIC_FIELD_ALIASES,
)
from finshared.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code

from .raw_store import RawMetricsStore

app = typer.Typer(add_completion=False)
console = Console()


def log_info(msg: str):
    console.print(msg)


def log_warn(msg: str):
    console.print(f"[yellow]{msg}[/yellow]")


@dataclass(frozen=True)
class CommonOpts:
    rs: ResolvedSymbol
    out_dir: Path
    provider: str
    tushare_token: str | None


def parse_date_local(s: str) -> date:
    return _parse_date(s)


def quarter_ends_between_local(start: date, end: date) -> list[date]:
    out: list[date] = []
    for y in range(start.year, end.year + 1):
        for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]:
            dt = date(y, m, d)
            if start <= dt <= end:
                out.append(dt)
    return out


def safe_dir_component(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', '_', str(s or '').strip()).strip() or 'unknown'


def expected_metric_xlsx_path(company_root: Path, code6: str, period_end: date) -> Path:
    return company_root / "metrics" / f"{code6}_financial_metrics_{period_end.strftime('%Y%m%d')}.xlsx"


def resolve_symbol(code: str | None, name: str | None) -> ResolvedSymbol:
    if code and name:
        raise typer.BadParameter("--code 与 --name 只能二选一")
    if code:
        rs0 = parse_code(code)
        if not rs0:
            raise typer.BadParameter(f"无法解析股票代码: {code}")
        try:
            df_map = load_a_share_name_map()
            m = df_map["code"].astype(str).str.zfill(6) == rs0.code6
            if m.any():
                nm = str(df_map[m].iloc[0]["name"])
                return ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=nm)
        except Exception:
            pass
        return rs0
    if name:
        df_map = load_a_share_name_map()
        cand = fuzzy_match_name(df_map, name)
        if cand.empty:
            raise typer.BadParameter(f"未匹配到名称: {name}")
        row = cand.iloc[0]
        rs = parse_code(str(row["code"]))
        return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=str(row["name"]))
    raise typer.BadParameter("必须提供 --code 或 --name，或者使用 --category")


def resolve_targets(code: str | None, name: str | None, category: str | None, category_config: Path | None) -> list[ResolvedSymbol]:
    if category:
        if code or name:
            raise typer.BadParameter("使用 --category 时不能同时传 --code/--name")
        resolved = resolve_company_category_symbols(category, category_config or default_company_categories_path())
        for msg in resolved.warnings:
            log_warn(msg)
        return resolved.symbols
    return [resolve_symbol(code=code, name=name)]


def normalize_metrics_df(raw_df: pd.DataFrame, code6: str, name: str | None) -> pd.DataFrame:
    rows: list[dict] = []
    for row in raw_df.to_dict(orient="records"):
        item = {col: row.get(col) for col in raw_df.columns}
        item["code6"] = code6
        item["name"] = name
        rows.append(item)
    df = normalize_rows(rows, METRIC_FIELD_ALIASES, DEFAULT_METRIC_COLUMNS)
    if not df.empty:
        if "end_date" in df.columns:
            df["end_date"] = df["end_date"].astype(str)
        if "ann_date" in df.columns:
            df["ann_date"] = df["ann_date"].astype(str)
        df = df.sort_values(["code6", "end_date"], na_position="last").reset_index(drop=True)
    return df


def _provider_choices(c: CommonOpts) -> list[str]:
    if c.provider in {"tushare", "akshare"}:
        return [c.provider]
    return ["tushare", "akshare"] if c.tushare_token else ["akshare"]


def fetch_full_history_metrics(c: CommonOpts, provider_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if provider_name == "tushare":
        provider = FinancialMetricsProvider()
        source_df = provider.fetch_company_metrics(ts_code=c.rs.ts_code, tushare_token=c.tushare_token)
        metrics_df = normalize_metrics_df(source_df, c.rs.code6, c.rs.name)
        return source_df, metrics_df

    source_df, metrics_df = fetch_company_metrics_akshare(c.rs.code6)
    metrics_df = metrics_df.copy()
    if not metrics_df.empty:
        metrics_df["name"] = c.rs.name
        metrics_df["ts_code"] = c.rs.ts_code
        metrics_df["code6"] = c.rs.code6
    return source_df, metrics_df


def _period_key_set(metrics_df: pd.DataFrame | None) -> set[str]:
    if metrics_df is None or metrics_df.empty or "end_date" not in metrics_df.columns:
        return set()
    return {str(x) for x in metrics_df["end_date"].astype(str).str.replace(r"[^0-9]", "", regex=True) if len(str(x)) == 8}


def _merge_metrics_df(old_df: pd.DataFrame | None, new_df: pd.DataFrame | None) -> pd.DataFrame:
    frames = []
    if old_df is not None and not old_df.empty:
        frames.append(old_df)
    if new_df is not None and not new_df.empty:
        frames.append(new_df)
    if not frames:
        return pd.DataFrame(columns=DEFAULT_METRIC_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    subset = [c for c in ["ts_code", "code6", "end_date"] if c in out.columns]
    if subset:
        out = out.drop_duplicates(subset=subset, keep="last")
    if "end_date" in out.columns:
        out["end_date"] = out["end_date"].astype(str)
    if "ann_date" in out.columns:
        out["ann_date"] = out["ann_date"].astype(str)
    sort_cols = [c for c in ["code6", "end_date"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, na_position="last")
    return out.reset_index(drop=True)


def _merge_source_df(old_df: pd.DataFrame | None, new_df: pd.DataFrame | None) -> pd.DataFrame:
    if new_df is None or new_df.empty:
        return old_df.copy() if old_df is not None else pd.DataFrame()
    if old_df is None or old_df.empty:
        return new_df.copy()
    subset = [c for c in ["ts_code", "end_date", "ann_date", "报告期", "公告日期"] if c in new_df.columns and c in old_df.columns]
    if not subset:
        return new_df.copy()
    out = pd.concat([old_df, new_df], ignore_index=True)
    out = out.drop_duplicates(subset=subset, keep="last")
    sort_col = "end_date" if "end_date" in out.columns else ("报告期" if "报告期" in out.columns else None)
    if sort_col:
        out = out.sort_values(sort_col, na_position="last")
    return out.reset_index(drop=True)


def _save_metrics_cache(store: RawMetricsStore, provider_name: str, source_df: pd.DataFrame, metrics_df: pd.DataFrame, *, snapshot: bool, metadata: dict | None = None) -> str | None:
    meta = {"scope": "full_history", "provider": provider_name}
    meta.update(metadata or {})
    return store.save(provider_name, source_df, metrics_df, meta, snapshot=snapshot)


def _refresh_provider_metrics(
    c: CommonOpts,
    store: RawMetricsStore,
    provider_name: str,
    *,
    snapshot: bool,
    required_periods: set[str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    old_metrics = store.load_metrics(provider_name)
    old_source = store.load_source(provider_name)
    meta = store.load_metadata(provider_name) or {}
    old_keys = _period_key_set(old_metrics)

    if old_metrics is not None and not old_metrics.empty and meta.get("scope") == "full_history":
        if required_periods and required_periods.issubset(old_keys) and not snapshot:
            return old_metrics, None

    source_df, fresh_metrics = fetch_full_history_metrics(c, provider_name)
    merged_metrics = _merge_metrics_df(old_metrics, fresh_metrics)
    merged_source = _merge_source_df(old_source, source_df)
    new_keys = _period_key_set(merged_metrics)
    added_keys = sorted(new_keys - old_keys)
    update_mode = "bootstrap_full" if not old_keys else ("incremental_merge" if added_keys else "refresh_noop")
    sid = _save_metrics_cache(
        store,
        provider_name,
        merged_source,
        merged_metrics,
        snapshot=snapshot,
        metadata={
            "ts_code": c.rs.ts_code,
            "update_mode": update_mode,
            "added_periods": added_keys,
        },
    )
    return merged_metrics, sid


def ensure_raw_metrics(c: CommonOpts, store: RawMetricsStore, *, required_periods: set[str] | None = None) -> tuple[str, pd.DataFrame]:
    preferred_existing = [p for p in ([c.provider] if c.provider in {"tushare", "akshare"} else store.available_providers()) if p]
    for provider_name in preferred_existing:
        metrics_df = store.load_metrics(provider_name)
        if metrics_df is None or metrics_df.empty:
            continue
        if not required_periods or required_periods.issubset(_period_key_set(metrics_df)):
            return provider_name, metrics_df
        refreshed, _sid = _refresh_provider_metrics(c, store, provider_name, snapshot=False, required_periods=required_periods)
        return provider_name, refreshed

    last_err: Exception | None = None
    for provider_name in _provider_choices(c):
        try:
            refreshed, _sid = _refresh_provider_metrics(c, store, provider_name, snapshot=False, required_periods=required_periods)
            return provider_name, refreshed
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"获取全历史指标失败：{last_err}")


def update_raw_metrics(c: CommonOpts, store: RawMetricsStore) -> tuple[str, pd.DataFrame, str | None]:
    last_err: Exception | None = None
    for provider_name in _provider_choices(c):
        try:
            metrics_df, sid = _refresh_provider_metrics(c, store, provider_name, snapshot=True, required_periods=None)
            return provider_name, metrics_df, sid
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"更新全历史指标失败：{last_err}")


def clear_raw_metrics(store: RawMetricsStore) -> None:
    providers = store.available_providers()
    if not providers:
        log_info("未发现可清理的指标原始数据。")
        return
    for pname in providers:
        removed = store.clear_old_snapshots(pname)
        if removed:
            log_info(f"已清理指标 provider={pname} 旧原始快照 {len(removed)} 个")
        else:
            log_info(f"指标 provider={pname} 没有旧原始快照可清理。")


def export_metrics_period(company_root: Path, rs: ResolvedSymbol, period_end: date, metrics_df: pd.DataFrame, *, no_clean: bool) -> str:
    out_dir = company_root / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = expected_metric_xlsx_path(company_root, rs.code6, period_end)
    if no_clean and out_path.exists():
        log_info(f"已存在，跳过重生成：{out_path}")
        return "skipped"

    pe_key = period_end.strftime("%Y%m%d")
    sub = metrics_df[metrics_df["end_date"].astype(str).str.replace(r"[^0-9]", "", regex=True) == pe_key].copy()
    if sub.empty:
        raise RuntimeError(f"原始数据中没有 {period_end.strftime('%Y-%m-%d')} 日期的指标")
    row = sub.iloc[0]
    items = []
    for col in ["roe", "roa", "roic", "ev", "ebitda"]:
        items.append({"指标": col.upper() if col in {"roe", "roa", "roic", "ev"} else col.upper(), "数值": row.get(col)})
    df_out = pd.DataFrame(items)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, sheet_name="metrics", index=False)
    return "exported"


@app.callback()
def _root():
    """公司财报指标抓取程序。"""


@app.command("fetch")
def fetch(
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    category: str | None = typer.Option(None, "--category"),
    category_config: Path | None = typer.Option(None, "--category-config"),
    date_: str | None = typer.Option(None, "--date"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    out_dir: Path = typer.Option(Path("output"), "--out", help="输出根目录"),
    provider: str = typer.Option("auto", "--provider", help="auto|tushare|akshare"),
    no_clean: bool = typer.Option(False, "--no-clean"),
    update_raw: bool = typer.Option(False, "--update-raw"),
    clear_raw: bool = typer.Option(False, "--clear-raw"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    if category and (code or name):
        raise typer.BadParameter("--category 与 --code/--name 互斥")
    if not category and not (code or name):
        raise typer.BadParameter("必须提供 --code/--name 或 --category")
    maintenance_only = (update_raw or clear_raw) and not date_ and not (start or end)
    if date_ and (start or end):
        raise typer.BadParameter("--date 与 --start/--end 不能同时使用")
    if (start and not end) or (end and not start):
        raise typer.BadParameter("--start 与 --end 必须同时提供")
    if not maintenance_only and not date_ and not (start and end):
        raise typer.BadParameter("必须提供 --date 或 --start/--end；若仅维护 raw，可使用 --update-raw/--clear-raw")

    targets = resolve_targets(code, name, category, category_config)
    for rs in targets:
        company_root = out_dir.resolve() / safe_dir_component(f"{(rs.name or rs.code6)}_{rs.code6}")
        store = RawMetricsStore(company_root)
        c = CommonOpts(rs=rs, out_dir=out_dir.resolve(), provider=provider.strip().lower(), tushare_token=tushare_token)

        required_periods: set[str] | None = None
        if date_:
            dt_target = parse_date_local(date_)
            required_periods = {
                pe.strftime('%Y%m%d')
                for pe in quarter_ends_between_local(date(max(dt_target.year - 2, 1990), 1, 1), dt_target)
            }
        elif start and end:
            required_periods = {pe.strftime('%Y%m%d') for pe in quarter_ends_between_local(parse_date_local(start), parse_date_local(end))}

        if update_raw:
            p, metrics_df, sid = update_raw_metrics(c, store)
            log_info(f"已更新指标原始数据：{rs.name or rs.code6}({rs.code6}) provider={p} snapshot={sid}")
        elif clear_raw and maintenance_only:
            clear_raw_metrics(store)
            log_info(f"原始指标维护完成：{rs.name or rs.code6}({rs.code6})")
            continue
        else:
            p, metrics_df = ensure_raw_metrics(c, store, required_periods=required_periods)

        if clear_raw:
            clear_raw_metrics(store)

        metrics_dir = company_root / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        summary_csv = metrics_dir / f"{rs.code6}_financial_metrics.csv"
        metrics_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

        if maintenance_only:
            log_info(f"原始指标维护完成：{rs.name or rs.code6}({rs.code6})")
            continue

        if date_:
            dt = parse_date_local(date_)
            available = sorted([parse_date_local(f"{str(x)[:4]}-{str(x)[4:6]}-{str(x)[6:8]}") for x in metrics_df["end_date"].astype(str).str.replace(r"[^0-9]", "", regex=True) if len(str(x)) == 8])
            target = None
            for pe in available:
                if pe <= dt:
                    target = pe
            if target is None:
                raise RuntimeError(f"原始数据中没有 {dt.strftime('%Y-%m-%d')} 之前可用的指标")
            result = export_metrics_period(company_root, rs, target, metrics_df, no_clean=no_clean)
            if result == "exported":
                log_info(f"已导出: {expected_metric_xlsx_path(company_root, rs.code6, target)}（provider={p}）")
        else:
            s = parse_date_local(start)
            e = parse_date_local(end)
            periods = quarter_ends_between_local(s, e)
            if not periods:
                raise RuntimeError("日期范围内没有任何标准报告期末日")
            for pe in periods:
                try:
                    result = export_metrics_period(company_root, rs, pe, metrics_df, no_clean=no_clean)
                    if result == "exported":
                        log_info(f"已导出: {expected_metric_xlsx_path(company_root, rs.code6, pe)}（provider={p}）")
                except Exception as exc:  # noqa: BLE001
                    log_warn(f"跳过 {pe.strftime('%Y-%m-%d')}：{exc}")
                    continue


def main():
    app()


if __name__ == "__main__":
    main()
