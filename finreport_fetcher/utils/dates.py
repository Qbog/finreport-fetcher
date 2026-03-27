from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


def parse_date(d: str) -> date:
    d = str(d or "").strip()
    key = d.lower()
    if key in {"now", "today"}:
        return date.today()
    if key == "yesterday":
        return date.today() - timedelta(days=1)

    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(d, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"无法解析日期: {d}. 支持格式: YYYY-MM-DD / YYYYMMDD / YYYY/MM/DD；也支持别名: now / yesterday")


def yyyymmdd(dt: date) -> str:
    return dt.strftime("%Y%m%d")


def quarter_ends_between(start: date, end: date) -> list[date]:
    if start > end:
        start, end = end, start

    # 每年固定 4 个报告期末
    qmd = [(3, 31), (6, 30), (9, 30), (12, 31)]
    res: list[date] = []
    for y in range(start.year, end.year + 1):
        for m, d in qmd:
            dt = date(y, m, d)
            if start <= dt <= end:
                res.append(dt)
    return sorted(res)


def candidate_quarter_ends_before(dt: date, years_back: int = 5) -> list[date]:
    # 生成 dt 之前（含）向前若干年的所有报告期末日，倒序
    qmd = [(12, 31), (9, 30), (6, 30), (3, 31)]
    res: list[date] = []
    for y in range(dt.year, dt.year - years_back - 1, -1):
        for m, d in qmd:
            q = date(y, m, d)
            if q <= dt:
                res.append(q)
    res = sorted(set(res), reverse=True)
    return res


@dataclass(frozen=True)
class ReportPeriod:
    period_end: date

    @property
    def category_cninfo(self) -> str:
        # 用于巨潮分类过滤
        if (self.period_end.month, self.period_end.day) == (12, 31):
            return "年报"
        if (self.period_end.month, self.period_end.day) == (6, 30):
            return "半年报"
        if (self.period_end.month, self.period_end.day) == (3, 31):
            return "一季报"
        if (self.period_end.month, self.period_end.day) == (9, 30):
            return "三季报"
        return ""
