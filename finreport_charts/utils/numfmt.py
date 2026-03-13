from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitScale:
    scale: float
    unit: str


def choose_unit_scale(max_abs: float) -> UnitScale:
    """Choose a Chinese-friendly scale/unit for amounts."""

    v = float(abs(max_abs or 0.0))
    if v >= 1e8:
        return UnitScale(scale=1e8, unit="亿")
    if v >= 1e4:
        return UnitScale(scale=1e4, unit="万")
    return UnitScale(scale=1.0, unit="元")


def fmt_scaled(v: float, us: UnitScale, *, decimals: int | None = None) -> str:
    x = float(v) / float(us.scale or 1.0)
    ax = abs(x)

    if decimals is None:
        if ax >= 100:
            decimals = 0
        elif ax >= 10:
            decimals = 1
        else:
            decimals = 2

    s = f"{x:,.{decimals}f}"
    # strip trailing zeros
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}{us.unit}"


def fmt_tick(v: float, us: UnitScale) -> str:
    x = float(v) / float(us.scale or 1.0)
    ax = abs(x)
    if ax < 1e-9:
        return f"0{us.unit}"
    # ticks prefer fewer decimals
    if ax >= 100:
        s = f"{x:,.0f}"
    elif ax >= 10:
        s = f"{x:,.1f}".rstrip("0").rstrip(".")
    else:
        s = f"{x:,.2f}".rstrip("0").rstrip(".")
    return f"{s}{us.unit}"
