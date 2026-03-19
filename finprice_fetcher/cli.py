from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from pathlib import Path

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console

from finreport_fetcher.utils.company_categories import resolve_company_category
from finreport_fetcher.utils.dates import parse_date
from finreport_fetcher.utils.paths import safe_dir_component
from finreport_fetcher.utils.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code


app = typer.Typer(add_completion=False)
console = Console()


class LogLevel(IntEnum):
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


def log_info(msg: str):
    log_print(LogLevel.INFO, msg)


def log_warn(msg: str):
    log_print(LogLevel.WARNING, f"[yellow]{msg}[/yellow]")


@dataclass(frozen=True)
class CommonOpts:
    rs: ResolvedSymbol
    start: date
    end: date
    out_dir: Path
    provider: str
    frequency: str
    tushare_token: str | None


def _resolve_symbol(code: str | None, name: str | None) -> ResolvedSymbol:
    if code and name:
        raise typer.BadParameter("--code 与 --name 只能二选一")

    df_map = None

    if code:
        rs0 = parse_code(code)
        if not rs0:
            raise typer.BadParameter(f"无法解析股票代码格式: {code}")

        # Fill official name if possible
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

        # 多候选：直接取最相似的第一个（价格抓取一般无需交互）
        c = cand.iloc[0]
        rs = parse_code(str(c["code"]))
        log_warn(f"名称 {name} 匹配到多个候选，默认取：{c['code']} {c['name']}")
        return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=str(c["name"]))

    raise typer.BadParameter("必须提供 --code 或 --name")


def _resolve_targets(
    *,
    code: str | None,
    name: str | None,
    category: str | None,
    category_config: Path | None,
) -> list[ResolvedSymbol]:
    if category:
        if code or name:
            raise typer.BadParameter("使用 --category 时不能同时传 --code/--name")
        cat = resolve_company_category(category, category_config)

        # 名称优先：配置文件里的 name；否则用 A 股映射表补齐
        df_map = None
        try:
            df_map = load_a_share_name_map()
        except Exception:
            df_map = None

        out: list[ResolvedSymbol] = []
        for it in cat.items:
            rs0 = parse_code(it.code6)
            nm = it.name
            if (not nm) and (df_map is not None):
                try:
                    m = df_map["code"].astype(str).str.zfill(6) == rs0.code6
                    if m.any():
                        nm = str(df_map[m].iloc[0]["name"])
                except Exception:
                    pass
            out.append(ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=nm))
        return out

    # single symbol
    return [_resolve_symbol(code=code, name=name)]


def _parse_common_args(
    *,
    start: str,
    end: str,
    out_dir: Path,
    provider: str,
    frequency: str,
    tushare_token: str | None,
) -> tuple[date, date, Path, str, str, str | None]:
    s = parse_date(start)
    e = parse_date(end)
    if s > e:
        raise typer.BadParameter(f"--start 不能晚于 --end：{start} > {end}")

    freq = (frequency or "daily").strip().lower()
    if freq in {"d", "day"}:
        freq = "daily"
    if freq in {"w", "week"}:
        freq = "weekly"
    if freq in {"m", "month"}:
        freq = "monthly"
    if freq not in {"daily", "weekly", "monthly"}:
        raise typer.BadParameter("--frequency 仅支持: daily/weekly/monthly")

    return (
        s,
        e,
        out_dir.resolve(),
        (provider or "auto").strip().lower(),
        freq,
        tushare_token,
    )


def _common(
    code: str | None,
    name: str | None,
    start: str,
    end: str,
    out_dir: Path,
    provider: str,
    frequency: str,
    tushare_token: str | None,
) -> CommonOpts:
    rs = _resolve_symbol(code=code, name=name)
    s, e, out_dir2, provider2, freq, token = _parse_common_args(
        start=start,
        end=end,
        out_dir=out_dir,
        provider=provider,
        frequency=frequency,
        tushare_token=tushare_token,
    )

    return CommonOpts(
        rs=rs,
        start=s,
        end=e,
        out_dir=out_dir2,
        provider=provider2,
        frequency=freq,
        tushare_token=token,
    )


def _fetch_price_tx(code6: str, start: date, end: date) -> pd.DataFrame:
    import akshare as ak

    symbol = "sh" + code6 if code6.startswith("6") else "sz" + code6
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start_s, end_date=end_s, adjust="", timeout=20)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    rename = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "前收盘": "pre_close",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
        "换手率": "turnover_rate",
    }
    out = df.rename(columns=rename).copy()
    if "date" not in out.columns:
        out.insert(0, "date", df.iloc[:, 0])
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

    for c in ["open", "high", "low", "close", "pre_close", "change", "pct_chg", "volume", "amount", "turnover_rate"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["date"]).sort_values("date")
    return out


