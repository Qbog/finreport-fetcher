#!/usr/bin/env python3
"""Scan A-share statements to discover uncommon / unmapped subjects.

Purpose
- Sample dozens of typical A-share companies by category (non-financial / bank / securities / insurance)
- Fetch statements from each provider
- Report:
  1) unmapped CN subjects (need to be added into subject_glossary.py)
  2) candidate uncommon subjects (appear rarely in the sample)

NOTE
- This script does NOT modify code; it only outputs a report.
- Tushare requires token via env `TUSHARE_TOKEN`.

Example
  # 非金融（排除银行/券商/保险）
  python3 scripts/scan_uncommon_subjects.py --category non_financial --n 50 --use-csi300 \
    --periods 2020-12-31,2024-12-31 --providers tushare,akshare_ths,akshare --out output/subject_scan/non_financial.json

  # 银行
  python3 scripts/scan_uncommon_subjects.py --category bank --n 20 --use-csi300 \
    --periods 2024-12-31 --providers tushare,akshare_ths,akshare --out output/subject_scan/bank.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from finreport_fetcher.providers.akshare_sina import AkshareSinaProvider
from finreport_fetcher.providers.akshare_ths import AkshareThsProvider
from finreport_fetcher.providers.tushare_provider import TushareProvider
from finreport_fetcher.utils.dates import parse_date
from finreport_fetcher.utils.symbols import parse_code
from finreport_fetcher.mappings.enrich import _normalize_subject  # type: ignore
from finreport_fetcher.mappings.subject_glossary import lookup_subject


@dataclass
class OccurExample:
    code6: str
    name: str | None
    period_end: str
    statement: str


def _try_load_csi300_samples(
    token: str,
    n: int,
    *,
    category: str,
) -> list[dict[str, str]]:
    """Return [{code6,name}] by CSI300 weights (top n) filtered by category."""

    import tushare as ts

    pro = ts.pro_api(token)

    # Get latest trade date (open day)
    cal = pro.trade_cal(exchange="SSE", is_open="1", fields="cal_date")
    cal_date = str(cal.iloc[-1]["cal_date"])  # YYYYMMDD

    w = pro.index_weight(index_code="399300.SZ", trade_date=cal_date, fields="con_code,weight")
    w = w.sort_values("weight", ascending=False)

    basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
    basic = basic.rename(columns={"ts_code": "con_code"})
    m = w.merge(basic, on="con_code", how="left")

    ind = m["industry"].fillna("").astype(str)

    if category == "bank":
        m = m[ind.str.contains("银行", regex=False)]
    elif category == "securities":
        m = m[ind.str.contains("证券|资本市场|多元金融|金融服务", regex=True)]
        m = m[~ind.str.contains("银行", regex=False)]
    elif category == "insurance":
        m = m[ind.str.contains("保险", regex=False)]
    elif category == "non_financial":
        m = m[~ind.str.contains("银行|证券|保险|资本市场|多元金融|金融服务", regex=True)]
    else:
        raise ValueError(f"unknown category: {category}")

    out: list[dict[str, str]] = []
    for _, r in m.head(n).iterrows():
        ts_code = str(r["con_code"])  # 000001.SZ
        pc = parse_code(ts_code)
        out.append({"code6": pc.code6, "name": str(r.get("name") or "")})
    return out


def _fallback_samples() -> list[dict[str, str]]:
    # A pragmatic, non-bank set of large/typical A-share companies across sectors.
    # (If you want this list to be reproducible and research-backed, prefer --use-csi300 + TUSHARE_TOKEN)
    return [
        {"code6": "600519", "name": "贵州茅台"},
        {"code6": "000858", "name": "五粮液"},
        {"code6": "002594", "name": "比亚迪"},
        {"code6": "300750", "name": "宁德时代"},
        {"code6": "600036", "name": "招商银行"},  # will be filtered if exclude_banks
        {"code6": "600276", "name": "恒瑞医药"},
        {"code6": "000333", "name": "美的集团"},
        {"code6": "000651", "name": "格力电器"},
        {"code6": "601318", "name": "中国平安"},
        {"code6": "600030", "name": "中信证券"},
        {"code6": "600887", "name": "伊利股份"},
        {"code6": "601888", "name": "中国中免"},
        {"code6": "600309", "name": "万华化学"},
        {"code6": "600438", "name": "通威股份"},
        {"code6": "600050", "name": "中国联通"},
        {"code6": "600104", "name": "上汽集团"},
        {"code6": "601857", "name": "中国石油"},
        {"code6": "601088", "name": "中国神华"},
        {"code6": "600028", "name": "中国石化"},
        {"code6": "601899", "name": "紫金矿业"},
        {"code6": "600585", "name": "海螺水泥"},
        {"code6": "600019", "name": "宝钢股份"},
        {"code6": "300454", "name": "深信服"},
        {"code6": "002415", "name": "海康威视"},
        {"code6": "600066", "name": "宇通客车"},
        {"code6": "600600", "name": "青岛啤酒"},
        {"code6": "002352", "name": "顺丰控股"},
        {"code6": "601012", "name": "隆基绿能"},
        {"code6": "600703", "name": "三安光电"},
        {"code6": "002230", "name": "科大讯飞"},
        {"code6": "600000", "name": "浦发银行"},  # filtered
    ]


def load_samples(*, n: int, use_csi300: bool, category: str) -> list[dict[str, str]]:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if use_csi300 and token:
        try:
            return _try_load_csi300_samples(token, n, category=category)
        except Exception as e:
            print(f"WARN: CSI300 sample load failed, fallback to built-in list: {e}")

    # fallback list：只用于无 token 场景；此时类别识别不可靠。
    rows = _fallback_samples()
    if category == "bank":
        rows = [r for r in rows if "银行" in (r.get("name") or "")]
    elif category == "securities":
        rows = [r for r in rows if "证券" in (r.get("name") or "")]
    elif category == "insurance":
        rows = [r for r in rows if "保险" in (r.get("name") or "")]
    else:
        rows = [r for r in rows if all(x not in (r.get("name") or "") for x in ("银行", "证券", "保险"))]

    return rows[:n]


def build_provider(name: str) -> Any:
    name = name.strip().lower()
    if name == "akshare":
        return AkshareSinaProvider()
    if name == "akshare_ths":
        return AkshareThsProvider()
    if name == "tushare":
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        return TushareProvider(token=token or None)
    raise ValueError(f"unknown provider: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="number of sample companies")
    ap.add_argument(
        "--periods",
        type=str,
        default="2020-12-31,2024-12-31",
        help="comma-separated period_end dates (YYYY-MM-DD)",
    )
    ap.add_argument(
        "--providers",
        type=str,
        default="tushare,akshare_ths,akshare",
        help="comma-separated provider list: tushare,akshare_ths,akshare",
    )
    ap.add_argument("--statement-type", type=str, default="merged", choices=["merged", "parent"])
    ap.add_argument(
        "--category",
        type=str,
        default="non_financial",
        choices=["non_financial", "bank", "securities", "insurance"],
        help="company category",
    )
    ap.add_argument("--use-csi300", action="store_true", help="try to sample CSI300 via tushare")
    ap.add_argument("--out", type=str, default="output/subject_scan/report.json")
    ap.add_argument("--uncommon-threshold", type=float, default=0.15, help="<= threshold occurrence rate => candidate uncommon")
    args = ap.parse_args()

    samples = load_samples(n=args.n, use_csi300=args.use_csi300, category=str(args.category))
    periods = [parse_date(x.strip()) for x in args.periods.split(",") if x.strip()]
    providers = [x.strip() for x in args.providers.split(",") if x.strip()]

    total_slots = len(samples) * len(periods)

    # counters
    unmapped: dict[str, Counter[str]] = defaultdict(Counter)  # provider|prefix -> cn
    unmapped_examples: dict[str, dict[str, list[OccurExample]]] = defaultdict(lambda: defaultdict(list))

    mapped_counts: dict[str, Counter[str]] = defaultdict(Counter)  # provider|prefix -> key

    for p_name in providers:
        p = build_provider(p_name)
        if hasattr(p, "supports") and not p.supports():
            continue

        for s in samples:
            code6 = s["code6"]
            name = (s.get("name") or "").strip() or None
            ts_code = parse_code(code6).ts_code

            for pe in periods:
                try:
                    bundle = p.get_bundle(ts_code, pe, args.statement_type)
                except Exception:
                    continue

                for prefix, st_name, df in [
                    ("bs", "资产负债表", getattr(bundle, "balance_sheet", None)),
                    ("is", "利润表", getattr(bundle, "income_statement", None)),
                    ("cf", "现金流量表", getattr(bundle, "cashflow_statement", None)),
                ]:
                    if df is None or getattr(df, "empty", False):
                        continue
                    if "科目" not in df.columns:
                        continue

                    for raw in df["科目"].astype(str).tolist():
                        cn_raw = (raw or "").strip()
                        if not cn_raw:
                            continue
                        cn_norm = _normalize_subject(cn_raw)
                        spec = lookup_subject(prefix, cn_raw) or lookup_subject(prefix, cn_norm)
                        key = f"{p_name}|{prefix}"
                        if spec is None:
                            unmapped[key][cn_norm] += 1
                            ex = OccurExample(
                                code6=code6,
                                name=name,
                                period_end=pe.strftime("%Y-%m-%d"),
                                statement=st_name,
                            )
                            if len(unmapped_examples[key][cn_norm]) < 5:
                                unmapped_examples[key][cn_norm].append(ex)
                        else:
                            mapped_counts[key][spec.key] += 1

    # build uncommon candidates among mapped keys
    uncommon_candidates: dict[str, list[dict[str, Any]]] = {}
    for key, cnt in mapped_counts.items():
        items = []
        for k, c in cnt.most_common():
            rate = c / float(total_slots) if total_slots else 0.0
            if rate <= float(args.uncommon_threshold):
                items.append({"key": k, "count": c, "rate": rate})
        uncommon_candidates[key] = items

    out = {
        "meta": {
            "n_companies": len(samples),
            "periods": [p.strftime("%Y-%m-%d") for p in periods],
            "providers": providers,
            "total_company_period_slots": total_slots,
            "uncommon_threshold": float(args.uncommon_threshold),
        },
        "samples": samples,
        "unmapped": {k: v.most_common() for k, v in unmapped.items()},
        "unmapped_examples": {
            k: {cn: [asdict(e) for e in exs] for cn, exs in m.items()} for k, m in unmapped_examples.items()
        },
        "uncommon_candidates": uncommon_candidates,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out_path}")


if __name__ == "__main__":
    main()
