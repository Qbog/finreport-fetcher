from __future__ import annotations

from pathlib import Path
import math

import numpy as np
import pandas as pd

from ..utils.mpl_style import apply_pretty_style
from ..utils.numfmt import UnitScale, choose_unit_scale, fmt_tick


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

    fig_size = figsize or (12, 6)
    fig, ax1 = plt.subplots(figsize=fig_size)

    # bars on left axis
    if df_bar is not None and (not df_bar.empty):
        bx = pd.to_datetime(df_bar[bar_x_col], errors="coerce").to_numpy()
        by = pd.to_numeric(df_bar[bar_col], errors="coerce").to_numpy()
        # width in days (timedelta is more robust across datetime types)
        w = np.timedelta64(int(bar_width_days or 12), "D")
        ax1.bar(bx, by, width=w, color=bar_color, alpha=0.75, label=bar_label or bar_col, zorder=2)

    ax1.set_xlabel(x_label or "时间")
    ax1.set_ylabel(bar_label or bar_col)
    if us is not None:
        ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: fmt_tick(v, us)))

    # line on right axis
    ax2 = ax1.twinx()
    ax2.plot(x_line, y_line, color=line_color, linewidth=2, label=line_label or line_col, zorder=3)
    ax2.set_ylabel(line_label or line_col)

    # x axis ticks: show months
    locator = mdates.MonthLocator(interval=max(int(month_interval), 1))
    ax1.xaxis.set_major_locator(locator)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=30)

    ax1.set_title(title)

    # merged legend
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    if h1 or h2:
        ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    plt.close(fig)
