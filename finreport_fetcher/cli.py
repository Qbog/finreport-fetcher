from __future__ import annotations

import warnings
from datetime import date
from enum import IntEnum
from pathlib import Path

import pandas as pd

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import typer
from rich.console import Console
from rich.prompt import IntPrompt

from .exporter.excel import export_bundle_to_excel
from .metrics_sheet import build_metrics_sheet
from .pdf.cninfo import find_and_download_period_pdf
from .raw_store import RawReportStore
from .providers.registry import ProviderConfig, build_providers
from .utils.dates import candidate_quarter_ends_before, parse_date, quarter_ends_between
from .utils.paths import safe_dir_component
from .utils.company_category import detect_company_category
from finshared.company_categories import default_company_categories_path, resolve_company_category_symbols
from finmetrics_fetcher.cli import CommonOpts as MetricsCommonOpts, clear_raw_metrics, ensure_raw_metrics, update_raw_metrics
from finmetrics_fetcher.raw_store import RawMetricsStore
from .utils.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code

app = typer.Typer(add_completion=False)
console = Console()


class LogLevel(IntEnum):
    """Log verbosity control.

    Lower value => more verbose.
    """

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


_LOG_LEVEL: LogLevel = LogLevel.INFO


def _parse_log_level(s: str) -> LogLevel:
    ss = (s or "").strip().lower()
    if ss in {"debug", "d"}:
        return LogLevel.DEBUG
    if ss in {"info", "i"}:
        return LogLevel.INFO
    if ss in {"warn", "warning", "w"}:
        return LogLevel.WARNING
    if ss in {"error", "err", "e"}:
        return LogLevel.ERROR
    raise typer.BadParameter("--log-level 仅支持: debug/info/warning/error")


def log_print(level: LogLevel, msg: str, *, always: bool = False):
    if always or level >= _LOG_LEVEL:
        console.print(msg)


def log_debug(msg: str):
    log_print(LogLevel.DEBUG, f"[dim]{msg}[/dim]")


def log_info(msg: str):
    log_print(LogLevel.INFO, msg)


def log_warn(msg: str):
    log_print(LogLevel.WARNING, f"[yellow]{msg}[/yellow]")


def log_error(msg: str):
    log_print(LogLevel.ERROR, f"[red]{msg}[/red]")


@app.callback()
def _root(
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-l",
        help="输出级别：debug/info/warning/error（默认 info）",
        show_default=True,
    ),
):
    """A股财报抓取工具。

    使用 `fetch` 子命令按股票代码/名称抓取三大报表并导出 Excel。
    """

    global _LOG_LEVEL
    _LOG_LEVEL = _parse_log_level(log_level)


@app.command()
def version():
    """输出版本号。"""
    from . import __version__

    console.print(__version__)


def _resolve_symbol(code: str | None, name: str | None) -> ResolvedSymbol:
    if code and name:
        raise typer.BadParameter("--code 与 --name 只能二选一")

    if code:
        rs0 = parse_code(code)
        if not rs0:
            raise typer.BadParameter(f"无法解析股票代码格式: {code}")

        # Fill official name if possible (user要求用正式简称命名目录)
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
        if len(cand) == 1:
            c = cand.iloc[0]
            rs = parse_code(str(c["code"]))
            return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=str(c["name"]))

        console.print(f"匹配到 {len(cand)} 个候选：")
        show_n = min(20, len(cand))
        for i in range(show_n):
            r = cand.iloc[i]
            console.print(f"[{i}] {r['code']}  {r['name']}")
        if len(cand) > show_n:
            console.print(f"... 仅显示前 {show_n} 条")

        idx = IntPrompt.ask("请选择序号", default=0)
        if idx < 0 or idx >= len(cand):
            raise typer.BadParameter("序号超出范围")
        r = cand.iloc[idx]
        rs = parse_code(str(r["code"]))
        return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=str(r["name"]))

    raise typer.BadParameter("必须提供 --code 或 --name")



