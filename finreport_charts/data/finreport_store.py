from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from finreport_fetcher.utils.dates import parse_date, quarter_ends_between


@dataclass(frozen=True)
class FinreportPaths:
    xlsx: Path
    pdf: Path | None


def expected_xlsx_path(data_dir: Path, code6: str, statement_type: str, period_end: date) -> Path:
    fname = f"{code6}_{statement_type}_{period_end.strftime('%Y%m%d')}.xlsx"
    return data_dir / fname


def expected_pdf_path(data_dir: Path, code6: str, period_end: date) -> Path:
    return data_dir / "pdf" / f"{code6}_{period_end.strftime('%Y%m%d')}.pdf"


def ensure_finreports(
    *,
    code_or_name_args: list[str],
    code6: str,
    start: date,
    end: date,
    data_dir: Path,
    provider: str,
    statement_type: str,
    pdf: bool,
    tushare_token: str | None = None,
) -> list[date]:
    """确保 data_dir 里存在 start~end 的所有报告期末日财报 xlsx。

    返回：本次“仍然缺失”的报告期末日列表（如果补齐失败）。

    缺失时通过调用 finreport_fetcher 补齐（增量写入）。
    """

    periods = quarter_ends_between(start, end)
    missing = [pe for pe in periods if not expected_xlsx_path(data_dir, code6, statement_type, pe).exists()]

    if not missing:
        return []

    args = [
        sys.executable,
        "-m",
        "finreport_fetcher",
        "fetch",
        *code_or_name_args,
        "--start",
        start.strftime("%Y-%m-%d"),
        "--end",
        end.strftime("%Y-%m-%d"),
        "--provider",
        provider,
        "--statement-type",
        statement_type,
        "--out",
        str(data_dir),
        "--no-clean",
    ]
    if pdf:
        args.append("--pdf")
    if tushare_token:
        args += ["--tushare-token", tushare_token]

    subprocess.check_call(args)

    still_missing = [pe for pe in periods if not expected_xlsx_path(data_dir, code6, statement_type, pe).exists()]
    return still_missing


def read_statement_df(xlsx_path: Path, sheet_name: str) -> pd.DataFrame:
    """读取某一期财报的某张表，返回 DataFrame(科目,数值)。"""

    # 我们的 xlsx：第1行标题、第2行注释、第3行表头
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=2)
    # 标准列
    df = df[["科目", "数值"]].copy()
    return df


def get_item_value(xlsx_path: Path, sheet_name: str, item: str) -> float | None:
    df = read_statement_df(xlsx_path, sheet_name)
    m = df["科目"].astype(str) == item
    sub = df[m]
    if sub.empty:
        return None
    v = sub.iloc[0]["数值"]
    try:
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def get_section_items(
    xlsx_path: Path, sheet_name: str, section: str
) -> list[tuple[str, float]]:
    """按 section（标题科目）取其后连续的子项，直到下一个标题行。

    标题行的识别规则：数值为空且科目非空。
    """

    df = read_statement_df(xlsx_path, sheet_name)
    subj = df["科目"].astype(str)
    val = df["数值"]

    idxs = df.index[subj == section].tolist()
    if not idxs:
        return []

    start_i = idxs[0] + 1
    items: list[tuple[str, float]] = []

    for i in range(start_i, len(df)):
        name = str(subj.iloc[i])
        v = val.iloc[i]

        # 下一标题
        if name and (pd.isna(v) or v is None):
            break

        if not name:
            continue
        if pd.isna(v) or v is None:
            continue
        try:
            items.append((name, float(v)))
        except Exception:
            continue

    return items


def load_price_csv(price_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(price_csv)
    # 约定列名 date, close
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError("股价 CSV 需要包含列: date, close")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).sort_values("date")


def price_on_or_before(df_price: pd.DataFrame, dt: date) -> float | None:
    sub = df_price[df_price["date"] <= dt]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["close"])
