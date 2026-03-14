from __future__ import annotations

import warnings
from datetime import date
from enum import IntEnum
from pathlib import Path

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import typer
from rich.console import Console
from rich.prompt import IntPrompt

from .exporter.excel import export_bundle_to_excel
from .pdf.cninfo import find_and_download_period_pdf
from .providers.registry import ProviderConfig, build_providers
from .utils.dates import candidate_quarter_ends_before, parse_date, quarter_ends_between
from .utils.paths import safe_dir_component
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



def _fetch_one_period(
    ts_code: str,
    code6: str,
    period_end: date,
    statement_type: str,
    providers,
    want_pdf: bool,
    out_dir: Path,
):
    last_err = None
    bundle = None
    used_provider = None
    for p in providers:
        try:
            bundle = p.get_bundle(ts_code=ts_code, period_end=period_end, statement_type=statement_type)
            used_provider = p
            break
        except Exception as e:
            last_err = e
            continue

    if bundle is None:
        raise RuntimeError(f"所有数据源均失败：{last_err}")

    # PDF（不用日期文件夹，用文件名区分）
    pdf_url = None
    pdf_path = None
    pdf_title = None
    pdf_note = None
    if want_pdf:
        # PDF 单独放到公司目录下的 pdf/ 子目录（与 reports 同级）
        pdf_root = out_dir.parent / "pdf"
        pdf_root.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_root / f"{code6}_{period_end.strftime('%Y%m%d')}.pdf"
        pdf_res = find_and_download_period_pdf(code6=code6, period_end=period_end, out_path=pdf_file)
        if pdf_res.ok:
            pdf_url = pdf_res.url
            pdf_path = pdf_res.local_path
            pdf_title = pdf_res.title
        else:
            pdf_note = pdf_res.note
            pdf_url = pdf_res.url
            pdf_title = pdf_res.title

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
        "pdf_local_path": pdf_path,
        "pdf_note": pdf_note,
    })
    if used_provider and getattr(used_provider, "name", None) in {"akshare", "akshare_ths"}:
        # 若用户请求合并但实际拿到母公司（或相反），在 meta 里说明（Sina only）
        detected = bundle.meta.get("detected_type")
        if detected:
            meta["statement_type_note"] = f"Sina 类型字段: {detected}"

    export_bundle_to_excel(
        out_path,
        balance_sheet=bs,
        income_statement=inc,
        cashflow_statement=cf,
        meta=meta,
        title_info={
            "code6": code6,
            "ts_code": ts_code,
            "period_end": period_end.strftime("%Y-%m-%d"),
            "statement_type": bundle.statement_type,
            "provider": bundle.provider,
            "pdf_url": pdf_url,
            "pdf_path": pdf_path,
        },
    )

    return out_path


@app.command("fetch")
def fetch(
    code: str | None = typer.Option(None, "--code", help="股票代码：600519 / 600519.SH / sh600519 等"),
    name: str | None = typer.Option(None, "--name", help="股票名称（模糊匹配，重名会提示选择）"),
    date_: str | None = typer.Option(None, "--date", help="单个日期：取该日期之前最近一期已披露的报告期"),
    start: str | None = typer.Option(None, "--start", help="日期范围开始"),
    end: str | None = typer.Option(None, "--end", help="日期范围结束"),
    provider: str = typer.Option("auto", "--provider", help="auto/tushare/akshare"),
    statement_type: str = typer.Option("merged", "--statement-type", help="merged(合并)/parent(母公司)"),
    pdf: bool = typer.Option(False, "--pdf", help="下载对应报告期 PDF 原文，并写入 Excel"),
    out_dir: Path = typer.Option(Path("output"), "--out", help="输出目录"),
    no_clean: bool = typer.Option(False, "--no-clean", help="不清空输出目录，改为增量写入（供图表程序补数据使用）"),
    tushare_token: str | None = typer.Option(None, "--tushare-token", help="Tushare token（可选，未提供则尝试环境变量）"),
):
    """抓取 A 股三大报表并导出 Excel。"""

    rs = _resolve_symbol(code=code, name=name)
    if statement_type not in {"merged", "parent"}:
        raise typer.BadParameter("--statement-type 仅支持 merged 或 parent")

    if date_ and (start or end):
        raise typer.BadParameter("--date 与 --start/--end 不能同时使用")
    if (start and not end) or (end and not start):
        raise typer.BadParameter("--start 与 --end 必须同时提供")
    if not date_ and not (start and end):
        raise typer.BadParameter("必须提供 --date 或 --start/--end")

    cfg = ProviderConfig(
        provider=provider,
        prefer_order=["tushare", "akshare_ths", "akshare"],
        tushare_token=tushare_token,
    )
    providers = build_providers(cfg)

    # 每次提取前删除之前的数据：仅删除本次公司(code6)相关文件，不影响其他公司
    out_root = out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    company_name = rs.name or rs.code6
    company_dirname = safe_dir_component(f"{company_name}_{rs.code6}")
    out_dir = out_root / company_dirname / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not no_clean:
        # 只清理本公司目录内的本公司文件
        for p in out_dir.glob(f"{rs.code6}_*.xlsx"):
            try:
                p.unlink()
            except Exception:
                pass
        for p in out_dir.glob(f"~${rs.code6}_*.xlsx"):
            try:
                p.unlink()
            except Exception:
                pass

        pdf_dir = out_dir.parent / "pdf"
        if pdf_dir.exists():
            for p in pdf_dir.glob(f"{rs.code6}_*.pdf"):
                try:
                    p.unlink()
                except Exception:
                    pass

    exported: list[Path] = []

    if date_:
        dt = parse_date(date_)
        # 候选报告期末：倒序尝试，哪个先拿到数据就算“最近一期已披露”
        candidates = candidate_quarter_ends_before(dt, years_back=10)
        last_err = None
        for pe in candidates:
            try:
                p = _fetch_one_period(
                    ts_code=rs.ts_code,
                    code6=rs.code6,
                    period_end=pe,
                    statement_type=statement_type,
                    providers=providers,
                    want_pdf=pdf,
                    out_dir=out_dir,
                )
                exported.append(p)
                log_info(f"已导出: {p}")
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
            try:
                p = _fetch_one_period(
                    ts_code=rs.ts_code,
                    code6=rs.code6,
                    period_end=pe,
                    statement_type=statement_type,
                    providers=providers,
                    want_pdf=pdf,
                    out_dir=out_dir,
                )
                exported.append(p)
                log_info(f"已导出: {p}")
            except Exception as e:
                failed.append((pe, str(e)))
                log_warn(f"跳过 {pe.strftime('%Y-%m-%d')}：{e}")
                continue

        if not exported:
            raise RuntimeError(f"范围内所有报告期均失败，共 {len(failed)} 期。示例错误: {failed[0] if failed else 'N/A'}")

        if failed:
            log_warn(f"提示：范围内有 {len(failed)} 期未能抓取（已跳过）。")
            for pe, msg in failed[:10]:
                log_warn(f"  - {pe.strftime('%Y-%m-%d')}: {msg}")
            if len(failed) > 10:
                log_warn("  ... 仅展示前 10 条")

    log_info(f"完成，共导出 {len(exported)} 个文件。输出目录: {out_dir}")
    log_info(f"提示：公司根目录为 {out_dir.parent}")


def main():
    app()


if __name__ == "__main__":
    main()