def _exc_short(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _expected_xlsx_path(out_dir: Path, code6: str, statement_type: str, period_end: date) -> Path:
    return out_dir / f"{code6}_{statement_type}_{period_end.strftime('%Y%m%d')}.xlsx"


def _company_root_from(out_dir: Path, company_name: str | None, code6: str) -> Path:
    return out_dir.parent / safe_dir_component(f"{(company_name or code6)}_{code6}")


def _load_metrics_sheet(
    *,
    ts_code: str,
    code6: str,
    company_name: str | None,
    period_end: date,
    provider: str,
    out_dir: Path,
    tushare_token: str | None,
    raw_store: RawReportStore | None,
) -> tuple[pd.DataFrame | None, str | None]:
    company_root = raw_store.company_root if raw_store is not None else _company_root_from(out_dir, company_name, code6)
    metrics_store = RawMetricsStore(company_root)
    rs0 = parse_code(ts_code) or parse_code(code6)
    rs = ResolvedSymbol(code6=code6, ts_code=ts_code, market=rs0.market if rs0 else "SZ", name=company_name)
    opts = MetricsCommonOpts(rs=rs, out_dir=company_root.parent.resolve(), provider=(provider or "auto").strip().lower(), tushare_token=tushare_token)
    provider_used, metrics_df = ensure_raw_metrics(opts, metrics_store, required_periods={period_end.strftime('%Y%m%d')})
    source_df = metrics_store.load_source(provider_used)
    sheet_df = build_metrics_sheet(source_df, metrics_df, period_end, provider_used)
    if sheet_df is None or sheet_df.empty:
        return None, provider_used
    return sheet_df, provider_used


def _infer_metrics_provider(requested_provider: str, used_provider_name: str | None) -> str:
    req = (requested_provider or "auto").strip().lower()
    if req in {"tushare", "akshare"}:
        return req
    used = (used_provider_name or "").strip().lower()
    if "tushare" in used:
        return "tushare"
    if "akshare" in used or used == "akshare_ths":
        return "akshare"
    return "auto"


def _fetch_one_period(
    ts_code: str,
    code6: str,
    company_name: str | None,
    period_end: date,
    statement_type: str,
    provider_pref: str,
    providers,
    want_pdf: bool,
    out_dir: Path,
    tushare_token: str | None,
    raw_store: RawReportStore | None,
) -> tuple[Path, str]:
    last_err: Exception | None = None
    bundle = None
    used_provider_name: str | None = None
    provider_errors: list[tuple[str, Exception]] = []

    for p in providers:
        pname = getattr(p, "name", p.__class__.__name__)
        try:
            bundle = p.get_bundle(
                ts_code=ts_code,
                period_end=period_end,
                statement_type=statement_type,
                raw_store=raw_store,
            )
            used_provider_name = str(getattr(bundle, "provider", None) or pname)
            break
        except Exception as e:
            last_err = e
            provider_errors.append((str(pname), e))
            log_debug(f"provider 失败，继续尝试下一个：{pname} => {_exc_short(e)}")
            continue

    if bundle is None:
        tried = ", ".join([n for n, _ in provider_errors]) or "<none>"
        # 错误信息尽量可读；详细堆栈请用 -l debug 重跑。
        brief = "; ".join([f"{n}=>{_exc_short(e)}" for n, e in provider_errors[:3]])
        more = "（更多错误请用 -l debug 查看）" if len(provider_errors) > 3 else ""
        raise RuntimeError(f"所有数据源均失败（已尝试：{tried}）。{brief}{more}" if brief else f"所有数据源均失败：{last_err}")

    used_provider_name = used_provider_name or str(getattr(bundle, "provider", None) or "unknown")

    pdf_url = None
    pdf_title = None
    pdf_note = None
    pdf_local_path = None
    if want_pdf:
        if raw_store:
            pdf_file = raw_store.pdf_path(code6, period_end)
            pdf_meta = raw_store.load_pdf_metadata(code6, period_end)
        else:
            pdf_root = out_dir.parent / "pdf"
            pdf_root.mkdir(parents=True, exist_ok=True)
            pdf_file = pdf_root / f"{code6}_{period_end.strftime('%Y%m%d')}.pdf"
            pdf_meta = None

        if pdf_file.exists():
            pdf_local_path = str(pdf_file)
            if pdf_meta:
                pdf_url = pdf_meta.get("url")
                pdf_title = pdf_meta.get("title")
                pdf_note = pdf_meta.get("note")
        else:
            pdf_res = find_and_download_period_pdf(code6=code6, period_end=period_end, out_path=pdf_file)
            if pdf_res.ok:
                pdf_url = pdf_res.url
                pdf_title = pdf_res.title
            else:
                pdf_note = pdf_res.note
                pdf_url = pdf_res.url
                pdf_title = pdf_res.title
            if pdf_file.exists():
                pdf_local_path = str(pdf_file)
            if raw_store:
                raw_store.save_pdf_metadata(
                    code6,
                    period_end,
                    {
                        "ok": pdf_res.ok,
                        "url": pdf_res.url,
                        "title": pdf_res.title,
                        "note": pdf_res.note,
                    },
                )

    bs = bundle.balance_sheet
    inc = bundle.income_statement
    cf = bundle.cashflow_statement

    fname = f"{code6}_{bundle.statement_type}_{period_end.strftime('%Y%m%d')}.xlsx"
    out_path = out_dir / fname

    meta = dict(bundle.meta)
    meta.update({
        "provider": bundle.provider,
        "provider_requested_order": [getattr(p, 'name', str(p)) for p in providers],
        "requested_statement_type": statement_type,
        "report_period_end": period_end.strftime("%Y-%m-%d"),
        "excel_schema_version": "1",
        "pdf_title": pdf_title,
        "pdf_url": pdf_url,
        "pdf_local_path": pdf_local_path,
        "pdf_note": pdf_note,
    })
    if used_provider_name in {"akshare", "akshare_ths"}:
        # 若用户请求合并但实际拿到母公司（或相反），在 meta 里说明（Sina only）
        detected = bundle.meta.get("detected_type")
        if detected:
            meta["statement_type_note"] = f"Sina 类型字段: {detected}"

    # 公司类别（用于“非通用科目”高亮与注释口径）
    cat = detect_company_category(
        ts_code=ts_code,
        name=company_name,
        tushare_token=tushare_token,
    )
    meta["company_category"] = cat.category
    if cat.industry:
        meta["company_industry"] = cat.industry
    meta["company_category_source"] = cat.source

    metrics_sheet_df = None
    metrics_provider_used = None
    try:
        metrics_sheet_df, metrics_provider_used = _load_metrics_sheet(
            ts_code=ts_code,
            code6=code6,
            company_name=company_name,
            period_end=period_end,
            provider=_infer_metrics_provider(provider_pref, used_provider_name),
            out_dir=out_dir,
            tushare_token=tushare_token,
            raw_store=raw_store,
        )
        if metrics_provider_used:
            meta["metrics_provider"] = metrics_provider_used
    except Exception as exc:
        meta["metrics_note"] = f"财报指标补充失败：{_exc_short(exc)}"
        log_warn(f"财报指标补充失败，继续导出三表：{company_name or code6} {period_end.strftime('%Y-%m-%d')} => {_exc_short(exc)}")

    export_bundle_to_excel(
        out_path,
        balance_sheet=bs,
        income_statement=inc,
        cashflow_statement=cf,
        metrics_statement=metrics_sheet_df,
        meta=meta,
        title_info={
            "code6": code6,
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "statement_type": bundle.statement_type,
            "provider": bundle.provider,
            "pdf_url": pdf_url,
            "pdf_path": pdf_local_path,
            "company_category": cat.category,
            "metrics_provider": metrics_provider_used,
        },
    )

    return out_path, used_provider_name


@app.command("fetch")
def fetch(
    code: str | None = typer.Option(None, "--code", help="股票代码：600519 / 600519.SH / sh600519 等"),
    name: str | None = typer.Option(None, "--name", help="股票名称（模糊匹配，重名会提示选择）"),
    category: str | None = typer.Option(None, "--category", help="公司分类名（见 config/company_categories.toml）"),
    category_config: Path | None = typer.Option(None, "--category-config", help="分类配置文件路径（默认：config/company_categories.toml）"),
    date_: str | None = typer.Option(None, "--date", help="单个日期：取该日期之前最近一期已披露的报告期"),
    start: str | None = typer.Option(None, "--start", help="日期范围开始"),
    end: str | None = typer.Option(None, "--end", help="日期范围结束"),
    provider: str = typer.Option("auto", "--provider", help="auto/tushare/akshare"),
    statement_type: str = typer.Option("merged", "--statement-type", help="merged(合并)/parent(母公司)"),
    pdf: bool = typer.Option(False, "--pdf", help="下载对应报告期 PDF 原文，并写入 Excel"),
    out_dir: Path = typer.Option(Path("output"), "--out", help="输出目录"),
    no_clean: bool = typer.Option(False, "--no-clean", help="不清空输出目录，改为增量写入（供图表程序补数据使用）"),
    update_raw: bool = typer.Option(False, "--update-raw", help="更新原始数据快照（保留旧快照）"),
    clear_raw: bool = typer.Option(False, "--clear-raw", help="清理旧原始数据快照，仅保留最新一版"),
    tushare_token: str | None = typer.Option(None, "--tushare-token", help="Tushare token（可选，未提供则尝试环境变量）"),
):
    """抓取 A 股三大报表并导出 Excel。"""

    if category and (code or name):
        raise typer.BadParameter("--category 与 --code/--name 互斥")
    if not category and not (code or name):
        raise typer.BadParameter("必须提供 --code/--name 或 --category")

    if statement_type not in {"merged", "parent"}:
        raise typer.BadParameter("--statement-type 仅支持 merged 或 parent")

    if date_ and (start or end):
        raise typer.BadParameter("--date 与 --start/--end 不能同时使用")
    if (start and not end) or (end and not start):
        raise typer.BadParameter("--start 与 --end 必须同时提供")
    if not update_raw and not clear_raw and not date_ and not (start and end):
        raise typer.BadParameter("必须提供 --date 或 --start/--end；若仅维护原始数据，可使用 --update-raw/--clear-raw")

    cfg = ProviderConfig(
        provider=provider,
        prefer_order=["tushare", "akshare_ths", "akshare"],
        tushare_token=tushare_token,
    )
    providers = build_providers(cfg)

    out_root = out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    def _resolve_category_targets() -> list[ResolvedSymbol]:
        cfg_path = category_config or default_company_categories_path()
        resolved = resolve_company_category_symbols(category, cfg_path)
        for msg in resolved.warnings:
            log_warn(msg)

        if resolved.category.alias:
            log_info(f"使用分类: {resolved.category.name}（{resolved.category.alias}），公司数: {len(resolved.symbols)}")
        else:
            log_info(f"使用分类: {resolved.category.name}，公司数: {len(resolved.symbols)}")

        return resolved.symbols

    maintenance_only = not date_ and not (start and end)

    targets: list[ResolvedSymbol]
    if category:
        targets = _resolve_category_targets()
    else:
        targets = [_resolve_symbol(code=code, name=name)]

    def _update_raw_for_symbol(rs: ResolvedSymbol, raw_store: RawReportStore, metrics_store: RawMetricsStore) -> str:
        last_err: Exception | None = None
        snapshot_id: str | None = None
        for p in providers:
            refresh = getattr(p, "refresh_raw_history", None)
            if callable(refresh):
                try:
                    snapshot_id = refresh(rs.ts_code, statement_type, raw_store)
                    log_info(f"已更新原始数据快照：{rs.name or rs.code6}({rs.code6}) provider={getattr(p, 'name', p)} snapshot={snapshot_id}")
                    break
                except Exception as exc:
                    last_err = exc
                    log_debug(f"update_raw 失败，继续尝试下一个 provider：{getattr(p, 'name', p)} => {_exc_short(exc)}")
                    continue
        if snapshot_id is None:
            raise RuntimeError(f"更新原始数据失败：{last_err}")

        metrics_provider = _infer_metrics_provider(provider, None)
        metrics_opts = MetricsCommonOpts(rs=rs, out_dir=out_root, provider=metrics_provider, tushare_token=tushare_token)
        metrics_provider_used, _metrics_df, metrics_sid = update_raw_metrics(metrics_opts, metrics_store)
        log_info(f"已更新指标原始数据：{rs.name or rs.code6}({rs.code6}) provider={metrics_provider_used} snapshot={metrics_sid}")
        return snapshot_id

    def _clear_raw_for_symbol(raw_store: RawReportStore, metrics_store: RawMetricsStore) -> None:
        all_providers = list(raw_store.available_providers())
        if not all_providers:
            log_info("未发现可清理的财报原始数据。")
        else:
            for pname in sorted(all_providers):
                removed = raw_store.clear_old_provider_snapshots(pname)
                if removed:
                    log_info(f"已清理 provider={pname} 旧原始快照 {len(removed)} 个")
                else:
                    log_info(f"provider={pname} 没有旧原始快照可清理。")

        clear_raw_metrics(metrics_store)

    def _fetch_for_symbol(rs: ResolvedSymbol) -> list[Path]:
        company_name = rs.name or rs.code6
        company_dirname = safe_dir_component(f"{company_name}_{rs.code6}")
        company_root = out_root / company_dirname
        out_reports_dir = company_root / "reports"
        out_reports_dir.mkdir(parents=True, exist_ok=True)
        raw_store = RawReportStore(company_root)
        metrics_store = RawMetricsStore(company_root)

        if update_raw:
            _update_raw_for_symbol(rs, raw_store, metrics_store)
        if clear_raw:
            _clear_raw_for_symbol(raw_store, metrics_store)

        if not no_clean:
            for p in out_reports_dir.glob(f"{rs.code6}_*.xlsx"):
                try:
                    p.unlink()
                except Exception:
                    pass
            for p in out_reports_dir.glob(f"~${rs.code6}_*.xlsx"):
                try:
                    p.unlink()
                except Exception:
                    pass

        exported: list[Path] = []

        if not date_ and not (start and end):
            return exported

        if date_:
            dt = parse_date(date_)
            candidates = candidate_quarter_ends_before(dt, years_back=10)
            last_err = None
            for pe in candidates:
                out_path0 = _expected_xlsx_path(out_reports_dir, rs.code6, statement_type, pe)
                if no_clean and out_path0.exists():
                    exported.append(out_path0)
                    log_info(f"已存在，跳过重生成：{out_path0}")
                    break
                try:
                    out_path, used_provider = _fetch_one_period(
                        ts_code=rs.ts_code,
                        code6=rs.code6,
                        company_name=rs.name,
                        period_end=pe,
                        statement_type=statement_type,
                        provider_pref=provider,
                        providers=providers,
                        want_pdf=pdf,
                        out_dir=out_reports_dir,
                        tushare_token=tushare_token,
                        raw_store=raw_store,
                    )
                    exported.append(out_path)
                    log_info(f"已导出: {out_path}（provider={used_provider}）")
                    break
                except Exception as e:
                    last_err = e
                    continue
            if not exported:
                raise RuntimeError(f"在 {dt} 之前未找到可用财报数据：{last_err}")
        else:
            s = parse_date(start)
            e = parse_date(end)
            periods = quarter_ends_between(s, e)
            if not periods:
                raise RuntimeError("日期范围内没有任何标准报告期末日（03-31/06-30/09-30/12-31）")
            failed: list[tuple[date, str]] = []
            for pe in periods:
                out_path0 = _expected_xlsx_path(out_reports_dir, rs.code6, statement_type, pe)
                if no_clean and out_path0.exists():
                    exported.append(out_path0)
                    log_info(f"已存在，跳过重生成：{out_path0}")
                    continue
                try:
                    out_path, used_provider = _fetch_one_period(
                        ts_code=rs.ts_code,
                        code6=rs.code6,
                        company_name=rs.name,
                        period_end=pe,
                        statement_type=statement_type,
                        provider_pref=provider,
                        providers=providers,
                        want_pdf=pdf,
                        out_dir=out_reports_dir,
                        tushare_token=tushare_token,
                        raw_store=raw_store,
                    )
                    exported.append(out_path)
                    log_info(f"已导出: {out_path}（provider={used_provider}）")
                except Exception as e:
                    failed.append((pe, str(e)))
                    log_warn(f"跳过 {pe.strftime('%Y-%m-%d')}：{e}")
                    continue

            if not exported:
                # 单行、可读：避免 rich traceback 自动换行导致补数日志只截到半句。
                if failed:
                    pe0, msg0 = failed[0]
                    raise RuntimeError(
                        f"范围内所有报告期均失败，共 {len(failed)} 期。示例：{pe0.strftime('%Y-%m-%d')} => {msg0}"
                    )
                raise RuntimeError(f"范围内所有报告期均失败，共 {len(failed)} 期。")

            if failed:
                # 这里属于“部分缺失但整体成功”的提示信息，不要用告警色刷屏
                log_info(f"提示：范围内有 {len(failed)} 期未能抓取（已跳过）。")
                for pe, msg in failed[:10]:
                    log_info(f"  - {pe.strftime('%Y-%m-%d')}: {msg}")
                if len(failed) > 10:
                    log_info("  ... 仅展示前 10 条")

        log_info(f"完成，共导出 {len(exported)} 个文件。输出目录: {out_reports_dir}")
        log_info(f"提示：公司根目录为 {out_reports_dir.parent}")
        return exported

    total_exported = 0
    failed_companies: list[tuple[ResolvedSymbol, Exception]] = []

    for rs in targets:
        if len(targets) > 1:
            log_info(f"\n[bold]公司[/bold]: {rs.name or rs.code6} ({rs.code6})")
        try:
            exported = _fetch_for_symbol(rs)
            total_exported += len(exported)
        except Exception as exc:
            failed_companies.append((rs, exc))
            log_warn(f"公司 {rs.name or rs.code6}({rs.code6}) 抓取失败：{exc}")

    # 只要有 1 个文件成功导出就算整体成功（其余公司失败会在下方提示）。
    # 如果全部失败：
    # - 单公司：抛出更具体的失败原因（便于 finreport_charts 的补数日志直接定位）
    # - 多公司：保留汇总错误
    if total_exported == 0 and not maintenance_only:
        if len(failed_companies) == 1:
            rs0, exc0 = failed_companies[0]
            raise RuntimeError(f"公司 {rs0.name or rs0.code6}({rs0.code6}) 抓取失败：{exc0}")
        raise RuntimeError("全部公司抓取失败，请检查配置或数据源")

    if failed_companies:
        log_warn(f"提示：{len(failed_companies)} 家公司抓取失败（其余已完成）。")
    elif maintenance_only:
        log_info("原始数据维护完成。")


def main():
    app()


if __name__ == "__main__":
    main()
