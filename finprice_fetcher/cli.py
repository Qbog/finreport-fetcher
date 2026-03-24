from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from pathlib import Path
import re

# 避免 pandas 在某些环境下对 numexpr/bottleneck 版本给出噪声警告
warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console

from finreport_fetcher.utils.company_categories import resolve_company_category
from finreport_fetcher.utils.dates import parse_date
from finreport_fetcher.utils.paths import safe_dir_component
from finshared.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code

from .raw_store import RawPriceStore


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


def _normalize_frequency(frequency: str) -> str:
    freq = (frequency or "daily").strip().lower()
    if freq in {"d", "day", "1d"}:
        return "daily"
    if freq in {"w", "week"}:
        return "weekly"
    if freq in {"m", "month"}:
        return "monthly"

    # custom N-day bars (e.g. 5d/7d/10d)
    m = re.fullmatch(r"(\d+)d", freq)
    if m:
        n = int(m.group(1))
        if n <= 0:
            raise typer.BadParameter("--frequency 的 Nd 必须为正整数，例如 5d")
        if n == 1:
            return "daily"
        if n > 60:
            raise typer.BadParameter("--frequency 的 Nd 过大（>60d），请确认是否输入错误")
        return f"{n}d"

    if freq not in {"daily", "weekly", "monthly"}:
        raise typer.BadParameter("--frequency 仅支持: daily/weekly/monthly/\"Nd\"(例如 5d/7d/10d)")
    return freq


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

    freq = _normalize_frequency(frequency)

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


