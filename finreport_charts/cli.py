from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from pathlib import Path
import math

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console
from rich.prompt import IntPrompt

from finreport_fetcher.utils.company_categories import resolve_company_category, default_company_categories_path
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
from .charts.line_trend import render_lines_png, write_lines_excel
from .charts.pie_share import render_pie_png, topn_with_other, write_pie_excel
from .data.finreport_store import (
    ensure_finreports,
    expected_pdf_path,
    expected_xlsx_path,
    get_item_value,
    get_section_items,
    load_price_csv,
    price_on_or_before,
    read_sheet_provider,
    read_statement_df,
)
from .templates.config import load_template_dir, load_template_file, load_templates
from .utils.expr import ExprError, eval_expr, tokenize
from .utils.files import safe_slug
from .utils.numfmt import UnitScale, choose_unit_scale, fmt_tick

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


@dataclass
class AxisPlan:
    y_range: tuple[float, float] | None
    unit_scale: UnitScale | None
    figsize: tuple[float, float]


class AxisStatsCollector:
    def __init__(self) -> None:
        self._min: float | None = None
        self._max: float | None = None
        self._max_points: int = 0

    def _update_value(self, value: float) -> None:
        if self._min is None or value < self._min:
            self._min = value
        if self._max is None or value > self._max:
            self._max = value

    def update(self, values: list[float], point_count: int) -> None:
        for v in values:
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                continue
            self._update_value(v)
        self._max_points = max(self._max_points, point_count)

    def build_plan(self) -> AxisPlan | None:
        if self._min is None or self._max is None:
            return None
        span = self._max - self._min
        pad = 0.1 * span if span > 0 else 1.0
        lower = self._min - pad
        upper = self._max + pad
        total = max(abs(self._min), abs(self._max))
        unit_scale = choose_unit_scale(total)
        fig_count = max(self._max_points or 1, 1)
        figsize = (max(7, min(22, 0.75 * fig_count + 4)), 5.5)
        return AxisPlan(y_range=(lower, upper), unit_scale=unit_scale, figsize=figsize)


def _collect_axis_stats(stats: AxisStatsCollector, df: pd.DataFrame, value_cols: list[str], point_col: str) -> None:
    if df.empty:
        return
    values: list[float] = []
    for col in value_cols:
        if col not in df.columns:
            continue
        try:
            vals = pd.to_numeric(df[col], errors="coerce").tolist()
        except Exception:
            vals = []
        for v in vals:
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                continue
            values.append(float(v))
    stats.update(values, point_count=len(df[point_col].tolist()))


_ID_DATE_SUFFIX = re.compile(r"^(?P<id>.+?)\.(?P<y>\d{4})\.(?P<m>\d{2})\.(?P<d>\d{2})$")


def _latest_quarter_end_on_or_before(d: date) -> date:
    start0 = date(d.year - 2, 1, 1)
    qs = quarter_ends_between(start0, d)
    if not qs:
        raise RuntimeError(f"无法从日期推断季末: {d}")
    return qs[-1]


def _prev_quarter_end(pe: date) -> date:
    pe0 = _latest_quarter_end_on_or_before(pe)
    mmdd = pe0.strftime('%m%d')
    if mmdd == '0331':
        return date(pe0.year - 1, 12, 31)
    if mmdd == '0630':
        return date(pe0.year, 3, 31)
    if mmdd == '0930':
        return date(pe0.year, 6, 30)
    if mmdd == '1231':
        return date(pe0.year, 9, 30)
    return date(pe0.year - 1, 12, 31)


def _prev_in_year_quarter_end(pe: date) -> date | None:
    pe0 = _latest_quarter_end_on_or_before(pe)
    mmdd = pe0.strftime('%m%d')
    if mmdd == '0331':
        return None
    if mmdd == '0630':
        return date(pe0.year, 3, 31)
    if mmdd == '0930':
        return date(pe0.year, 6, 30)
    if mmdd == '1231':
        return date(pe0.year, 9, 30)
    return None


def _split_id_date(s: str) -> tuple[str, date | None]:
    m = _ID_DATE_SUFFIX.match(s)
    if not m:
        return s, None
    base = m.group('id')
    y, mm, dd = int(m.group('y')), int(m.group('m')), int(m.group('d'))
    return base, date(y, mm, dd)


def _statement_from_key(key0: str, default_statement: str) -> str:
    k2 = (key0 or '').strip().lower()
    if k2.startswith('is.'):
        return '利润表'
    if k2.startswith('bs.'):
        return '资产负债表'
    if k2.startswith('cf.'):
        return '现金流量表'
    return default_statement


def _value_map_for_statement(xlsx: Path, statement: str) -> dict[str, float]:
    df = read_statement_df(xlsx, sheet_name=statement)
    m: dict[str, float] = {}
    if 'key' not in df.columns:
        return m
    for k2, v2 in zip(df['key'].astype(str), df['数值']):
        if pd.isna(v2) or v2 is None:
            continue
        try:
            m[str(k2)] = float(v2)
        except Exception:
            continue
    return m


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

    if s > e:
        raise typer.BadParameter(f"--start 不能晚于 --end：{start} > {end}")

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


