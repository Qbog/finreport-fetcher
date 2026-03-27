from __future__ import annotations

from pathlib import Path
import math

import numpy as np
import pandas as pd

from ..utils.mpl_style import apply_pretty_style
from ..utils.numfmt import UnitScale, choose_unit_scale, fmt_scaled, fmt_tick


def render_merge_png(
    *,
    df_line: pd.DataFrame,
    x_col: str,
    line_col: str,
    df_bar: pd.DataFrame | None,
    bar_x_col: str,
    bar_col: str,
    out_png: Path,
    title: str,
    x_label: str = "",
    bar_label: str = "",
    line_label: str = "",
    bar_color: str = "#4E79A7",
    line_color: str = "#F28E2B",
    month_interval: int = 1,
    bar_width_days: int = 8,
    unit_scale: UnitScale | None = None,
    figsize: tuple[float, float] | None = None,
    xtick_dates: list[str] | None = None,
    xtick_labels: list[str] | None = None,
):
    """Merge a line time-series with sparse bars on the same datetime x-axis.

    - line: df_line[x_col] must be parseable datetime or date.
    - bars: df_bar can be None; if provided, draw bars at bar_x_col dates.

    Output: PNG only.
    """

    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import FuncFormatter

    apply_pretty_style()

    if df_line is None or df_line.empty:
        raise RuntimeError("df_line 为空，无法绘制")

    x_line = pd.to_datetime(df_line[x_col], errors="coerce").to_numpy()
    y_line = pd.to_numeric(df_line[line_col], errors="coerce").to_numpy()

    # bar unit scale (left axis)
    us = unit_scale
    if us is None and df_bar is not None and (not df_bar.empty) and (bar_col in df_bar.columns):
        try:
            v = float(pd.to_numeric(df_bar[bar_col], errors="coerce").abs().max())
            if math.isfinite(v):
                us = choose_unit_scale(v)
        except Exception:
            us = None

    n_points = max(int(len(df_line.index)), 1)
    fig_size = figsize or (max(14.0, min(24.0, 12.5 + n_points / 260.0)), 7.4)
    fig, ax1 = plt.subplots(figsize=fig_size)
    ax1.set_axisbelow(True)
    ax1.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.22)

    bar_cont = None
    by_numeric = None

    # bars on left axis
    if df_bar is not None and (not df_bar.empty):
        bx = pd.to_datetime(df_bar[bar_x_col], errors="coerce").to_numpy()
        by_numeric = pd.to_numeric(df_bar[bar_col], errors="coerce")
        by = by_numeric.to_numpy()
        # width in days (timedelta is more robust across datetime types)
        w = np.timedelta64(int(bar_width_days or 12), "D")
        bar_cont = ax1.bar(
            bx,
            by,
            width=w,
            color=bar_color,
            alpha=0.88,
            edgecolor="#F4F6F8",
            linewidth=0.9,
            label=bar_label or bar_col,
            zorder=2,
        )

    ax1.set_xlabel(x_label or "时间")
    ax1.set_ylabel(bar_label or bar_col, color=bar_color)
    ax1.tick_params(axis="y", colors=bar_color)
    if us is not None:
        ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: fmt_tick(v, us)))

    # line on right axis
    ax2 = ax1.twinx()
    ax2.plot(x_line, y_line, color=line_color, linewidth=1.55, label=line_label or line_col, zorder=3)
    ax2.set_ylabel(line_label or line_col, color=line_color)
    ax2.tick_params(axis="y", colors=line_color)

    # x axis ticks
    if xtick_dates:
        ticks = pd.to_datetime(pd.Series(xtick_dates), errors="coerce").dropna().to_numpy()
        if len(ticks) > 0:
            ax1.set_xticks(ticks)
            if xtick_labels and len(xtick_labels) == len(ticks):
                ax1.set_xticklabels(list(xtick_labels), rotation=30)
            else:
                ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    else:
        # fallback: monthly ticks
        locator = mdates.MonthLocator(interval=max(int(month_interval), 1))
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    fig.autofmt_xdate(rotation=30)

    if by_numeric is not None and us is not None and bar_cont is not None:
        finite_vals = by_numeric.dropna()
        if not finite_vals.empty:
            ymax = float(finite_vals.max())
            ymin = float(finite_vals.min())
            span = max(abs(ymax - ymin), abs(ymax), 1.0)
            cur_lo, cur_hi = ax1.get_ylim()
            ax1.set_ylim(min(cur_lo, ymin - 0.08 * span), max(cur_hi, ymax + 0.20 * span))
        for patch in bar_cont.patches:
            h = patch.get_height()
            if h is None or (isinstance(h, float) and not math.isfinite(h)):
                continue
            x0 = patch.get_x() + patch.get_width() / 2
            txt = fmt_scaled(float(h), us)
            ax1.text(
                x0,
                h,
                txt,
                ha="center",
                va="bottom" if h >= 0 else "top",
                fontsize=9,
                color="#EAEAEA",
                fontweight="semibold",
                zorder=4,
            )

    ax1.margins(x=0.01)
    ax1.set_title(title, pad=14)

    # merged legend
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    if h1 or h2:
        ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    plt.close(fig)
