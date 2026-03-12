from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import IntPrompt

from .exporter.excel import export_bundle_to_excel
from .pdf.cninfo import find_and_download_period_pdf
from .providers.registry import ProviderConfig, build_providers
from .utils.dates import candidate_quarter_ends_before, parse_date, quarter_ends_between
from .utils.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code

app = typer.Typer(add_completion=False)
fetch_app = typer.Typer(add_completion=False)
app.add_typer(fetch_app, name="fetch", help="抓取财报并导出 Excel")

console = Console()


def _resolve_symbol(code: str | None, name: str | None) -> ResolvedSymbol:
    if code and name:
        raise typer.BadParameter("--code 与 --name 只能二选一")

    if code:
        rs = parse_code(code)
        if not rs:
            raise typer.BadParameter(f"无法解析股票代码格式: {code}")
        return rs

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

    # PDF
    pdf_url = None
    pdf_path = None
    pdf_note = None
    if want_pdf:
        pdf_dir = out_dir / "pdf" / code6 / period_end.strftime("%Y%m%d")
        pdf_res = find_and_download_period_pdf(code6=code6, period_end=period_end, out_dir=pdf_dir)
        if pdf_res.ok:
            pdf_url = pdf_res.url
            pdf_path = pdf_res.local_path
        else:
            pdf_note = pdf_res.note
            pdf_url = pdf_res.url

    # 将 PDF 信息附加到三张表（每张表都带一列，方便你单独看）
    def add_pdf_cols(df):
        df2 = df.copy()
        if want_pdf:
            df2["PDF链接"] = pdf_url
            df2["PDF本地路径"] = pdf_path
            df2["PDF备注"] = pdf_note
        return df2

    bs = add_pdf_cols(bundle.balance_sheet)
    inc = add_pdf_cols(bundle.income_statement)
    cf = add_pdf_cols(bundle.cashflow_statement)

    fname = f"{code6}_{bundle.statement_type}_{period_end.strftime('%Y%m%d')}.xlsx"
    out_path = out_dir / fname

    meta = dict(bundle.meta)
    meta.update({
        "provider": bundle.provider,
        "provider_requested_order": [getattr(p, 'name', str(p)) for p in providers],
        "requested_statement_type": statement_type,
    })
    if used_provider and getattr(used_provider, "name", None) == "akshare":
        # 若用户请求合并但实际拿到母公司（或相反），在 meta 里说明
        detected = bundle.meta.get("detected_type")
        if detected:
            meta["statement_type_note"] = f"Sina 类型字段: {detected}"

    export_bundle_to_excel(out_path, bs, inc, cf, meta)

    return out_path


@fetch_app.command("run")
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

    cfg = ProviderConfig(provider=provider, prefer_order=["tushare", "akshare"], tushare_token=tushare_token)
    providers = build_providers(cfg)

    out_dir.mkdir(parents=True, exist_ok=True)

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
                console.print(f"已导出: {p}")
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
        for pe in periods:
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
            console.print(f"已导出: {p}")

    console.print(f"完成，共导出 {len(exported)} 个文件。输出目录: {out_dir}")


def main():
    app()


if __name__ == "__main__":
    main()