def _fetch_price_akshare(code6: str, start: date, end: date, frequency: str) -> pd.DataFrame:
    """Fetch price data via akshare.

    目标：尽量保留 akshare 能提供的列（开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/换手率...）。
    """

    import akshare as ak

    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")
    period = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}[frequency]

    # akshare 底层是 requests，偶发网络抖动会 RemoteDisconnected；这里做轻量重试。
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code6,
                period=period,
                start_date=start_s,
                end_date=end_s,
                adjust="",
                timeout=20,
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
            # 1s/2s/4s backoff
            import time

            time.sleep(2 ** (attempt - 1))
            continue

    if last_err is not None:
        log_warn(f"akshare 价格接口失败，尝试腾讯：{last_err}")
        if frequency != "daily":
            raise last_err
        tx_df = _fetch_price_tx(code6, start, end)
        if not tx_df.empty:
            return tx_df
        raise last_err

    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    # akshare 常见列：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
    rename = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
        "换手率": "turnover_rate",
    }

    out = df.rename(columns=rename).copy()

    # date
    if "date" not in out.columns:
        out.insert(0, "date", df.iloc[:, 0])
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

    # numeric coercion for common fields
    for c in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "amplitude",
        "pct_chg",
        "change",
        "turnover_rate",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["date"]).sort_values("date")
    return out


def _fetch_price_tushare(ts_code: str, start: date, end: date, frequency: str, token: str) -> pd.DataFrame:
    """Fetch daily OHLCV via tushare pro.daily.

    tushare 这条接口只支持日频；周/月频走 akshare。
    """

    import tushare as ts

    pro = ts.pro_api(token)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    if frequency != "daily":
        raise RuntimeError("tushare provider 目前仅实现 daily；weekly/monthly 请用 akshare")

    df = pro.daily(ts_code=ts_code, start_date=start_s, end_date=end_s)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    # tushare: trade_date/open/high/low/close/pre_close/change/pct_chg/vol/amount
    out = df.rename(
        columns={
            "trade_date": "date",
            "vol": "volume",
        }
    ).copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")

    for c in ["open", "high", "low", "close", "pre_close", "change", "pct_chg", "volume", "amount"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["date"]).sort_values("date")
    return out


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
    global _LOG_LEVEL
    _LOG_LEVEL = _parse_log_level(log_level)


