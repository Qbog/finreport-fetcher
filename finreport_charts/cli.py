from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console
from rich.prompt import IntPrompt

from finreport_fetcher.utils.dates import parse_date, quarter_ends_between
from finreport_fetcher.utils.paths import safe_dir_component
from finreport_fetcher.utils.symbols import (
    ResolvedSymbol,
    fuzzy_match_name,
    load_a_share_name_map,
    parse_code,
)

from .charts.bar_trend import render_bar_png, render_bars_png, write_bar_excel, write_bars_excel
from .charts.combo_dual_axis import render_combo_png, write_combo_excel
from .charts.pie_share import render_pie_png, topn_with_other, write_pie_excel
from .data.finreport_store import (
    ensure_finreports,
    expected_pdf_path,
    expected_xlsx_path,
    get_item_value,
    get_section_items,
    load_price_csv,
    price_on_or_before,
    read_statement_df,
)
from .templates.config import load_template_dir, load_template_file, load_templates
from .utils.expr import ExprError, eval_expr, tokenize
from .utils.files import safe_slug
from .utils.ttm import quarter_from_ytd, ttm_from_ytd

app = typer.Typer(add_completion=False)
console = Console()


@dataclass(frozen=True)
class CommonOpts:
    rs: ResolvedSymbol
    start: date
    end: date
    data_dir: Path
    out_dir: Path
    provider: str
    statement_type: str
    pdf: bool
    tushare_token: str | None


def _resolve_symbol(code: str | None, name: str | None) -> ResolvedSymbol:
    if code and name:
        raise typer.BadParameter("--code 与 --name 只能二选一")

    if code:
        rs0 = parse_code(code)
        if not rs0:
            raise typer.BadParameter(f"无法解析股票代码格式: {code}")

        # Fill official name if possible（用于公司目录名/默认输出目录）
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
        show_n = min(30, len(cand))
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


def _common(
    code: str | None,
    name: str | None,
    start: str,
    end: str,
    data_dir: Path,
    out_dir: Path,
    provider: str,
    statement_type: str,
    pdf: bool,
    tushare_token: str | None,
) -> CommonOpts:
    rs = _resolve_symbol(code=code, name=name)
    s = parse_date(start)
    e = parse_date(end)

    if statement_type not in {"merged", "parent"}:
        raise typer.BadParameter("--statement-type 仅支持 merged 或 parent")

    return CommonOpts(
        rs=rs,
        start=s,
        end=e,
        data_dir=data_dir.resolve(),
        out_dir=out_dir.resolve(),
        provider=provider,
        statement_type=statement_type,
        pdf=pdf,
        tushare_token=tushare_token,
    )


def _maybe_fetch_missing(c: CommonOpts, fetch_start: date | None = None):
    # 检测缺失的报告期文件（TTM 等场景可能需要 start 之前的历史期）
    check_start = fetch_start or c.start
    periods = quarter_ends_between(check_start, c.end)
    missing = [
        pe
        for pe in periods
        if not expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name).exists()
    ]

    if not missing:
        return

    fs = fetch_start or c.start
    console.print(f"发现缺失财报 {len(missing)} 期，调用 finreport_fetcher 补齐到: {c.data_dir}")
    still = ensure_finreports(
        code_or_name_args=["--code", c.rs.code6],
        code6=c.rs.code6,
        start=fs,
        end=c.end,
        data_dir=c.data_dir,
        provider=c.provider,
        statement_type=c.statement_type,
        pdf=c.pdf,
        company_name=c.rs.name,
        tushare_token=c.tushare_token,
    )
    if still:
        raise RuntimeError(f"补齐后仍缺失 {len(still)} 期财报: {still}")


@app.callback()
def _root():
    """基于 finreport_fetcher 输出，生成漂亮的财务图表（PNG + Excel(含原始数据+Excel图表)）。"""


