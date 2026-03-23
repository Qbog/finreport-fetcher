from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from .utils.symbols import parse_code


@dataclass(frozen=True)
class DatasetPaths:
    root: Path
    raw_dir: Path
    csv_path: Path
    latest_meta_path: Path


GLOBAL_ROOT_NAME = "_global"
COMPANY_BASICS_DATASET = "company_basics"
FINANCIAL_METRICS_DATASET = "financial_metrics"


def dataset_paths(data_dir: Path, dataset_name: str, csv_name: str) -> DatasetPaths:
    root = data_dir.resolve() / GLOBAL_ROOT_NAME / dataset_name
    raw_dir = root / "raw"
    return DatasetPaths(
        root=root,
        raw_dir=raw_dir,
        csv_path=root / csv_name,
        latest_meta_path=root / "latest.json",
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_dataset(df: pd.DataFrame, *, paths: DatasetPaths, provider: str, raw_name: str) -> None:
    ensure_dir(paths.root)
    ensure_dir(paths.raw_dir)
    raw_path = paths.raw_dir / raw_name
    df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    df.to_csv(paths.csv_path, index=False, encoding="utf-8-sig")
    paths.latest_meta_path.write_text(
        json.dumps(
            {
                "provider": provider,
                "raw": raw_path.name,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "rows": int(len(df.index)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


BASIC_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ts_code": ("ts_code",),
    "code6": ("symbol", "code", "证券代码", "股票代码"),
    "name": ("name", "简称", "股票简称", "证券简称"),
    "area": ("area", "地域"),
    "industry": ("industry", "所属行业", "行业"),
    "market": ("market", "市场类型", "市场"),
    "exchange": ("exchange", "交易所"),
    "list_status": ("list_status", "上市状态"),
    "list_date": ("list_date", "上市日期"),
    "delist_date": ("delist_date", "退市日期"),
    "full_name": ("fullname", "full_name", "公司全称"),
    "enname": ("enname", "英文名称"),
}


METRIC_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ts_code": ("ts_code",),
    "code6": ("symbol", "code", "证券代码", "股票代码"),
    "name": ("name", "简称", "股票简称", "证券简称"),
    "end_date": ("end_date", "报告期", "report_date"),
    "ann_date": ("ann_date", "公告日期"),
    "roe": ("roe", "roe_dt", "净资产收益率", "净资产收益率(%)"),
    "roa": ("roa", "总资产净利率", "总资产报酬率"),
    "roic": ("roic",),
    "ev": ("ev", "enterprise_value"),
    "ebitda": ("ebitda",),
}


DEFAULT_METRIC_COLUMNS = ["ts_code", "code6", "name", "end_date", "ann_date", "roe", "roa", "roic", "ev", "ebitda"]


def _pick(row: dict[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def normalize_rows(rows: list[dict[str, Any]], aliases: dict[str, tuple[str, ...]], columns: list[str]) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {col: _pick(row, aliases.get(col, (col,))) for col in columns}
        code_like = item.get("code6") or item.get("ts_code")
        if code_like:
            rs = parse_code(str(code_like))
            if rs:
                item["code6"] = rs.code6
                item["ts_code"] = item.get("ts_code") or rs.ts_code
        normalized.append(item)
    df = pd.DataFrame(normalized, columns=columns)
    if "code6" in df.columns:
        df["code6"] = df["code6"].fillna("").astype(str).str.zfill(6)
        df = df[df["code6"].str.fullmatch(r"\d{6}", na=False)]
    return df.drop_duplicates().reset_index(drop=True)


class CompanyBasicsProvider:
    def fetch(self, tushare_token: str | None = None) -> tuple[str, pd.DataFrame]:
        errors: list[str] = []

        try:
            import tushare as ts

            token = tushare_token or os.getenv("TUSHARE_TOKEN")
            if token:
                ts.set_token(token)
                pro = ts.pro_api()
                df = pro.stock_basic(
                    exchange="",
                    list_status="L",
                    fields="ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date,fullname,enname",
                )
                if df is not None and not df.empty:
                    return "tushare", df
                errors.append("tushare 返回空数据")
            else:
                errors.append("缺少 TUSHARE_TOKEN")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tushare: {exc}")

        try:
            import akshare as ak

            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                return "akshare", df
            errors.append("akshare 返回空数据")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"akshare: {exc}")

        raise RuntimeError("无法获取公司基础信息：" + " | ".join(errors))


class FinancialMetricsProvider:
    def __init__(self, company_basics_provider: CompanyBasicsProvider | None = None) -> None:
        self.company_basics_provider = company_basics_provider or CompanyBasicsProvider()

    def fetch_company_list(self, tushare_token: str | None = None) -> pd.DataFrame:
        _provider, df = self.company_basics_provider.fetch(tushare_token=tushare_token)
        rows = df.to_dict(orient="records")
        return normalize_rows(rows, BASIC_FIELD_ALIASES, list(BASIC_FIELD_ALIASES.keys()))

    def fetch_company_metrics(self, ts_code: str, tushare_token: str | None = None) -> pd.DataFrame:
        import tushare as ts

        token = tushare_token or os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("抓取财报指标需要 TUSHARE_TOKEN")
        ts.set_token(token)
        pro = ts.pro_api()
        fields = "ts_code,ann_date,end_date,roe,roe_dt,roa,roic,ebitda,ev"
        try:
            df = pro.fina_indicator(ts_code=ts_code, fields=fields)
        except Exception:
            df = pro.fina_indicator_vip(ts_code=ts_code, fields=fields)
        if df is None:
            return pd.DataFrame(columns=DEFAULT_METRIC_COLUMNS)
        return df


def fetch_company_basics_dataset(*, data_dir: Path, tushare_token: str | None = None, provider: CompanyBasicsProvider | None = None) -> DatasetPaths:
    provider = provider or CompanyBasicsProvider()
    used_provider, raw_df = provider.fetch(tushare_token=tushare_token)
    rows = raw_df.to_dict(orient="records")
    df = normalize_rows(rows, BASIC_FIELD_ALIASES, list(BASIC_FIELD_ALIASES.keys()))
    df = df.sort_values(["code6", "name"], na_position="last").reset_index(drop=True)

    paths = dataset_paths(data_dir, COMPANY_BASICS_DATASET, "company_basics.csv")
    write_dataset(df, paths=paths, provider=used_provider, raw_name=f"{used_provider}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    return paths


def fetch_financial_metrics_dataset(
    *,
    data_dir: Path,
    tushare_token: str | None = None,
    provider: FinancialMetricsProvider | None = None,
    limit: int | None = None,
) -> DatasetPaths:
    provider = provider or FinancialMetricsProvider()
    company_df = provider.fetch_company_list(tushare_token=tushare_token)
    if limit is not None and limit > 0:
        company_df = company_df.head(limit)

    paths = dataset_paths(data_dir, FINANCIAL_METRICS_DATASET, "financial_metrics.csv")
    ensure_dir(paths.root)
    ensure_dir(paths.raw_dir)

    rows: list[dict[str, Any]] = []
    raw_index_path = paths.raw_dir / "index.csv"
    with raw_index_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code6", "ts_code", "raw_file"])
        for _, comp in company_df.iterrows():
            ts_code = str(comp.get("ts_code") or "").strip()
            code6 = str(comp.get("code6") or "").strip().zfill(6)
            name = str(comp.get("name") or "").strip() or None
            if not ts_code:
                continue
            raw_df = provider.fetch_company_metrics(ts_code=ts_code, tushare_token=tushare_token)
            raw_file = f"{code6}.csv"
            raw_df.to_csv(paths.raw_dir / raw_file, index=False, encoding="utf-8-sig")
            writer.writerow([code6, ts_code, raw_file])
            for row in raw_df.to_dict(orient="records"):
                item = {col: row.get(col) for col in raw_df.columns}
                item["code6"] = code6
                item["name"] = name
                rows.append(item)

    df = normalize_rows(rows, METRIC_FIELD_ALIASES, DEFAULT_METRIC_COLUMNS)
    if "end_date" in df.columns:
        df["end_date"] = df["end_date"].astype(str)
    if "ann_date" in df.columns:
        df["ann_date"] = df["ann_date"].astype(str)
    df = df.sort_values(["code6", "end_date"], na_position="last").reset_index(drop=True)
    df.to_csv(paths.csv_path, index=False, encoding="utf-8-sig")
    paths.latest_meta_path.write_text(
        json.dumps(
            {
                "provider": "tushare",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "rows": int(len(df.index)),
                "companies": int(company_df["code6"].nunique()) if "code6" in company_df.columns else 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return paths


def load_company_basics_csv(data_dir: Path) -> pd.DataFrame:
    paths = dataset_paths(data_dir, COMPANY_BASICS_DATASET, "company_basics.csv")
    if not paths.csv_path.exists():
        return pd.DataFrame(columns=list(BASIC_FIELD_ALIASES.keys()))
    return pd.read_csv(paths.csv_path)


def load_financial_metrics_csv(data_dir: Path) -> pd.DataFrame:
    paths = dataset_paths(data_dir, FINANCIAL_METRICS_DATASET, "financial_metrics.csv")
    if not paths.csv_path.exists():
        return pd.DataFrame(columns=DEFAULT_METRIC_COLUMNS)
    return pd.read_csv(paths.csv_path)
