from __future__ import annotations

from datetime import date


def quarter_from_ytd(period_end: date, ytd_map: dict[date, float]) -> float | None:
    """将某报告期末的年内累计值（YTD）转换为当季值（单季）。

    规则（同一财年内差分）：
    - Q1：单季 = Q1 YTD
    - Q2：单季 = Q2 YTD - Q1 YTD
    - Q3：单季 = Q3 YTD - Q2 YTD
    - Q4：单季 = Q4 YTD - Q3 YTD

    若缺少上一期 YTD，则返回 None。
    """

    cur = ytd_map.get(period_end)
    if cur is None:
        return None

    m, d = period_end.month, period_end.day
    if (m, d) == (3, 31):
        return float(cur)

    # previous quarter end in the same year
    if (m, d) == (6, 30):
        prev = date(period_end.year, 3, 31)
    elif (m, d) == (9, 30):
        prev = date(period_end.year, 6, 30)
    elif (m, d) == (12, 31):
        prev = date(period_end.year, 9, 30)
    else:
        return None

    p = ytd_map.get(prev)
    if p is None:
        return None

    return float(cur) - float(p)


def ttm_from_ytd(period_end: date, ytd_map: dict[date, float]) -> float | None:
    """将某报告期末的年内累计值（YTD）转换为 TTM。

    规则：
    - Q4(12-31)：TTM=年报值
    - 其他季度：TTM = 当前YTD + (上一年年报YTD - 上一年同季度YTD)

    需要 ytd_map 至少包含：
    - 当前 period_end
    - 上一年 12-31
    - 上一年同季度
    """

    cur = ytd_map.get(period_end)
    if cur is None:
        return None

    if (period_end.month, period_end.day) == (12, 31):
        return float(cur)

    prev_y = period_end.year - 1
    prev_annual = date(prev_y, 12, 31)
    prev_same = date(prev_y, period_end.month, period_end.day)

    a = ytd_map.get(prev_annual)
    s = ytd_map.get(prev_same)
    if a is None or s is None:
        return None

    return float(cur) + (float(a) - float(s))