def _aggregate_n_days(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date")
    if out.empty:
        return pd.DataFrame(columns=["date", "close"])

    out = out.reset_index(drop=True)
    out["__grp"] = (out.index // max(int(n), 1)).astype(int)

    def _first(s):
        return s.iloc[0] if len(s) else pd.NA

    def _last(s):
        return s.iloc[-1] if len(s) else pd.NA

    agg: dict[str, object] = {
        "date": ("date", _last),
    }

    # OHLC
    if "open" in out.columns:
        agg["open"] = ("open", _first)
    if "high" in out.columns:
        agg["high"] = ("high", "max")
    if "low" in out.columns:
        agg["low"] = ("low", "min")
    if "close" in out.columns:
        agg["close"] = ("close", _last)

    # sums
    for c in ["volume", "amount"]:
        if c in out.columns:
            agg[c] = (c, "sum")

    g = out.groupby("__grp", as_index=False).agg(**agg)

    # compute change/pct_chg from close series if possible
    if "close" in g.columns:
        g["pre_close"] = pd.to_numeric(g["close"], errors="coerce").shift(1)
        g["change"] = pd.to_numeric(g["close"], errors="coerce") - pd.to_numeric(g["pre_close"], errors="coerce")
        g["pct_chg"] = (pd.to_numeric(g["change"], errors="coerce") / pd.to_numeric(g["pre_close"], errors="coerce") * 100.0)

    g["date"] = pd.to_datetime(g["date"]).dt.strftime("%Y-%m-%d")
    g = g.drop(columns=[c for c in g.columns if c == "__grp"], errors="ignore")
    return g


def _coerce_price_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])

    out = df.copy()
    if "date" not in out.columns:
        return pd.DataFrame(columns=["date", "close"])

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    for c in [
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "volume",
        "amount",
        "amplitude",
        "turnover_rate",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out.reset_index(drop=True)


# canonical raw cache uses full-history daily bars, then derive weekly/monthly/Nd outputs locally.
def _filter_price_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    out = _coerce_price_df(df)
    if out.empty:
        return out
    mask = (pd.to_datetime(out["date"]) >= pd.Timestamp(start)) & (pd.to_datetime(out["date"]) <= pd.Timestamp(end))
    return out.loc[mask].reset_index(drop=True)


def _aggregate_calendar_period(df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    out = _coerce_price_df(df)
    if out.empty:
        return out
    if frequency == "daily":
        return out

    rule = {"weekly": "W-FRI", "monthly": "ME"}.get(frequency)
    if not rule:
        raise ValueError(f"不支持的日历频率聚合: {frequency}")

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if out.empty:
        return pd.DataFrame(columns=["date", "close"])

    agg: dict[str, tuple[str, object]] = {
        "date": ("date", lambda s: s.iloc[-1] if len(s) else pd.NaT),
    }
    if "open" in out.columns:
        agg["open"] = ("open", lambda s: s.iloc[0] if len(s) else pd.NA)
    if "high" in out.columns:
        agg["high"] = ("high", "max")
    if "low" in out.columns:
        agg["low"] = ("low", "min")
    if "close" in out.columns:
        agg["close"] = ("close", lambda s: s.iloc[-1] if len(s) else pd.NA)
    for c in ["volume", "amount"]:
        if c in out.columns:
            agg[c] = (c, "sum")
    for c in ["turnover_rate"]:
        if c in out.columns:
            agg[c] = (c, "mean")

    g = out.groupby(pd.Grouper(key="date", freq=rule), as_index=False).agg(**agg)
    g = g.dropna(subset=["date"]).reset_index(drop=True)
    if g.empty:
        return pd.DataFrame(columns=["date", "close"])

    if "close" in g.columns:
        g["pre_close"] = pd.to_numeric(g["close"], errors="coerce").shift(1)
        g["change"] = pd.to_numeric(g["close"], errors="coerce") - pd.to_numeric(g["pre_close"], errors="coerce")
        g["pct_chg"] = pd.to_numeric(g["change"], errors="coerce") / pd.to_numeric(g["pre_close"], errors="coerce") * 100.0
    if {"high", "low", "pre_close"}.issubset(g.columns):
        g["amplitude"] = (
            (pd.to_numeric(g["high"], errors="coerce") - pd.to_numeric(g["low"], errors="coerce"))
            / pd.to_numeric(g["pre_close"], errors="coerce")
            * 100.0
        )

    g["date"] = pd.to_datetime(g["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return _coerce_price_df(g)


def _finalize_price_df(df: pd.DataFrame) -> pd.DataFrame:
    out = _coerce_price_df(df)

    try:
        if "amount" in out.columns and "volume" in out.columns:
            vol = pd.to_numeric(out["volume"], errors="coerce")
            amt = pd.to_numeric(out["amount"], errors="coerce")
            out["avg_amount_over_volume"] = (amt / vol).where(vol != 0)
        else:
            out["avg_amount_over_volume"] = pd.NA
    except Exception:
        out["avg_amount_over_volume"] = pd.NA

    try:
        cols = [c for c in ["open", "high", "low", "close"] if c in out.columns]
        if len(cols) == 4:
            out["avg_ohlc4"] = (
                pd.to_numeric(out["open"], errors="coerce")
                + pd.to_numeric(out["high"], errors="coerce")
                + pd.to_numeric(out["low"], errors="coerce")
                + pd.to_numeric(out["close"], errors="coerce")
            ) / 4.0
        else:
            out["avg_ohlc4"] = pd.NA
    except Exception:
        out["avg_ohlc4"] = pd.NA

    return out


def _fetch_full_history_akshare(code6: str) -> pd.DataFrame:
    return _fetch_price_akshare(code6, date(1990, 1, 1), date.today(), "daily")


def _fetch_full_history_tushare(ts_code: str, token: str) -> pd.DataFrame:
    return _fetch_price_tushare(ts_code, date(1990, 1, 1), date.today(), "daily", token)


def _load_cached_raw_daily(store: RawPriceStore, provider_name: str) -> pd.DataFrame | None:
    df = store.load_daily_prices(provider_name)
    if df is None:
        return None
    df2 = _coerce_price_df(df)
    return df2 if not df2.empty else None


def _save_raw_daily(store: RawPriceStore, provider_name: str, df: pd.DataFrame) -> pd.DataFrame:
    out = _coerce_price_df(df)
    store.save_daily_prices(
        provider_name,
        out,
        metadata={
            "scope": "full_history_daily",
            "note": "首次无缓存时抓取整家公司全历史日线原始数据，后续频率/区间输出均从 raw 提取。",
        },
    )
    return out


def _ensure_raw_daily_price(c: CommonOpts, company_root: Path) -> tuple[pd.DataFrame, str]:
    store = RawPriceStore(company_root)

    def _load(provider_name: str) -> pd.DataFrame | None:
        return _load_cached_raw_daily(store, provider_name)

    def _fetch_and_save(provider_name: str) -> pd.DataFrame:
        if provider_name == "tushare":
            if not c.tushare_token:
                raise RuntimeError("未提供 TUSHARE_TOKEN，无法抓取 tushare 全历史股价 raw")
            raw_df = _fetch_full_history_tushare(c.rs.ts_code, c.tushare_token)
        elif provider_name == "akshare":
            raw_df = _fetch_full_history_akshare(c.rs.code6)
        else:
            raise RuntimeError(f"不支持的 raw 价格 provider: {provider_name}")
        return _save_raw_daily(store, provider_name, raw_df)

    if c.provider in {"akshare", "tushare"}:
        cached = _load(c.provider)
        if cached is not None:
            return cached, c.provider
        return _fetch_and_save(c.provider), c.provider

    # auto: 优先使用已存在缓存；无缓存时再按优先级抓取全历史。
    preferred = ["tushare", "akshare"] if c.tushare_token else ["akshare"]
    cached_candidates = preferred + [p for p in store.available_providers() if p not in preferred]
    for provider_name in cached_candidates:
        cached = _load(provider_name)
        if cached is not None:
            return cached, provider_name

    last_err: Exception | None = None
    fetch_candidates = preferred + ["akshare"]
    seen: set[str] = set()
    for provider_name in fetch_candidates:
        if provider_name in seen:
            continue
        seen.add(provider_name)
        try:
            return _fetch_and_save(provider_name), provider_name
        except Exception as ex:
            last_err = ex
            if provider_name == "tushare":
                log_warn(f"tushare 全历史股价 raw 获取失败，回退 akshare：{ex}")
            continue

    raise RuntimeError(f"无法获取全历史股价 raw：{last_err}")


def _fetch_price_akshare(code6: str, start: date, end: date, frequency: str) -> pd.DataFrame:
    """Fetch price data via akshare.

    目标：尽量保留 akshare 能提供的列（开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/换手率...）。

    说明：akshare 原生只支持 daily/weekly/monthly；自定义 Nd(例如 5d/7d/10d) 会先取 daily 再在 fetcher 内聚合。
    """

    import akshare as ak

    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    # custom Nd => fetch daily then aggregate
    m = re.fullmatch(r"(\d+)d", frequency or "")
    if m and frequency not in {"daily", "weekly", "monthly"}:
        n = int(m.group(1))
        df_daily = _fetch_price_akshare(code6, start, end, "daily")
        return _aggregate_n_days(df_daily, n)

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
    """Fetch OHLCV via tushare pro.daily.

    tushare 只提供日频；weekly/monthly 仍建议走 akshare。
    对自定义 Nd(例如 5d/7d/10d)：先取日频，再在 fetcher 内聚合。
    """

    import tushare as ts

    pro = ts.pro_api(token)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    m = re.fullmatch(r"(\d+)d", frequency or "")
    if frequency in {"weekly", "monthly"}:
        raise RuntimeError("tushare provider 不支持 weekly/monthly；请用 akshare")

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

    # custom Nd => aggregate
    if m and frequency not in {"daily", "weekly", "monthly"}:
        n = int(m.group(1))
        return _aggregate_n_days(out, n)

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
        help="频率：daily/weekly/monthly 或 Nd（例如 5d/7d/10d；Nd 会在 fetcher 内由日频聚合得到）（默认 daily）",
        show_default=True,
    ),
    tushare_token: str | None = typer.Option(None, "--tushare-token", envvar="TUSHARE_TOKEN"),
):
    """抓取股价数据（CSV + Excel）。

    支持：
    - 单公司：--code 或 --name
    - 批量：--category（读取 config/company_categories.toml）

    输出：
    - 原始全历史日线 raw：{out}/{公司名}_{code6}/raw/price/{provider}/daily.pkl
    - 使用输出：{out}/{公司名}_{code6}/price/{code6}.csv
    - 使用输出：{out}/{公司名}_{code6}/price/{code6}.xlsx

    行为：
    - 第一次无缓存时，会先抓整家公司“全历史日线原始数据”保存到 raw 目录。
    - 之后再取 daily/weekly/monthly/Nd 时，都从 raw 中裁切/聚合，不再重复访问远端。

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

        # 输出到公司归档目录：{out}/{公司名}_{code6}/price/{code6}[_{frequency}].csv
        company_dir = safe_dir_component(f"{(c.rs.name or c.rs.code6)}_{c.rs.code6}")
        company_root = c.out_dir / company_dir
        out_dir2 = company_root / "price"
        out_dir2.mkdir(parents=True, exist_ok=True)

        suffix = "" if c.frequency == "daily" else f"_{c.frequency}"
        out_path = out_dir2 / f"{c.rs.code6}{suffix}.csv"

        try:
            raw_daily, src = _ensure_raw_daily_price(c, company_root)

            df_range = _filter_price_range(raw_daily, c.start, c.end)
            if c.frequency == "daily":
                df = df_range
            elif c.frequency in {"weekly", "monthly"}:
                df = _aggregate_calendar_period(df_range, c.frequency)
            else:
                m = re.fullmatch(r"(\d+)d", c.frequency or "")
                if not m:
                    raise typer.BadParameter("--frequency 仅支持 daily/weekly/monthly/\"Nd\"(例如 5d/7d/10d)")
                df = _aggregate_n_days(df_range, int(m.group(1)))

            df = _finalize_price_df(df)
        except Exception as ex:
            # category 模式下尽量不中断：记录失败公司，继续下一家。
            log_warn(f"股价抓取失败：{c.rs.name or c.rs.code6}({c.rs.code6}) => {type(ex).__name__}: {ex}")
            failed.append((c.rs.code6, str(ex)))
            continue

        df.to_csv(out_path, index=False)

        out_xlsx = out_dir2 / f"{c.rs.code6}{suffix}.xlsx"
        # 价格表 Excel：方便人工查看/二次处理
        try:
            with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
                df.to_excel(w, sheet_name="price", index=False)
            log_info(f"已输出: {out_path} / {out_xlsx} (provider={src}, frequency={c.frequency}, rows={len(df)}, raw=full_history_daily)")
        except PermissionError as e:
            # HGFS/共享盘上，xlsx 可能被宿主机 Excel 打开而无法覆盖；此时保留 CSV 产物即可（charts 补数只依赖 CSV）。
            if out_xlsx.exists():
                log_warn(f"提示：无法写入 Excel（可能文件被占用），将保留现有文件：{out_xlsx} ({e})")
                log_info(f"已输出: {out_path} (xlsx 保留现有) (provider={src}, frequency={c.frequency}, rows={len(df)})")
            else:
                alt = out_xlsx.with_name(out_xlsx.stem + "_new.xlsx")
                try:
                    with pd.ExcelWriter(alt, engine="openpyxl") as w:
                        df.to_excel(w, sheet_name="price", index=False)
                    log_warn(f"提示：无法写入 Excel（可能文件被占用）：{out_xlsx}；已改写到：{alt}")
                    log_info(f"已输出: {out_path} / {alt} (provider={src}, frequency={c.frequency}, rows={len(df)})")
                except Exception:
                    raise

    if failed:
        # 提示：即使有失败公司，成功的公司文件仍然已经写入。
        ex = "; ".join([f"{code6}=>{msg}" for code6, msg in failed[:3]])
        more = "（更多失败请用 -l debug）" if len(failed) > 3 else ""
        raise RuntimeError(f"股价抓取失败 {len(failed)}/{len(targets)}。示例：{ex}{more}")


def main():
    app()


if __name__ == "__main__":
    main()
