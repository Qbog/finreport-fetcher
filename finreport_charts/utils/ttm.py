from __future__ import annotations

from datetime import date


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