def _default_price_csv_path(c: CommonOpts) -> Path:
    """Default price CSV path.

    优先读取公司归档目录：
    - {data_dir}/{公司名}_{code6}/price/{code6}.csv

    兼容旧路径：
    - {data_dir}/price/{code6}.csv
    """

    company_dir = safe_dir_component(f"{(c.rs.name or c.rs.code6)}_{c.rs.code6}")
    p1 = c.data_dir / company_dir / "price" / f"{c.rs.code6}.csv"
    p2 = c.data_dir / "price" / f"{c.rs.code6}.csv"
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    return p1


def _maybe_fetch_missing(c: CommonOpts, fetch_start: date | None = None) -> list[date]:
    """Ensure finreport xlsx exists for required periods.

    返回仍缺失的报告期列表（不会在此处抛异常）。

    说明：
    - 最新一期未披露/数据源缺失时，允许继续执行（上层可选择 strict）。
    - 避免重复下载：底层 ensure_finreports 会只补齐缺失期。
    """

    # 检测缺失的报告期文件（TTM 等场景可能需要 start 之前的历史期）
    check_start = fetch_start or c.start
    # end 超过今天时没有意义（未来报告期不可能有数据），避免误触导致大量无效下载尝试
    check_end = min(c.end, date.today())
    periods = quarter_ends_between(check_start, check_end)
    missing = [
        pe
        for pe in periods
        if not expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name).exists()
    ]

    if not missing:
        return []

    fs = fetch_start or c.start
    log_info(f"发现缺失财报 {len(missing)} 期，调用 finreport_fetcher 补齐到: {c.data_dir}")
    still = ensure_finreports(
        code_or_name_args=["--code", c.rs.code6],
        code6=c.rs.code6,
        start=fs,
        end=check_end,
        data_dir=c.data_dir,
        provider=c.provider,
        statement_type=c.statement_type,
        pdf=c.pdf,
        company_name=c.rs.name,
        tushare_token=c.tushare_token,
    )
    if still:
        log_warn(f"提示：补齐后仍缺失 {len(still)} 期财报，将跳过缺失期继续绘图：{still}")

    return still



def _resolve_chart_targets(
    code: str | None,
    name: str | None,
    category: str | None,
    category_config: Path | None,
) -> list[ResolvedSymbol]:
    if category and (code or name):
        raise typer.BadParameter("--category 与 --code/--name 互斥")
    if not category and not (code or name):
        raise typer.BadParameter("必须提供 --code/--name 或 --category")

    if category:
        cfg_path = category_config or default_company_categories_path()
        cat = resolve_company_category(category, cfg_path)

        try:
            df_map = load_a_share_name_map()
        except Exception:
            df_map = None

        targets: list[ResolvedSymbol] = []
        seen: set[str] = set()
        for item in cat.items:
            rs0 = parse_code(item.code6)
            if not rs0 or rs0.code6 in seen:
                continue
            seen.add(rs0.code6)
            name0 = None
            if df_map is not None:
                try:
                    m = df_map["code"].astype(str).str.zfill(6) == rs0.code6
                    if m.any():
                        name0 = str(df_map[m].iloc[0]["name"])
                except Exception:
                    pass
            targets.append(
                ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=name0 or item.name)
            )
        if not targets:
            raise typer.BadParameter(f"分类 {category} 未配置任何公司")
        if cat.alias:
            log_info(f"使用分类: {cat.name}（{cat.alias}）→ {len(targets)} 家公司")
        else:
            log_info(f"使用分类: {cat.name} → {len(targets)} 家公司")
        return targets

    return [_resolve_symbol(code=code, name=name)]


