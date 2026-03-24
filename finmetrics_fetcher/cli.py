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

from finshared.company_categories import default_company_categories_path, resolve_company_category
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
    return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()


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
        cat = resolve_company_category(category, category_config or default_company_categories_path())
        df_map = None
        try:
            df_map = load_a_share_name_map()
        except Exception:
            pass
        out: list[ResolvedSymbol] = []
        seen: set[str] = set()
        for it in cat.items:
            rs0 = parse_code(it.code6)
            if not rs0 or rs0.code6 in seen:
                continue
            seen.add(rs0.code6)
            nm = it.name
            if (not nm) and df_map is not None:
                m = df_map["code"].astype(str).str.zfill(6) == rs0.code6
                if m.any():
                    nm = str(df_map[m].iloc[0]["name"])
            out.append(ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=nm))
        return out
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


def fetch_full_history_metrics(c: CommonOpts) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    last_err: Exception | None = None
    choices = [c.provider] if c.provider in {"tushare", "akshare"} else (["tushare", "akshare"] if c.tushare_token else ["akshare"])
    for provider_name in choices:
        try:
            if provider_name == "tushare":
                provider = FinancialMetricsProvider()
                source_df = provider.fetch_company_metrics(ts_code=c.rs.ts_code, tushare_token=c.tushare_token)
                metrics_df = normalize_metrics_df(source_df, c.rs.code6, c.rs.name)
            else:
                source_df, metrics_df = fetch_company_metrics_akshare(c.rs.code6)
                metrics_df = metrics_df.copy()
                if not metrics_df.empty:
                    metrics_df["name"] = c.rs.name
                    metrics_df["ts_code"] = c.rs.ts_code
                    metrics_df["code6"] = c.rs.code6
            return provider_name, source_df, metrics_df
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"获取全历史指标失败：{last_err}")


def ensure_raw_metrics(c: CommonOpts, store: RawMetricsStore) -> tuple[str, pd.DataFrame]:
    for provider_name in ([c.provider] if c.provider in {"tushare", "akshare"} else store.available_providers()):
        df = store.load_metrics(provider_name)
        if df is not None and not df.empty:
            return provider_name, df
    provider_name, source_df, metrics_df = fetch_full_history_metrics(c)
    store.save(provider_name, source_df, metrics_df, {"scope": "full_history", "ts_code": c.rs.ts_code, "provider": provider_name}, snapshot=False)
    return provider_name, metrics_df


def update_raw_metrics(c: CommonOpts, store: RawMetricsStore) -> tuple[str, pd.DataFrame, str | None]:
    provider_name, source_df, metrics_df = fetch_full_history_metrics(c)
    sid = store.save(provider_name, source_df, metrics_df, {"scope": "full_history", "ts_code": c.rs.ts_code, "provider": provider_name}, snapshot=True)
    return provider_name, metrics_df, sid


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

        if update_raw:
            p, metrics_df, sid = update_raw_metrics(c, store)
            log_info(f"已更新指标原始数据：{rs.name or rs.code6}({rs.code6}) provider={p} snapshot={sid}")
        elif clear_raw and maintenance_only:
            clear_raw_metrics(store)
            log_info(f"原始指标维护完成：{rs.name or rs.code6}({rs.code6})")
            continue
        else:
            p, metrics_df = ensure_raw_metrics(c, store)

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