@app.command("fetch")
def fetch(
    code: str | None = typer.Option(None, "--code"),
    name: str | None = typer.Option(None, "--name"),
    category: str | None = typer.Option(None, "--category", help="公司分类名（见 config/company_categories.toml）"),
    category_config: Path | None = typer.Option(None, "--category-config", help="分类配置文件路径（默认：config/company_categories.toml）"),
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    out: Path = typer.Option(Path("output"), "--out", help="输出根目录（默认 output）"),
    provider: str = typer.Option(
        "auto",
        "--provider",
        help="数据源：auto|akshare|tushare（默认 auto）",
        show_default=True,
    ),
    frequency: str = typer.Option(
        "daily",
        "--frequency",
        "-f",
        help="频率：daily/weekly/monthly（默认 daily）",
        show_default=True,
    ),
    tushare_token: str | None = typer.Option(None, "--tushare-token", envvar="TUSHARE_TOKEN"),
):
    """抓取股价数据（CSV + Excel）。

    支持：
    - 单公司：--code 或 --name
    - 批量：--category（读取 config/company_categories.toml）

    输出：
    - {out}/{公司名}_{code6}/price/{code6}.csv
    - {out}/{公司名}_{code6}/price/{code6}.xlsx

    字段：尽量保留开盘/收盘/最高/最低/成交量/成交额/涨跌幅等，并额外计算：
    - avg_amount_over_volume = amount / volume
    - avg_ohlc4 = (open+high+low+close)/4
    """

    # 解析通用参数（不依赖单公司 code/name）
    s, e, out_dir0, provider0, freq0, token0 = _parse_common_args(
        start=start,
        end=end,
        out_dir=out,
        provider=provider,
        frequency=frequency,
        tushare_token=tushare_token,
    )

    targets = _resolve_targets(code=code, name=name, category=category, category_config=category_config)

    failed: list[tuple[str, str]] = []

    # 对 category：每家公司共用相同的时间范围/输出目录/数据源配置
    for i, rs in enumerate(targets):
        c = CommonOpts(
            rs=rs,
            start=s,
            end=e,
            out_dir=out_dir0,
            provider=provider0,
            frequency=freq0,
            tushare_token=token0,
        )

        if len(targets) > 1:
            log_info(f"\n公司: {c.rs.name or c.rs.code6} ({c.rs.code6}) [{i+1}/{len(targets)}]")

        # 输出到公司归档目录：{out}/{公司名}_{code6}/price/{code6}.csv
        company_dir = safe_dir_component(f"{(c.rs.name or c.rs.code6)}_{c.rs.code6}")
        out_dir2 = c.out_dir / company_dir / "price"
        out_dir2.mkdir(parents=True, exist_ok=True)
        out_path = out_dir2 / f"{c.rs.code6}.csv"

        try:
            # provider selection
            if c.provider == "auto":
                # 周/月频：优先 akshare；日频：token 有则优先 tushare，否则 akshare
                if c.frequency != "daily":
                    df = _fetch_price_akshare(c.rs.code6, c.start, c.end, c.frequency)
                    src = "akshare"
                elif c.tushare_token:
                    try:
                        df = _fetch_price_tushare(c.rs.ts_code, c.start, c.end, c.frequency, c.tushare_token)
                        src = "tushare"
                    except Exception as ex:
                        log_warn(f"tushare 获取失败，回退 akshare：{ex}")
                        df = _fetch_price_akshare(c.rs.code6, c.start, c.end, c.frequency)
                        src = "akshare"
                else:
                    df = _fetch_price_akshare(c.rs.code6, c.start, c.end, c.frequency)
                    src = "akshare"
            elif c.provider == "tushare":
                if not c.tushare_token:
                    raise typer.BadParameter("provider=tushare 需要 TUSHARE_TOKEN 或 --tushare-token")
                df = _fetch_price_tushare(c.rs.ts_code, c.start, c.end, c.frequency, c.tushare_token)
                src = "tushare"
            elif c.provider == "akshare":
                df = _fetch_price_akshare(c.rs.code6, c.start, c.end, c.frequency)
                src = "akshare"
            else:
                raise typer.BadParameter("--provider 仅支持 auto|akshare|tushare")
        except Exception as ex:
            # category 模式下尽量不中断：记录失败公司，继续下一家。
            log_warn(f"股价抓取失败：{c.rs.name or c.rs.code6}({c.rs.code6}) => {type(ex).__name__}: {ex}")
            failed.append((c.rs.code6, str(ex)))
            continue

        # computed averages (two kinds)
        try:
            if "amount" in df.columns and "volume" in df.columns:
                vol = pd.to_numeric(df["volume"], errors="coerce")
                amt = pd.to_numeric(df["amount"], errors="coerce")
                df["avg_amount_over_volume"] = (amt / vol).where(vol != 0)
            else:
                df["avg_amount_over_volume"] = pd.NA
        except Exception:
            df["avg_amount_over_volume"] = pd.NA

        try:
            cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
            if len(cols) == 4:
                df["avg_ohlc4"] = (
                    pd.to_numeric(df["open"], errors="coerce")
                    + pd.to_numeric(df["high"], errors="coerce")
                    + pd.to_numeric(df["low"], errors="coerce")
                    + pd.to_numeric(df["close"], errors="coerce")
                ) / 4.0
            else:
                df["avg_ohlc4"] = pd.NA
        except Exception:
            df["avg_ohlc4"] = pd.NA

        df.to_csv(out_path, index=False)

        out_xlsx = out_dir2 / f"{c.rs.code6}.xlsx"
        # 价格表 Excel：方便人工查看/二次处理
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="price", index=False)

        log_info(f"已输出: {out_path} / {out_xlsx} (provider={src}, frequency={c.frequency}, rows={len(df)})")

    if failed:
        # 提示：即使有失败公司，成功的公司文件仍然已经写入。
        ex = "; ".join([f"{code6}=>{msg}" for code6, msg in failed[:3]])
        more = "（更多失败请用 -l debug）" if len(failed) > 3 else ""
        raise RuntimeError(f"股价抓取失败 {len(failed)}/{len(targets)}。示例：{ex}{more}")


def main():
    app()


if __name__ == "__main__":
    main()