class ExpressionEvaluator:
    def __init__(self, opts: CommonOpts):
        self.opts = opts
        self._map_cache: dict[tuple[Path, str], dict[str, float]] = {}
        self._fetch_tried: set[date] = set()

    def _xlsx_for_period(self, pe: date) -> Path:
        xlsx = expected_xlsx_path(
            self.opts.data_dir,
            self.opts.rs.code6,
            self.opts.statement_type,
            pe,
            name=self.opts.rs.name,
        )
        if xlsx.exists():
            return xlsx
        if pe in self._fetch_tried:
            return xlsx
        self._fetch_tried.add(pe)
        ensure_finreports(
            code_or_name_args=["--code", self.opts.rs.code6],
            code6=self.opts.rs.code6,
            start=pe,
            end=pe,
            data_dir=self.opts.data_dir,
            provider=self.opts.provider,
            statement_type=self.opts.statement_type,
            pdf=self.opts.pdf,
            company_name=self.opts.rs.name,
            tushare_token=self.opts.tushare_token,
        )
        return xlsx

    def _values_map_for(self, pe: date, statement: str) -> dict[str, float]:
        xlsx = self._xlsx_for_period(pe)
        if not xlsx.exists():
            return {}
        key = (xlsx, statement)
        if key not in self._map_cache:
            self._map_cache[key] = _value_map_for_statement(xlsx, statement)
        return self._map_cache[key]

    def _resolve_ident_value(self, ident: str, *, current_pe: date, default_statement: str) -> float | None:
        ident_s = (ident or '').strip()
        if not ident_s:
            return None

        prev_in_year = False
        if ident_s.endswith('.prev_in_year'):
            prev_in_year = True
            ident_s = ident_s[: -len('.prev_in_year')]

        prev_n = 0
        while ident_s.endswith('.prev'):
            prev_n += 1
            ident_s = ident_s[: -len('.prev')]

        base, specified_date = _split_id_date(ident_s)
        statement = _statement_from_key(base, default_statement)

        target_pe = current_pe
        if specified_date:
            target_pe = _latest_quarter_end_on_or_before(specified_date)

        if prev_in_year:
            prev_pe = _prev_in_year_quarter_end(target_pe)
            if prev_pe is None:
                return 0.0
            target_pe = prev_pe

        for _ in range(prev_n):
            target_pe = _prev_quarter_end(target_pe)

        values_map = self._values_map_for(target_pe, statement)
        v0 = values_map.get(base)
        if v0 is not None:
            return float(v0)

        # fallback: allow key-like string not in vm, or CN subject
        xlsx = self._xlsx_for_period(target_pe)
        if not xlsx.exists():
            return None
        v1 = get_item_value(xlsx, statement, base)
        return float(v1) if v1 is not None else None

    def eval(self, expr: str, *, current_pe: date, default_statement: str) -> float | None:
        expr_s = (expr or '').strip()
        if not expr_s:
            return None

        if re.search(r"[\+\-\*/\(\)]", expr_s):
            try:
                toks = tokenize(expr_s)
                ids = [t for t in toks if t not in {"+", "-", "*", "/", "(", ")"} and not re.fullmatch(r"\d+(?:\.\d+)?", t)]
                vals: dict[str, float] = {}
                for ident in ids:
                    v = self._resolve_ident_value(
                        ident, current_pe=current_pe, default_statement=default_statement
                    )
                    if v is None:
                        raise ExprError(f"缺少变量: {ident}")
                    vals[ident] = float(v)
                return float(eval_expr(expr_s, vals))
            except ExprError as ex:
                log_warn(f"表达式计算失败: {expr_s} ({ex})")
                return None

        if '.' in expr_s:
            return self._resolve_ident_value(expr_s, current_pe=current_pe, default_statement=default_statement)

        xlsx = self._xlsx_for_period(current_pe)
        v = get_item_value(xlsx, default_statement, expr_s)
        return float(v) if v is not None else None


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
    """基于 finreport_fetcher 输出，生成漂亮的财务图表（PNG + Excel(含原始数据+Excel图表)）。"""

    global _LOG_LEVEL
    _LOG_LEVEL = _parse_log_level(log_level)


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
        price_csv = _default_price_csv_path(c)

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

        price_csv = _default_price_csv_path(c)
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
    category: str | None = typer.Option(None, "--category", help="公司分类名（见 config/company_categories.toml）"),
    category_config: Path | None = typer.Option(None, "--category-config", help="分类配置文件路径（默认：config/company_categories.toml）"),
    peer: list[str] = typer.Option(
        [],
        "--peer",
        help="同业分析：同业公司（可重复；支持 6 位代码或公司简称）。例如：--peer 深信服 --peer 奇安信",
        show_default=False,
    ),
    start: str = typer.Option(..., "--start", help="趋势分析必须提供时间范围；结构分析也可复用该范围"),
    end: str = typer.Option(..., "--end"),
    as_of: str | None = typer.Option(None, "--as-of", help="结构分析使用的报告期末日（YYYY-MM-DD）。不传则取 end 对应的最近一个季末"),
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
    strict: bool = typer.Option(False, "--strict", help="缺失财报时是否直接报错退出（默认：跳过缺失期继续）"),
):
    """模板驱动的图表生成（唯一推荐方式）。

    模板要求（你的约束）：
    - 必须有：type(类型)、title(标题)、x_label/y_label（坐标轴显示名，bar/combo 使用）
    - bar 需要 mode：trend（趋势分析）/ structure（结构分析，旧 compare）/ peer（同业分析）
    - bar 的每根柱都通过 [[bars]] 配置块描述，支持 expr 表达式（key + +-*/()）

    运行规则：
    - 不传 --template 或传入 '*'：运行 --templates 目录下全部模板
    - 传入 --template：仅运行指定模板（可重复）
    """

    targets = _resolve_chart_targets(code=code, name=name, category=category, category_config=category_config)
    s = parse_date(start)
    e = parse_date(end)

    if s > e:
        raise typer.BadParameter(f"--start 不能晚于 --end：{start} > {end}")

    if statement_type not in {"merged", "parent"}:
        raise typer.BadParameter("--statement-type 仅支持 merged 或 parent")

    if data_dir is None:
        data_dir = Path("output") if Path("output").exists() else Path(".")
    data_dir = data_dir.resolve()
    out_dir_base = out_dir.resolve() if out_dir is not None else None

    def _build_common(rs: ResolvedSymbol) -> CommonOpts:
        company_dir = data_dir / safe_dir_component(f"{(rs.name or rs.code6)}_{rs.code6}")
        out_dir0 = out_dir_base or (company_dir / "charts")
        out_dir0 = out_dir0.resolve()
        out_dir0.mkdir(parents=True, exist_ok=True)

        return CommonOpts(
            rs=rs,
            start=s,
            end=e,
            data_dir=data_dir,
            out_dir=out_dir0,
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
        log_info("将运行以下模板：")
        for k in selected.keys():
            log_info(f"  - {k}")
        return

    # helpers

    def _run_templates_for_company(
        c: CommonOpts,
        *,
        collect_only: bool,
        axis_plan_map: dict[str, AxisPlan] | None,
        stats_map: dict[str, AxisStatsCollector] | None,
    ) -> None:
        main_eval = ExpressionEvaluator(c)
        pad_x = len(targets) > 1

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

            axis_plan = axis_plan_map.get(k) if axis_plan_map else None
            axis_png_extra: dict[str, object] = {}
            axis_xlsx_extra: dict[str, object] = {}
            if axis_plan:
                axis_png_extra = {
                    "y_range": axis_plan.y_range,
                    "unit_scale": axis_plan.unit_scale,
                    "figsize": axis_plan.figsize,
                }
                axis_xlsx_extra = {"y_range": axis_plan.y_range}

            if not collect_only:
                log_info(f"\n[bold]运行模板[/bold]: {k} → {fname_base}")

            # ---- bar / line ----
            if t_type in {"bar", "line"}:
                mode = (getattr(tpl, "mode", None) or "trend").strip().lower().replace("compare", "structure")
                bars = getattr(tpl, "bars", None)
                statement_default = getattr(tpl, "statement", None) or "利润表"

                def _flatten_bar_blocks(
                    blocks,
                    *,
                    prefix: str | None = None,
                    parent_statement: str | None = None,
                    parent_color: str | None = None,
                ):
                    """Flatten nested bars into leaf blocks.

                    - group blocks (no expr, has children) act as containers
                    - statement/color inherit from parent when missing
                    - leaf display name includes group prefix: e.g. "资产/货币资金"
                    """

                    out = []
                    for b in blocks or []:
                        b_name = str(getattr(b, "name", None) or "").strip() or "value"
                        b_expr = getattr(b, "expr", None)
                        b_stmt = str(getattr(b, "statement", None) or parent_statement or statement_default)
                        b_color = getattr(b, "color", None) or parent_color

                        name_full = f"{prefix}/{b_name}" if prefix else b_name

                        # leaf
                        if b_expr:
                            out.append({"name": name_full, "expr": str(b_expr).strip(), "statement": b_stmt, "color": b_color})

                        # children
                        kids = getattr(b, "children", None)
                        if kids:
                            # group prefix uses current node name_full
                            out.extend(_flatten_bar_blocks(kids, prefix=name_full, parent_statement=b_stmt, parent_color=b_color))

                    return out

                chart_kind = "bar" if t_type == "bar" else "line"
                render_png = render_bars_png if t_type == "bar" else render_lines_png
                write_xlsx = write_bars_excel if t_type == "bar" else write_lines_excel

                if mode not in {"trend", "structure", "peer"}:
                    raise RuntimeError(f"{chart_kind} 模板 mode 仅支持 trend/structure/peer: {k}")

                if not bars and mode == "trend":
                    raise RuntimeError(f"趋势 {chart_kind} 模板必须提供 [[bars]]: {k}")

                # ---- trend ----
                if mode == "trend":
                    # requirement: must have start/end (already required by CLI)
                    periods_out = _filter_periods(quarter_ends_between(c.start, min(c.end, date.today())))
                    # transform 配置已弃用：现在按表达式直接取值（不做 ttm/ytd/q 口径转换）。
                    # 若模板里仍写了 transform，仅提示并忽略。
                    if getattr(tpl, 'transform', None):
                        log_debug("提示：模板字段 transform 已弃用，将被忽略（按 expr 原值取数）")
                    for b in bars or []:
                        if getattr(b, 'transform', None):
                            b_n = str(getattr(b, 'name', None) or getattr(b, 'expr', '')).strip() or 'value'
                            log_debug(f"提示：bars.transform 已弃用，将被忽略：{b_n}")

                    still = _maybe_fetch_missing(c)
                    if strict and still:
                        raise RuntimeError(f"缺失财报 {len(still)} 期（strict 模式退出）：{still}")

                    bars_flat = _flatten_bar_blocks(bars)
                    if not bars_flat:
                        raise RuntimeError(f"趋势 {chart_kind} 模板缺少可用 bars（叶子节点需提供 expr）: {k}")

                    # build output df (one row per period)
                    rows: list[dict[str, object]] = []
                    used_periods: list[date] = []
                    for pe in periods_out:
                        xlsx0 = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
                        if not xlsx0.exists():
                            if pad_x:
                                row0: dict[str, object] = {"period_end": pe.strftime("%Y-%m-%d")}
                                for b in bars_flat:
                                    row0[str(b["name"])] = float("nan")
                                rows.append(row0)
                                used_periods.append(pe)
                            continue

                        row: dict[str, object] = {"period_end": pe.strftime("%Y-%m-%d")}
                        any_val = False
                        for b in bars_flat:
                            b_name = str(b["name"])
                            b_expr = str(b["expr"])
                            b_stmt = str(b.get("statement") or statement_default)
                            v = main_eval.eval(b_expr, current_pe=pe, default_statement=b_stmt)
                            if v is None and pad_x:
                                row[b_name] = float("nan")
                            else:
                                row[b_name] = v
                            if v is not None:
                                any_val = True

                        if not any_val and not pad_x:
                            continue

                        rows.append(row)
                        used_periods.append(pe)

                    if not rows:
                        log_warn(f"提示：{k} 在该区间内没有可用数据（可能都缺失/未披露）。")
                        continue

                    df_out = pd.DataFrame(rows)
                    value_cols = [str(b["name"]) for b in bars_flat]
                    if (not df_out.empty) and (not pd.to_numeric(df_out[value_cols].stack(), errors="coerce").notna().any()):
                        if not collect_only:
                            log_warn(f"提示：{k} 在该区间内没有可用数据（可能都缺失/未披露）。")
                        continue

                    title = f"{c.rs.name or c.rs.code6} | {title0}"

                    actual_s = used_periods[0]
                    actual_e = used_periods[-1]
                    if (not pad_x) and actual_e < c.end:
                        log_warn(f"提示：end={c.end} 对应最新报告期数据不可用，实际截至 {actual_e}。")

                    out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{actual_s.strftime('%Y%m%d')}_{actual_e.strftime('%Y%m%d')}.png"
                    out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{actual_s.strftime('%Y%m%d')}_{actual_e.strftime('%Y%m%d')}.xlsx"

                    series_cols = [(b["name"], b["name"]) for b in bars_flat]
                    series_colors = [b.get("color") for b in bars_flat]

                    # de-dup in case of duplicate names
                    seen = set()
                    series_cols2 = []
                    series_colors2 = []
                    for (col, label), colr in zip(series_cols, series_colors):
                        if col in seen:
                            continue
                        seen.add(col)
                        series_cols2.append((col, label))
                        series_colors2.append(colr)

                    if collect_only and stats_map is not None:
                        stats = stats_map.setdefault(k, AxisStatsCollector())
                        _collect_axis_stats(stats, df_out, value_cols=[c0 for c0, _ in series_cols2], point_col="period_end")
                        continue

                    extra = {}
                    if t_type == "bar":
                        extra["series_colors"] = series_colors2

                    render_png(
                        df_out,
                        title=title,
                        x_col="period_end",
                        series=series_cols2,
                        out_png=out_png,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_png_extra,
                    )
                    write_xlsx(
                        df_out,
                        title=title,
                        x_col="period_end",
                        series=series_cols2,
                        out_xlsx=out_xlsx,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_xlsx_extra,
                    )

                    if not collect_only:
                        log_info(f"已生成: {out_png}")
                        log_info(f"已生成: {out_xlsx}")
                    continue

                if mode == "peer":
                    # Peer list: merge template peers + CLI peers
                    peer_defs: list[str] = []
                    peer_defs.extend([str(x) for x in (getattr(tpl, "peers", None) or [])])
                    peer_defs.extend([str(x) for x in (peer or [])])

                    if not peer_defs:
                        raise RuntimeError(f"peer 模式需要 peers：可在模板中配置 peers=[]，或命令行传入 --peer（可重复）: {k}")

                    if not bars:
                        raise RuntimeError(f"peer 模式必须在模板中显式配置 [[bars]]: {k}")

                    bars_flat = _flatten_bar_blocks(bars)
                    if not bars_flat:
                        raise RuntimeError(f"peer 模式缺少可用 bars（叶子节点需提供 expr）: {k}")

                    company_evals: list[tuple[str, str, ExpressionEvaluator]] = []
                    company_evals.append((c.rs.name or c.rs.code6, c.rs.code6, main_eval))
                    seen_codes = {c.rs.code6}

                    for peer_conf in peer_defs:
                        peer_val = str(peer_conf or "").strip()
                        if not peer_val:
                            continue
                        try:
                            if peer_val.isdigit() and len(peer_val) == 6:
                                peer_rs = _resolve_symbol(code=peer_val, name=None)
                            else:
                                peer_rs = _resolve_symbol(code=None, name=peer_val)
                        except Exception as exc:
                            raise RuntimeError(f"peer 模式解析公司 {peer_val} 失败: {exc}")
                        if peer_rs.code6 in seen_codes:
                            continue
                        seen_codes.add(peer_rs.code6)
                        opts_peer = CommonOpts(
                            rs=peer_rs,
                            start=c.start,
                            end=c.end,
                            data_dir=c.data_dir,
                            out_dir=c.out_dir,
                            provider=c.provider,
                            statement_type=c.statement_type,
                            pdf=c.pdf,
                            tushare_token=c.tushare_token,
                        )
                        company_evals.append((peer_rs.name or peer_rs.code6, peer_rs.code6, ExpressionEvaluator(opts_peer)))

                    if len(company_evals) < 2:
                        raise RuntimeError(f"peer 模式需要至少两个不同公司: {k}")

                    if getattr(tpl, "period_end", None):
                        target_date = parse_date(str(getattr(tpl, "period_end")))
                    elif as_of:
                        target_date = parse_date(as_of)
                    else:
                        target_date = c.end
                    pe_target = _latest_quarter_end_on_or_before(target_date)

                    rows = []
                    skipped = []
                    for label, _, eval_ctx in company_evals:
                        row = {"company": label}
                        any_val = False
                        for b in bars_flat:
                            b_name = b["name"]
                            b_expr = b["expr"]
                            b_stmt = b["statement"]
                            v = eval_ctx.eval(str(b_expr), current_pe=pe_target, default_statement=b_stmt)
                            row[b_name] = v
                            if v is not None:
                                any_val = True
                        if not any_val:
                            skipped.append(label)
                            continue
                        rows.append(row)

                    if not rows:
                        log_warn(f"提示：{k} peer 模式在 {pe_target.strftime('%Y-%m-%d')} 没有可用数据。")
                        continue

                    df_peer = pd.DataFrame(rows)
                    series_cols = []
                    series_colors = []
                    for b in bars_flat:
                        col = b["name"]
                        if col not in df_peer.columns:
                            continue
                        if df_peer[col].dropna().empty:
                            continue
                        series_cols.append((col, col))
                        series_colors.append(b.get("color"))

                    if not series_cols:
                        log_warn(f"提示：{k} peer 模式所有科目在 {pe_target.strftime('%Y-%m-%d')} 均为空。")
                        continue

                    if collect_only and stats_map is not None:
                        stats = stats_map.setdefault(k, AxisStatsCollector())
                        _collect_axis_stats(stats, df_peer, value_cols=[c0 for c0, _ in series_cols], point_col="company")
                        continue

                    extra = {}
                    if t_type == "bar":
                        extra["series_colors"] = series_colors

                    title = f"{c.rs.name or c.rs.code6} | {title0} | 同业对比 {pe_target.strftime('%Y-%m-%d')}"
                    out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_peer_{pe_target.strftime('%Y%m%d')}.png"
                    out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_peer_{pe_target.strftime('%Y%m%d')}.xlsx"

                    render_png(
                        df_peer,
                        title=title,
                        x_col="company",
                        series=series_cols,
                        out_png=out_png,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_png_extra,
                    )
                    write_xlsx(
                        df_peer,
                        title=title,
                        x_col="company",
                        series=series_cols,
                        out_xlsx=out_xlsx,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_xlsx_extra,
                    )

                    if not collect_only:
                        log_info(f"已生成: {out_png}")
                        log_info(f"已生成: {out_xlsx}")
                        if skipped:
                            log_warn(
                                f"提示：{k} peer 模式以下公司在 {pe_target.strftime('%Y-%m-%d')} 缺失数据，将跳过: {', '.join(skipped)}"
                            )
                    continue

                # ---- structure ----
                # 约定：当用户提供 --start/--end 时，结构分析会对时间范围内每个报告期各生成一张图。
                # 若显式指定了 --as-of 或模板 period_end，则按“单期末”输出。

                statement = statement_default

                # 结构分析：完全由模板 bars 控制（不自动枚举“全部科目”）
                if not bars:
                    raise RuntimeError(f"structure 模式必须在模板中显式配置 [[bars]]: {k}")

                bars_flat = _flatten_bar_blocks(bars)
                if not bars_flat:
                    raise RuntimeError(f"structure 模式缺少可用 bars（叶子节点需提供 expr）: {k}")

                # ---- single-period structure ----
                if getattr(tpl, "period_end", None) or as_of:
                    if getattr(tpl, "period_end", None):
                        pe0 = parse_date(str(getattr(tpl, "period_end")))
                    else:
                        pe0 = parse_date(as_of)

                    pe = _latest_quarter_end_on_or_before(pe0)

                    still = ensure_finreports(
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
                    if still:
                        log_warn(f"提示：结构分析期末财报不可用: {still}")
                        if strict:
                            raise RuntimeError(f"缺失财报 {len(still)} 期（strict 模式退出）：{still}")

                    xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)

                    # 若对应期末未披露：自动回退到最近一期可用财报（向前找最多 12 个季度）
                    if not xlsx.exists():
                        pe2 = pe
                        xlsx2 = xlsx
                        for _ in range(12):
                            pe2 = _prev_quarter_end(pe2)
                            xlsx2 = expected_xlsx_path(
                                c.data_dir, c.rs.code6, c.statement_type, pe2, name=c.rs.name
                            )
                            if xlsx2.exists():
                                log_warn(
                                    f"提示：{pe.strftime('%Y-%m-%d')} 财报不可用，回退到 {pe2.strftime('%Y-%m-%d')}。"
                                )
                                pe = pe2
                                xlsx = xlsx2
                                break

                    if not xlsx.exists():
                        log_warn(f"提示：结构分析缺少财报，跳过模板 {k}。")
                        continue

                    rows = []
                    x_colors = []
                    for b in bars_flat:
                        b_name = str(b["name"]).strip() or "value"
                        b_expr = str(b["expr"]).strip()
                        b_stmt = str(b.get("statement") or statement)
                        v = main_eval.eval(b_expr, current_pe=pe, default_statement=b_stmt)
                        if v is None:
                            if pad_x:
                                rows.append({"name": b_name, "value": float("nan")})
                                x_colors.append(b.get("color"))
                            continue
                        rows.append({"name": b_name, "value": v})
                        x_colors.append(b.get("color"))

                    df_cmp = pd.DataFrame(rows)
                    if df_cmp.empty:
                        log_warn(f"提示：{k} 在该期末没有可用数据（可能科目缺失/表达式失败）。")
                        continue

                    if collect_only and stats_map is not None:
                        stats = stats_map.setdefault(k, AxisStatsCollector())
                        _collect_axis_stats(stats, df_cmp, value_cols=["value"], point_col="name")
                        continue

                    title = f"{c.rs.name or c.rs.code6} | {title0} | {pe.strftime('%Y-%m-%d')}"
                    out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
                    out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

                    extra = {}
                    if t_type == "bar":
                        extra["x_colors"] = x_colors

                    render_png(
                        df_cmp,
                        title=title,
                        x_col="name",
                        series=[("value", y_label)],
                        out_png=out_png,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_png_extra,
                    )
                    write_xlsx(
                        df_cmp,
                        title=title,
                        x_col="name",
                        series=[("value", y_label)],
                        out_xlsx=out_xlsx,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_xlsx_extra,
                    )

                    if not collect_only:
                        log_info(f"已生成: {out_png}")
                        log_info(f"已生成: {out_xlsx}")
                    continue

                # ---- per-period structure (range) ----
                periods_cmp = _filter_periods(quarter_ends_between(c.start, min(c.end, date.today())))

                still = _maybe_fetch_missing(c)
                if strict and still:
                    raise RuntimeError(f"缺失财报 {len(still)} 期（strict 模式退出）：{still}")

                any_ok = False
                for pe in periods_cmp:
                    xlsx = expected_xlsx_path(c.data_dir, c.rs.code6, c.statement_type, pe, name=c.rs.name)
                    if not xlsx.exists():
                        continue

                    rows = []
                    x_colors = []
                    for b in bars_flat:
                        b_name = str(b["name"]).strip() or "value"
                        b_expr = str(b["expr"]).strip()
                        b_stmt = str(b.get("statement") or statement)
                        v = main_eval.eval(b_expr, current_pe=pe, default_statement=b_stmt)
                        if v is None:
                            if pad_x:
                                rows.append({"name": b_name, "value": float("nan")})
                                x_colors.append(b.get("color"))
                            continue
                        rows.append({"name": b_name, "value": v})
                        x_colors.append(b.get("color"))

                    df_cmp = pd.DataFrame(rows)
                    if df_cmp.empty:
                        continue

                    if collect_only and stats_map is not None:
                        stats = stats_map.setdefault(k, AxisStatsCollector())
                        _collect_axis_stats(stats, df_cmp, value_cols=["value"], point_col="name")
                        continue

                    any_ok = True
                    title = f"{c.rs.name or c.rs.code6} | {title0} | {pe.strftime('%Y-%m-%d')}"
                    out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.png"
                    out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{pe.strftime('%Y%m%d')}.xlsx"

                    extra = {}
                    if t_type == "bar":
                        extra["x_colors"] = x_colors

                    render_png(
                        df_cmp,
                        title=title,
                        x_col="name",
                        series=[("value", y_label)],
                        out_png=out_png,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_png_extra,
                    )
                    write_xlsx(
                        df_cmp,
                        title=title,
                        x_col="name",
                        series=[("value", y_label)],
                        out_xlsx=out_xlsx,
                        x_label=x_label,
                        y_label=y_label,
                        **extra,
                        **axis_xlsx_extra,
                    )

                    if not collect_only:
                        log_info(f"已生成: {out_png}")
                        log_info(f"已生成: {out_xlsx}")

                if not collect_only and not any_ok:
                    log_warn(f"提示：{k} 在该区间内没有可用数据（可能缺失/未披露）。")

                continue

            # ---- pie ----
            if t_type == "pie":
                if collect_only:
                    continue
                statement = getattr(tpl, "statement", None) or "资产负债表"
                t_section = getattr(tpl, "section", None)
                t_items = getattr(tpl, "items", None)
                n = top_n if top_n is not None else (getattr(tpl, "top_n", None) or 10)

                if not t_section and not t_items:
                    raise RuntimeError(f"pie 模板需要 section 或 items: {k}")

                still = _maybe_fetch_missing(c)
                if strict and still:
                    raise RuntimeError(f"缺失财报 {len(still)} 期（strict 模式退出）：{still}")

                periods = _filter_periods(quarter_ends_between(c.start, min(c.end, date.today())))

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

                log_info(f"完成 pie 模板: {k}")
                continue

            # ---- combo ----
            if t_type == "combo":
                statement = getattr(tpl, "statement", None) or "利润表"
                bar_item = getattr(tpl, "bar_item", None) or "营业总收入"

                if getattr(tpl, "transform", None):
                    log_debug("提示：combo.transform 已弃用，将被忽略（按 bar_item 表达式原值取数）")

                still = _maybe_fetch_missing(c)
                if strict and still:
                    raise RuntimeError(f"缺失财报 {len(still)} 期（strict 模式退出）：{still}")

                price_csv = _default_price_csv_path(c)
                if not price_csv.exists():
                    raise RuntimeError(f"未找到股价 CSV: {price_csv}")

                df_price = load_price_csv(price_csv)
                periods = _filter_periods(quarter_ends_between(c.start, min(c.end, date.today())))

                rows = []
                for pe in periods:
                    amount = main_eval.eval(str(bar_item), current_pe=pe, default_statement=statement)
                    px = price_on_or_before(df_price, pe)
                    rows.append({"period_end": pe.strftime("%Y-%m-%d"), "amount": amount, "close": px})

                df = pd.DataFrame(rows).sort_values("period_end")
                if pad_x:
                    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
                    df["close"] = pd.to_numeric(df["close"], errors="coerce")
                else:
                    df = df.dropna(subset=["amount", "close"])

                if df.empty or (not pd.to_numeric(df["amount"], errors="coerce").notna().any()):
                    if not collect_only:
                        log_warn(f"提示：{k} 在该区间内没有可用数据（可能缺少财报或股价数据）。")
                    continue

                # 以实际有数据的报告期作为输出文件名范围（避免 end 对应期末未披露导致误导）
                used_periods = [parse_date(str(x)) for x in df["period_end"].tolist()]
                actual_s = used_periods[0]
                actual_e = used_periods[-1]
                if (not pad_x) and actual_e < c.end:
                    log_warn(f"提示：end={c.end} 对应最新报告期数据不可用，实际截至 {actual_e}。")

                if collect_only and stats_map is not None:
                    stats = stats_map.setdefault(k, AxisStatsCollector())
                    _collect_axis_stats(stats, df, value_cols=["amount"], point_col="period_end")
                    continue

                title = f"{c.rs.name or c.rs.code6} | {title0}"

                out_png = c.out_dir / f"{fname_base}_{c.rs.code6}_{actual_s.strftime('%Y%m%d')}_{actual_e.strftime('%Y%m%d')}.png"
                out_xlsx = c.out_dir / f"{fname_base}_{c.rs.code6}_{actual_s.strftime('%Y%m%d')}_{actual_e.strftime('%Y%m%d')}.xlsx"

                render_combo_png(
                    df,
                    title=title,
                    x_col="period_end",
                    bar_col="amount",
                    line_col="close",
                    out_png=out_png,
                    bar_label=y_label,
                    line_label="收盘价",
                    x_label=x_label,
                    **axis_png_extra,
                )
                write_combo_excel(
                    df,
                    title=title,
                    x_col="period_end",
                    bar_col="amount",
                    line_col="close",
                    out_xlsx=out_xlsx,
                    bar_label=y_label,
                    line_label="收盘价",
                    x_label=x_label,
                    **axis_xlsx_extra,
                )

                if not collect_only:
                    log_info(f"已生成: {out_png}")
                    log_info(f"已生成: {out_xlsx}")
                continue

            raise RuntimeError(f"暂不支持的模板 type: {t_type} ({k})")

        if not collect_only:
            log_info(f"\n全部完成。输出目录: {c.out_dir}")

    axis_plan_map: dict[str, AxisPlan] | None = None
    if len(targets) > 1:
        stats_map: dict[str, AxisStatsCollector] = {}
        for rs in targets:
            c = _build_common(rs)
            _run_templates_for_company(c, collect_only=True, axis_plan_map=None, stats_map=stats_map)
        axis_plan_map = {k: v.build_plan() for k, v in stats_map.items() if v.build_plan() is not None}

    for rs in targets:
        c = _build_common(rs)
        _run_templates_for_company(c, collect_only=False, axis_plan_map=axis_plan_map, stats_map=None)



def main():
    app()


if __name__ == "__main__":
    main()