@app.command("bar")
def bar_trend(
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    statement: str = typer.Option("利润表", "--statement", help="资产负债表/利润表/现金流量表"),
    item: str = typer.Option("营业总收入", "--item", help="科目精确匹配"),
    item_like: str | None = typer.Option(None, "--item-like", help="科目模糊匹配（正则/包含）"),
    transform: str = typer.Option("ttm", "--transform", help="ttm/ytd/q（raw 视为 ytd）"),
    data_dir: Path = typer.Option(Path("output"), "--data-dir"),
    out_dir: Path = typer.Option(Path("charts_output"), "--out"),
    provider: str = typer.Option("auto", "--provider"),
    statement_type: str = typer.Option("merged", "--statement-type"),
    pdf: bool = typer.Option(False, "--pdf"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    """财务科目趋势柱状图（默认转换为 TTM）。

    ⚠️ 已弃用：请使用 `finreport_charts run` + `templates/*.toml`。
    """

    console.print("[yellow]此命令已弃用：请使用 `python3 -m finreport_charts run`（模板驱动）[/yellow]")
    raise typer.Exit(code=2)

    c = _common(code, name, start, end, data_dir, out_dir, provider, statement_type, pdf, tushare_token)

    # 口径：
    # - ttm：需要上一年数据（从上一年 1/1 补齐）
    # - q：需要同一年内上一季度（从当年 1/1 补齐）
    # - ytd/raw：只需要范围内
    t = "ytd" if transform == "raw" else transform
    if t == "ttm":
        fetch_start = date(c.start.year - 1, 1, 1)
    elif t == "q":
        fetch_start = date(c.start.year, 1, 1)
    else:
        fetch_start = c.start

    _maybe_fetch_missing(c, fetch_start=fetch_start)

    periods = quarter_ends_between(c.start, c.end)

    series_ytd: dict[date, float] = {}
    for pe in quarter_ends_between(fetch_start, c.end):
        xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
        if not xlsx.exists():
            continue

        # item_like 支持：优先精确；否则正则/包含
        if item_like:
            df = pd.read_excel(xlsx, sheet_name=statement, header=2)
            subj_col = "科目"
            df = df[[subj_col, "数值"]].copy()

            # 兼容“中文 (English)”显示列：用于打印时可读，但匹配时用中文部分
            subj = df["科目"].astype(str)
            subj_cn = subj.str.split(" (", n=1).str[0]
            # regex first (match on CN part)
            try:
                m = subj_cn.str.contains(item_like, regex=True, na=False)
            except Exception:
                m = subj_cn.str.contains(item_like, regex=False, na=False)
            sub = df[m]
            if sub.empty:
                continue
            v = sub.iloc[0]["数值"]
        else:
            v = get_item_value(xlsx, statement, item)

        if v is None:
            continue
        series_ytd[pe] = float(v)

    # 输出范围内数据（支持 q/ytd/ttm）
    rows = []
    for pe in periods:
        y_raw = series_ytd.get(pe)
        if y_raw is None:
            rows.append({"period_end": pe.strftime("%Y-%m-%d"), "value": None})
            continue

        if t == "ttm":
            y = ttm_from_ytd(pe, series_ytd)
        elif t == "q":
            y = quarter_from_ytd(pe, series_ytd)
        else:
            y = y_raw
        rows.append({"period_end": pe.strftime("%Y-%m-%d"), "value": y})

    df_out = pd.DataFrame(rows)

    title = f"{c.rs.code6} {statement}.{item if not item_like else item_like} 趋势 ({t.upper()})"
    base = safe_slug(f"bar_{statement}_{item if not item_like else item_like}")
    out_png = c.out_dir / f"{base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
    out_xlsx = c.out_dir / f"{base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

    render_bar_png(df_out.dropna(), title=title, x_col="period_end", y_col="value", out_png=out_png, y_label="金额")
    write_bar_excel(df_out.dropna(), title=title, x_col="period_end", y_col="value", out_xlsx=out_xlsx, y_label="金额")

    console.print(f"已生成: {out_png}")
    console.print(f"已生成: {out_xlsx}")


@app.command("pie")
def pie_share(
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    statement: str = typer.Option("资产负债表", "--statement"),
    section: str | None = typer.Option(None, "--section", help="按分组标题取子项做饼图"),
    items: str | None = typer.Option(None, "--items", help="手动指定科目列表，用逗号分隔"),
    top_n: int = typer.Option(10, "--top-n"),
    data_dir: Path = typer.Option(Path("output"), "--data-dir"),
    out_dir: Path = typer.Option(Path("charts_output"), "--out"),
    provider: str = typer.Option("auto", "--provider"),
    statement_type: str = typer.Option("merged", "--statement-type"),
    pdf: bool = typer.Option(False, "--pdf"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    """同型分析饼图：范围内每期一张。

    ⚠️ 已弃用：请使用 `finreport_charts run` + `templates/*.toml`。
    """

    console.print("[yellow]此命令已弃用：请使用 `python3 -m finreport_charts run`（模板驱动）[/yellow]")
    raise typer.Exit(code=2)

    if not section and not items:
        raise typer.BadParameter("必须提供 --section 或 --items")

    c = _common(code, name, start, end, data_dir, out_dir, provider, statement_type, pdf, tushare_token)
    _maybe_fetch_missing(c)

    periods = quarter_ends_between(c.start, c.end)
    item_list = [x.strip() for x in items.split(",")] if items else None

    for pe in periods:
        xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
        if not xlsx.exists():
            continue

        if section:
            raw_items = get_section_items(xlsx, statement, section)
        else:
            raw_items = []
            for it in item_list or []:
                v = get_item_value(xlsx, statement, it)
                if v is None:
                    continue
                raw_items.append((it, v))

        items_top = topn_with_other(raw_items, top_n=top_n)
        if not items_top:
            continue

        t = section if section else "items"
        title = f"{c.rs.code6} {statement}.{t} 占比 | {pe.strftime('%Y-%m-%d')}"
        base = safe_slug(f"pie_{statement}_{section or 'items'}")
        out_png = c.out_dir / f"{base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
        out_xlsx = c.out_dir / f"{base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

        render_pie_png(items_top, title=title, out_png=out_png)
        write_pie_excel(items_top, title=title, out_xlsx=out_xlsx)

    console.print(f"完成。输出目录: {c.out_dir}")


@app.command("combo")
def combo_dual_axis(
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    statement: str = typer.Option("利润表", "--statement"),
    bar_item: str = typer.Option("营业总收入", "--bar-item"),
    bar_transform: str = typer.Option("ttm", "--bar-transform", help="ttm/ytd/q（raw 视为 ytd）"),
    price_csv: Path | None = typer.Option(None, "--price-csv", help="股价CSV（列: date, close）"),
    data_dir: Path = typer.Option(Path("output"), "--data-dir"),
    out_dir: Path = typer.Option(Path("charts_output"), "--out"),
    provider: str = typer.Option("auto", "--provider"),
    statement_type: str = typer.Option("merged", "--statement-type"),
    pdf: bool = typer.Option(False, "--pdf"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    """双轴合并图：财务柱状 + 股价折线（收盘价）。

    ⚠️ 已弃用：请使用 `finreport_charts run` + `templates/*.toml`。
    """

    console.print("[yellow]此命令已弃用：请使用 `python3 -m finreport_charts run`（模板驱动）[/yellow]")
    raise typer.Exit(code=2)

    c = _common(code, name, start, end, data_dir, out_dir, provider, statement_type, pdf, tushare_token)

    bt = "ytd" if bar_transform == "raw" else bar_transform
    if bt == "ttm":
        fetch_start = date(c.start.year - 1, 1, 1)
    elif bt == "q":
        fetch_start = date(c.start.year, 1, 1)
    else:
        fetch_start = c.start
    _maybe_fetch_missing(c, fetch_start=fetch_start)

    if price_csv is None:
        price_csv = c.data_dir / "price" / f"{c.rs.code6}.csv"

    if not price_csv.exists():
        raise RuntimeError(f"未找到股价 CSV: {price_csv}")

    df_price = load_price_csv(price_csv)

    periods = quarter_ends_between(c.start, c.end)

    # 财务序列
    ytd_map: dict[date, float] = {}
    for pe in quarter_ends_between(fetch_start, c.end):
        xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
        if not xlsx.exists():
            continue
        v = get_item_value(xlsx, statement, bar_item)
        if v is None:
            continue
        ytd_map[pe] = float(v)

    rows = []
    for pe in periods:
        v_raw = ytd_map.get(pe)
        if v_raw is None:
            continue
        if bt == "ttm":
            v = ttm_from_ytd(pe, ytd_map)
        elif bt == "q":
            v = quarter_from_ytd(pe, ytd_map)
        else:
            v = v_raw
        px = price_on_or_before(df_price, pe)
        rows.append({"period_end": pe.strftime("%Y-%m-%d"), "amount": v, "close": px})

    df = pd.DataFrame(rows).dropna(subset=["amount", "close"])

    title = f"{c.rs.code6} {statement}.{bar_item} ({bar_transform.upper()}) + 股价(收盘)"
    base = safe_slug(f"combo_{statement}_{bar_item}_close")
    out_png = c.out_dir / f"{base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
    out_xlsx = c.out_dir / f"{base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

    render_combo_png(
        df,
        title=title,
        x_col="period_end",
        bar_col="amount",
        line_col="close",
        out_png=out_png,
        bar_label="金额",
        line_label="收盘价",
    )
    write_combo_excel(
        df,
        title=title,
        x_col="period_end",
        bar_col="amount",
        line_col="close",
        out_xlsx=out_xlsx,
        bar_label="金额",
        line_label="收盘价",
    )

    console.print(f"已生成: {out_png}")
    console.print(f"已生成: {out_xlsx}")


@app.command("template")
def run_template(
    type_: str = typer.Option(..., "--type", help="模板名"),
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    config: Path = typer.Option(Path("charts.toml"), "--config"),
    data_dir: Path = typer.Option(Path("output"), "--data-dir"),
    out_dir: Path = typer.Option(Path("charts_output"), "--out"),
    provider: str = typer.Option("auto", "--provider"),
    statement_type: str = typer.Option("merged", "--statement-type"),
    pdf: bool = typer.Option(False, "--pdf"),
    top_n: int | None = typer.Option(None, "--top-n", help="覆盖模板 top_n"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    """按 TOML 模板生成图表（文件名优先使用 alias）。

    ⚠️ 已弃用：请使用 `finreport_charts run` + 单模板单文件（`templates/*.toml`）。
    """

    console.print("[yellow]此命令已弃用：请使用 `python3 -m finreport_charts run`（单模板单文件）[/yellow]")
    raise typer.Exit(code=2)

    templates = load_templates(config)
    if type_ not in templates:
        raise typer.BadParameter(f"未找到模板: {type_}")

    tpl = templates[type_]
    c = _common(code, name, start, end, data_dir, out_dir, provider, statement_type, pdf, tushare_token)

    fname_base = safe_slug(tpl.alias or tpl.name)

    if tpl.chart == "bar":
        # 复用 bar 命令逻辑，但使用文件名 base
        statement = tpl.statement or "利润表"
        item = tpl.item or "营业总收入"
        transform = tpl.transform or "ttm"
        t2 = "ytd" if transform == "raw" else transform
        if t2 == "ttm":
            fetch_start = date(c.start.year - 1, 1, 1)
        elif t2 == "q":
            fetch_start = date(c.start.year, 1, 1)
        else:
            fetch_start = c.start
        _maybe_fetch_missing(c, fetch_start=fetch_start)

        periods = quarter_ends_between(c.start, c.end)

        series_ytd: dict[date, float] = {}
        for pe in quarter_ends_between(fetch_start, c.end):
            xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
            if not xlsx.exists():
                continue
            v = get_item_value(xlsx, statement, item)
            if v is None:
                continue
            series_ytd[pe] = float(v)

        rows = []
        for pe in periods:
            y_raw = series_ytd.get(pe)
            if y_raw is None:
                continue
            if t2 == "ttm":
                y = ttm_from_ytd(pe, series_ytd)
            elif t2 == "q":
                y = quarter_from_ytd(pe, series_ytd)
            else:
                y = y_raw
            rows.append({"period_end": pe.strftime("%Y-%m-%d"), "value": y})

        df_out = pd.DataFrame(rows)
        title = f"{c.rs.code6} {statement}.{item} 趋势 ({transform.upper()})"

        out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
        out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

        render_bar_png(df_out, title=title, x_col="period_end", y_col="value", out_png=out_png, y_label="金额")
        write_bar_excel(df_out, title=title, x_col="period_end", y_col="value", out_xlsx=out_xlsx, y_label="金额")

        console.print(f"已生成: {out_png}")
        console.print(f"已生成: {out_xlsx}")
        return

    if tpl.chart == "pie":
        statement = tpl.statement or "资产负债表"
        t_section = tpl.section
        t_items = tpl.items
        n = top_n if top_n is not None else (tpl.top_n or 10)

        if not t_section and not t_items:
            raise RuntimeError("pie 模板需要 section 或 items")

        _maybe_fetch_missing(c)
        periods = quarter_ends_between(c.start, c.end)

        for pe in periods:
            xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
            if not xlsx.exists():
                continue

            if t_section:
                raw_items = get_section_items(xlsx, statement, t_section)
            else:
                raw_items = []
                for it in t_items or []:
                    v = get_item_value(xlsx, statement, it)
                    if v is None:
                        continue
                    raw_items.append((it, v))

            items_top = topn_with_other(raw_items, top_n=n)
            if not items_top:
                continue

            title = f"{c.rs.code6} {statement}.{t_section or tpl.name} 占比 | {pe.strftime('%Y-%m-%d')}"
            out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
            out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

            render_pie_png(items_top, title=title, out_png=out_png)
            write_pie_excel(items_top, title=title, out_xlsx=out_xlsx)

        console.print(f"完成。输出目录: {c.out_dir}")
        return

    if tpl.chart == "combo":
        statement = tpl.statement or "利润表"
        bar_item = tpl.bar_item or tpl.item or "营业总收入"
        transform = tpl.transform or "ttm"
        t3 = "ytd" if transform == "raw" else transform
        if t3 == "ttm":
            fetch_start = date(c.start.year - 1, 1, 1)
        elif t3 == "q":
            fetch_start = date(c.start.year, 1, 1)
        else:
            fetch_start = c.start
        _maybe_fetch_missing(c, fetch_start=fetch_start)

        price_csv = c.data_dir / "price" / f"{c.rs.code6}.csv"
        if not price_csv.exists():
            raise RuntimeError(f"未找到股价 CSV: {price_csv}")

        df_price = load_price_csv(price_csv)
        periods = quarter_ends_between(c.start, c.end)

        ytd_map: dict[date, float] = {}
        for pe in quarter_ends_between(fetch_start, c.end):
            xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
            if not xlsx.exists():
                continue
            v = get_item_value(xlsx, statement, bar_item)
            if v is None:
                continue
            ytd_map[pe] = float(v)

        rows = []
        for pe in periods:
            v_raw = ytd_map.get(pe)
            if v_raw is None:
                continue
            if t3 == "ttm":
                v = ttm_from_ytd(pe, ytd_map)
            elif t3 == "q":
                v = quarter_from_ytd(pe, ytd_map)
            else:
                v = v_raw
            px = price_on_or_before(df_price, pe)
            rows.append({"period_end": pe.strftime("%Y-%m-%d"), "amount": v, "close": px})

        df = pd.DataFrame(rows).dropna(subset=["amount", "close"])
        title = f"{c.rs.code6} {statement}.{bar_item} ({transform.upper()}) + 股价(收盘)"

        out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
        out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

        render_combo_png(df, title=title, x_col="period_end", bar_col="amount", line_col="close", out_png=out_png, bar_label="金额", line_label="收盘价")
        write_combo_excel(df, title=title, x_col="period_end", bar_col="amount", line_col="close", out_xlsx=out_xlsx, bar_label="金额", line_label="收盘价")

        console.print(f"已生成: {out_png}")
        console.print(f"已生成: {out_xlsx}")
        return

    raise RuntimeError(f"暂不支持的模板 chart 类型: {tpl.chart}")


@app.command("run")
def run(
    template: list[str] = typer.Option(
        [],
        "--template",
        help="模板文件/模板名（可重复）。支持 '*' 表示运行模板目录下全部模板。",
        show_default=False,
    ),
    templates: Path = typer.Option(Path("templates"), "--templates", help="模板目录（单模板单文件 *.toml）"),
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    start: str = typer.Option(..., "--start", help="趋势分析必须提供时间范围；比较分析也可复用该范围"),
    end: str = typer.Option(..., "--end"),
    as_of: str | None = typer.Option(None, "--as-of", help="比较分析使用的报告期末日（YYYY-MM-DD）。不传则取 end 对应的最近一个季末"),
    period: str | None = typer.Option(
        None,
        "--period",
        "--period-ends",
        help="仅过滤绘图输出的报告期（例如: q4,q2 或 half 或 0630,1231；不影响自动补数/取数）",
    ),
    data_dir: Path | None = typer.Option(None, "--data-dir", help="财报数据目录（默认：若 ./output 存在则用 output，否则用当前目录）"),
    out_dir: Path | None = typer.Option(None, "--out", help="输出目录（默认：{data_dir}/{公司名}_{code6}/charts/）"),
    provider: str = typer.Option("auto", "--provider"),
    statement_type: str = typer.Option("merged", "--statement-type"),
    pdf: bool = typer.Option(False, "--pdf"),
    top_n: int | None = typer.Option(None, "--top-n", help="覆盖模板的 top_n（常用于 pie）"),
    list_only: bool = typer.Option(False, "--list", help="仅列出将要运行的模板并退出"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
):
    """模板驱动的图表生成（唯一推荐方式）。

    模板要求（你的约束）：
    - 必须有：type(类型)、title(标题)、x_label/y_label（坐标轴显示名，bar/combo 使用）
    - bar 需要 mode：trend（趋势分析）/ compare（比较分析）
    - bar 的每根柱都通过 [[bars]] 配置块描述，支持 expr 表达式（key + +-*/()）

    运行规则：
    - 不传 --template 或传入 '*'：运行 --templates 目录下全部模板
    - 传入 --template：仅运行指定模板（可重复）
    """

    rs = _resolve_symbol(code=code, name=name)
    s = parse_date(start)
    e = parse_date(end)

    if statement_type not in {"merged", "parent"}:
        raise typer.BadParameter("--statement-type 仅支持 merged 或 parent")

    if data_dir is None:
        data_dir = Path("output") if Path("output").exists() else Path(".")
    data_dir = data_dir.resolve()

    company_dir = data_dir / safe_dir_component(f"{(rs.name or rs.code6)}_{rs.code6}")
    if out_dir is None:
        out_dir = company_dir / "charts"
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    c = CommonOpts(
        rs=rs,
        start=s,
        end=e,
        data_dir=data_dir,
        out_dir=out_dir,
        provider=provider,
        statement_type=statement_type,
        pdf=pdf,
        tushare_token=tushare_token,
    )

    def _parse_period(v: str | None) -> set[str] | None:
        if not v:
            return None
        vv = v.strip().lower()
        if not vv:
            return None

        qmap = {
            "q1": "0331",
            "q2": "0630",
            "q3": "0930",
            "q4": "1231",
        }
        if vv in qmap:
            return {qmap[vv]}
        if vv in {"half", "hy"}:
            return {"0630", "1231"}

        parts = re.split(r"[\s,]+", vv)
        out: set[str] = set()
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if p in qmap:
                out.add(qmap[p])
                continue
            if p in {"half", "hy"}:
                out.update({"0630", "1231"})
                continue

            p = p.replace("-", "")
            if len(p) == 8 and p.isdigit():
                p = p[4:]
            if len(p) != 4 or (not p.isdigit()):
                raise typer.BadParameter(f"--period 无法解析: {v}")
            out.add(p)
        return out

    pe_filter = _parse_period(period)

    def _filter_periods(periods: list[date]) -> list[date]:
        if not pe_filter:
            return periods
        return [pe for pe in periods if pe.strftime('%m%d') in pe_filter]

    # 1) load templates
    selected: dict[str, object] = {}

    def _resolve_tpl_path(s0: str) -> Path:
        p = Path(s0)
        cands: list[Path] = []
        if p.suffix != ".toml":
            cands.append(p.with_suffix(".toml"))
        cands.append(p)
        base = p.name
        cands.append(templates / base)
        if not base.endswith(".toml"):
            cands.append(templates / f"{base}.toml")
        for pp in cands:
            if pp.exists() and pp.is_file():
                return pp
        raise FileNotFoundError(f"未找到模板文件: {s0}（已尝试: {', '.join(str(x) for x in cands)}）")

    # '*' means all templates
    if template and any(t.strip() == "*" for t in template):
        template = []

    if template:
        for t in template:
            p = _resolve_tpl_path(t)
            tpl = load_template_file(p)
            selected[tpl.name] = tpl
    else:
        selected = load_template_dir(templates)

    if not selected:
        raise RuntimeError("未加载到任何模板")

    if list_only:
        console.print("将运行以下模板：")
        for k in selected.keys():
            console.print(f"  - {k}")
        return

    # helpers
    def _latest_quarter_end_on_or_before(d: date) -> date:
        # search back up to 2 years
        start0 = date(d.year - 2, 1, 1)
        qs = quarter_ends_between(start0, d)
        if not qs:
            raise RuntimeError(f"无法从日期推断季末: {d}")
        return qs[-1]

    def _value_map_for_statement(xlsx: Path, statement: str) -> dict[str, float]:
        df = read_statement_df(xlsx, sheet_name=statement)
        m: dict[str, float] = {}
        if "key" not in df.columns:
            return m
        for k2, v2 in zip(df["key"].astype(str), df["数值"]):
            if pd.isna(v2) or v2 is None:
                continue
            try:
                m[str(k2)] = float(v2)
            except Exception:
                continue
        return m

    _ID_DATE_SUFFIX = re.compile(r"^(?P<id>.+?)\.(?P<y>\d{4})\.(?P<m>\d{2})\.(?P<d>\d{2})$")

    def _split_id_date(s: str) -> tuple[str, date | None]:
        m = _ID_DATE_SUFFIX.match(s)
        if not m:
            return s, None
        base = m.group("id")
        y, mm, dd = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return base, date(y, mm, dd)

    def _statement_from_key(key0: str, default_statement: str) -> str:
        k2 = (key0 or "").strip().lower()
        if k2.startswith("is."):
            return "利润表"
        if k2.startswith("bs."):
            return "资产负债表"
        if k2.startswith("cf."):
            return "现金流量表"
        return default_statement

    # cache: (xlsx_path, statement) -> {key: value}
    _map_cache: dict[tuple[Path, str], dict[str, float]] = {}

    def _xlsx_for_period(pe: date) -> Path:
        xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
        if xlsx.exists():
            return xlsx

        # on-demand fetch (允许缺失时自动补齐)
        ensure_finreports(
            code_or_name_args=["--code", c.rs.code6],
            code6=c.rs.code6,
            start=pe,
            end=pe,
            data_dir=c.data_dir,
            provider=c.provider,
            statement_type=c.statement_type,
            pdf=c.pdf,
            company_name=c.rs.name,
            tushare_token=c.tushare_token,
        )
        return xlsx

    def _values_map_for(pe: date, statement: str) -> dict[str, float]:
        xlsx = _xlsx_for_period(pe)
        key = (xlsx, statement)
        if key not in _map_cache:
            _map_cache[key] = _value_map_for_statement(xlsx, statement)
        return _map_cache[key]

    def _resolve_ident_value(ident: str, *, current_pe: date, default_statement: str) -> float | None:
        ident_s = (ident or "").strip()
        if not ident_s:
            return None

        base, pe2 = _split_id_date(ident_s)
        pe_use = pe2 or current_pe

        statement = _statement_from_key(base, default_statement)
        xlsx = _xlsx_for_period(pe_use)

        # key path
        if "." in base:
            vm = _values_map_for(pe_use, statement)
            if base in vm:
                return float(vm[base])
            # fallback: allow key-like string not in vm
            v = get_item_value(xlsx, statement, base)
            return float(v) if v is not None else None

        # CN subject fallback
        v = get_item_value(xlsx, statement, base)
        return float(v) if v is not None else None

    def _eval_expr_or_item(expr: str, *, current_pe: date, default_statement: str) -> float | None:
        expr_s = (expr or "").strip()
        if not expr_s:
            return None

        # expression: only ASCII identifiers are supported inside expr
        if re.search(r"[\+\-\*/\(\)]", expr_s):
            try:
                toks = tokenize(expr_s)
                ids = [t for t in toks if t not in {"+", "-", "*", "/", "(", ")"} and not re.fullmatch(r"\d+(?:\.\d+)?", t)]
                vals: dict[str, float] = {}
                for ident in ids:
                    v = _resolve_ident_value(ident, current_pe=current_pe, default_statement=default_statement)
                    if v is None:
                        raise ExprError(f"缺少变量: {ident}")
                    vals[ident] = float(v)
                return float(eval_expr(expr_s, vals))
            except ExprError as ex:
                console.print(f"[yellow]表达式计算失败: {expr_s} ({ex})[/yellow]")
                return None

        # single identifier / item
        if "." in expr_s:
            return _resolve_ident_value(expr_s, current_pe=current_pe, default_statement=default_statement)

        # CN subject
        xlsx = _xlsx_for_period(current_pe)
        v = get_item_value(xlsx, default_statement, expr_s)
        return float(v) if v is not None else None

    # 2) run templates
    for k, tpl in selected.items():
        fname_base = safe_slug(getattr(tpl, "alias", None) or getattr(tpl, "name", k))
        t_type = str(getattr(tpl, "type", "")).strip().lower()
        if not t_type:
            raise RuntimeError(f"模板缺少 type: {k}")

        title0 = getattr(tpl, "title", None)
        if not title0:
            raise RuntimeError(f"模板缺少 title: {k}")

        x_label = getattr(tpl, "x_label", None)
        y_label = getattr(tpl, "y_label", None)
        if not x_label or not y_label:
            raise RuntimeError(f"模板缺少 x_label/y_label: {k}")

        console.print(f"\n[bold]运行模板[/bold]: {k} → {fname_base}")

        # ---- bar ----
        if t_type == "bar":
            mode = (getattr(tpl, "mode", None) or "trend").strip().lower()
            bars = getattr(tpl, "bars", None)
            statement_default = getattr(tpl, "statement", None) or "利润表"

            if mode not in {"trend", "compare"}:
                raise RuntimeError(f"bar 模板 mode 仅支持 trend/compare: {k}")

            if not bars and mode == "trend":
                raise RuntimeError(f"趋势 bar 模板必须提供 [[bars]]: {k}")

            # ---- trend ----
            if mode == "trend":
                # requirement: must have start/end (already required by CLI)
                periods_out = _filter_periods(quarter_ends_between(c.start, c.end))

                # decide fetch_start based on transforms
                transforms = []
                for b in bars or []:
                    transforms.append(str(getattr(b, "transform", None) or "ttm").lower())
                if any(t == "ttm" for t in transforms):
                    fetch_start = date(c.start.year - 1, 1, 1)
                elif any(t == "q" for t in transforms):
                    fetch_start = date(c.start.year, 1, 1)
                else:
                    fetch_start = c.start

                _maybe_fetch_missing(c, fetch_start=fetch_start)

                periods_all = quarter_ends_between(fetch_start, c.end)

                # compute ytd/raw series for each bar
                series_ytd_by_name: dict[str, dict[date, float]] = {}

                for pe in periods_all:
                    for b in bars or []:
                        b_name = str(getattr(b, "name", None) or getattr(b, "expr", "")).strip() or "value"
                        b_expr = str(getattr(b, "expr", "")).strip()
                        b_stmt = str(getattr(b, "statement", None) or statement_default)

                        v_raw = _eval_expr_or_item(b_expr, current_pe=pe, default_statement=b_stmt)
                        if v_raw is None:
                            continue
                        series_ytd_by_name.setdefault(b_name, {})[pe] = float(v_raw)

                # build output df (one row per period)
                rows: list[dict[str, object]] = []
                for pe in periods_out:
                    row: dict[str, object] = {"period_end": pe.strftime("%Y-%m-%d")}
                    for b in bars or []:
                        b_name = str(getattr(b, "name", None) or getattr(b, "expr", "")).strip() or "value"
                        b_t = str(getattr(b, "transform", None) or "ttm").lower()
                        t2 = "ytd" if b_t == "raw" else b_t
                        ytd_map = series_ytd_by_name.get(b_name) or {}
                        y_raw = ytd_map.get(pe)
                        if y_raw is None:
                            row[b_name] = None
                            continue
                        if t2 == "ttm":
                            row[b_name] = ttm_from_ytd(pe, ytd_map)
                        elif t2 == "q":
                            row[b_name] = quarter_from_ytd(pe, ytd_map)
                        else:
                            row[b_name] = y_raw
                    rows.append(row)

                df_out = pd.DataFrame(rows)

                title = f"{c.rs.name or c.rs.code6} | {title0}"
                out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
                out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

                series_cols = [(str(getattr(b, 'name', None) or getattr(b, 'expr', '')).strip() or 'value', str(getattr(b, 'name', None) or getattr(b, 'expr', '')).strip() or 'value') for b in (bars or [])]
                # de-dup in case of duplicate names
                seen=set(); series_cols2=[]
                for col,label in series_cols:
                    if col in seen:
                        continue
                    seen.add(col)
                    series_cols2.append((col,label))

                render_bars_png(df_out, title=title, x_col="period_end", series=series_cols2, out_png=out_png, x_label=x_label, y_label=y_label)
                write_bars_excel(df_out, title=title, x_col="period_end", series=series_cols2, out_xlsx=out_xlsx, x_label=x_label, y_label=y_label)

                console.print(f"已生成: {out_png}")
                console.print(f"已生成: {out_xlsx}")
                continue

            # ---- compare ----
            # determine as_of
            if getattr(tpl, "period_end", None):
                pe0 = parse_date(str(getattr(tpl, "period_end")))
            elif as_of:
                pe0 = parse_date(as_of)
            else:
                pe0 = _latest_quarter_end_on_or_before(c.end)
            pe = _latest_quarter_end_on_or_before(pe0)

            # ensure the one period exists
            missing = ensure_finreports(
                code_or_name_args=["--code", c.rs.code6],
                code6=c.rs.code6,
                start=pe,
                end=pe,
                data_dir=c.data_dir,
                provider=c.provider,
                statement_type=c.statement_type,
                pdf=c.pdf,
                company_name=c.rs.name,
                tushare_token=c.tushare_token,
            )
            if missing:
                console.print(f"[yellow]警告：比较分析仍缺失报告期: {missing}[/yellow]")

            xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
            if not xlsx.exists():
                raise RuntimeError(f"未找到期末财报 xlsx: {xlsx}")

            statement = statement_default

            # 比较分析：完全由模板 bars 控制（不自动枚举“全部科目”）
            if not bars:
                raise RuntimeError(f"compare 模式必须在模板中显式配置 [[bars]]: {k}")

            rows = []
            for b in bars:
                b_name = str(getattr(b, "name", None) or getattr(b, "expr", "")).strip() or "value"
                b_expr = str(getattr(b, "expr", "")).strip()
                b_stmt = str(getattr(b, "statement", None) or statement)
                v = _eval_expr_or_item(b_expr, current_pe=pe, default_statement=b_stmt)
                rows.append({"name": b_name, "value": v})

            df_cmp = pd.DataFrame(rows)
            title = f"{c.rs.name or c.rs.code6} | {title0} | {pe.strftime('%Y-%m-%d')}"

            out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
            out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

            render_bars_png(df_cmp, title=title, x_col="name", series=[("value", y_label)], out_png=out_png, x_label=x_label, y_label=y_label)
            write_bars_excel(df_cmp, title=title, x_col="name", series=[("value", y_label)], out_xlsx=out_xlsx, x_label=x_label, y_label=y_label)

            console.print(f"已生成: {out_png}")
            console.print(f"已生成: {out_xlsx}")
            continue

        # ---- pie ----
        if t_type == "pie":
            statement = getattr(tpl, "statement", None) or "资产负债表"
            t_section = getattr(tpl, "section", None)
            t_items = getattr(tpl, "items", None)
            n = top_n if top_n is not None else (getattr(tpl, "top_n", None) or 10)

            if not t_section and not t_items:
                raise RuntimeError(f"pie 模板需要 section 或 items: {k}")

            _maybe_fetch_missing(c)
            periods = _filter_periods(quarter_ends_between(c.start, c.end))

            for pe in periods:
                xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
                if not xlsx.exists():
                    continue

                if t_section:
                    raw_items = get_section_items(xlsx, statement, t_section)
                else:
                    raw_items = []
                    for it in t_items or []:
                        v = get_item_value(xlsx, statement, it)
                        if v is None:
                            continue
                        raw_items.append((it, v))

                items_top = topn_with_other(raw_items, top_n=n)
                if not items_top:
                    continue

                title = f"{c.rs.name or c.rs.code6} | {title0} | {pe.strftime('%Y-%m-%d')}"
                out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
                out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

                render_pie_png(items_top, title=title, out_png=out_png)
                write_pie_excel(items_top, title=title, out_xlsx=out_xlsx)

            console.print(f"完成 pie 模板: {k}")
            continue

        # ---- combo ----
        if t_type == "combo":
            statement = getattr(tpl, "statement", None) or "利润表"
            bar_item = getattr(tpl, "bar_item", None) or "营业总收入"
            transform = getattr(tpl, "transform", None) or "ttm"

            t3 = "ytd" if transform == "raw" else str(transform).lower()
            if t3 == "ttm":
                fetch_start = date(c.start.year - 1, 1, 1)
            elif t3 == "q":
                fetch_start = date(c.start.year, 1, 1)
            else:
                fetch_start = c.start
            _maybe_fetch_missing(c, fetch_start=fetch_start)

            price_csv = c.data_dir / "price" / f"{c.rs.code6}.csv"
            if not price_csv.exists():
                raise RuntimeError(f"未找到股价 CSV: {price_csv}")

            df_price = load_price_csv(price_csv)
            periods = _filter_periods(quarter_ends_between(c.start, c.end))

            ytd_map: dict[date, float] = {}
            for pe in quarter_ends_between(fetch_start, c.end):
                xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
                if not xlsx.exists():
                    continue
                v = get_item_value(xlsx, statement, bar_item)
                if v is None:
                    continue
                ytd_map[pe] = float(v)

            rows = []
            for pe in periods:
                v_raw = ytd_map.get(pe)
                if v_raw is None:
                    continue
                if t3 == "ttm":
                    v = ttm_from_ytd(pe, ytd_map)
                elif t3 == "q":
                    v = quarter_from_ytd(pe, ytd_map)
                else:
                    v = v_raw
                px = price_on_or_before(df_price, pe)
                rows.append({"period_end": pe.strftime("%Y-%m-%d"), "amount": v, "close": px})

            df = pd.DataFrame(rows).dropna(subset=["amount", "close"])
            title = f"{c.rs.name or c.rs.code6} | {title0}"

            out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.png"
            out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{c.start.strftime('%Y%m%d')}_{c.end.strftime('%Y%m%d')}.xlsx"

            render_combo_png(df, title=title, x_col="period_end", bar_col="amount", line_col="close", out_png=out_png, bar_label=y_label, line_label="收盘价", x_label=x_label)
            write_combo_excel(df, title=title, x_col="period_end", bar_col="amount", line_col="close", out_xlsx=out_xlsx, bar_label=y_label, line_label="收盘价", x_label=x_label)

            console.print(f"已生成: {out_png}")
            console.print(f"已生成: {out_xlsx}")
            continue

        raise RuntimeError(f"暂不支持的模板 type: {t_type} ({k})")

    console.print(f"\n全部完成。输出目录: {c.out_dir}")



def main():
    app()


if __name__ == "__main__":
    main()
