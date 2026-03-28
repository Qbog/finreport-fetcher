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
    line_col: str | None = None,
    df_bar: pd.DataFrame | None,
    bar_x_col: str,
    bar_col: str,
    out_png: Path,
    title: str,
    x_label: str = "",
    bar_label: str = "",
    line_label: str = "",
    line_series: list[tuple[str, str, str | None]] | None = None,
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

    line_defs = list(line_series or [])
    if not line_defs and line_col:
        line_defs = [(line_col, line_label or line_col, line_color)]
    if not line_defs:
        raise RuntimeError("merge 图缺少可用折线 series")

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

    # line axes on right side (support multi-line / multi-axis)
    line_palette = [
        "#F59E0B",
        "#22C55E",
        "#38BDF8",
        "#A78BFA",
        "#F472B6",
        "#FB7185",
    ]
    extra_right = max(len(line_defs) - 1, 0)
    ax2 = None
    line_handles = []
    line_labels = []
    for idx, (col_name, label_name, color_name) in enumerate(line_defs):
        if col_name not in df_line.columns:
            continue
        axis = ax1.twinx()
        if idx > 0:
            axis.spines["right"].set_position(("axes", 1.0 + 0.10 * idx))
            axis.spines["right"].set_visible(True)
            axis.patch.set_alpha(0.0)
        color0 = color_name or line_palette[idx % len(line_palette)]
        y_line = pd.to_numeric(df_line[col_name], errors="coerce").to_numpy()
        line_us = None
        try:
            vmax = float(pd.to_numeric(df_line[col_name], errors="coerce").abs().max())
            if math.isfinite(vmax):
                line_us = choose_unit_scale(vmax)
        except Exception:
            line_us = None
        (handle,) = axis.plot(x_line, y_line, color=color0, linewidth=1.55, marker=None, label=label_name or col_name, zorder=3 + idx)
        axis.set_ylabel(f"{label_name}（{line_us.unit}）" if line_us and line_us.unit else (label_name or col_name), color=color0)
        axis.tick_params(axis="y", colors=color0)
        if line_us is not None:
            axis.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos, us=line_us: fmt_tick(v, us)))
        line_handles.append(handle)
        line_labels.append(label_name or col_name)
        if ax2 is None:
            ax2 = axis

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
        # long-range daily merge charts need sparse, readable ticks
        locator = mdates.AutoDateLocator(minticks=5, maxticks=8)
        ax1.xaxis.set_major_locator(locator)
        ax1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    fig.autofmt_xdate(rotation=30)

    if by_numeric is not None and us is not None and bar_cont is not None:
        finite_vals = by_numeric.dropna()
        if not finite_vals.empty:
            ymax = float(finite_vals.max())
            ymin = float(finite_vals.min())
            span = max(abs(ymax - ymin), abs(ymax), 1.0)
            cur_lo, cur_hi = ax1.get_ylim()
            ax1.set_ylim(min(cur_lo, ymin - 0.08 * span), max(cur_hi, ymax + 0.20 * span))

        patches = list(bar_cont.patches)
        label_step = 1
        n_bars = len(patches)
        if n_bars > 24:
            label_step = 4
        elif n_bars > 12:
            label_step = 2

        for idx, patch in enumerate(patches):
            if idx % label_step != 0 and idx != n_bars - 1:
                continue
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
    if h1 or line_handles:
        ax1.legend(h1 + line_handles, l1 + line_labels, loc="upper left")

    right_margin = max(0.62, 0.92 - 0.08 * extra_right)
    fig.subplots_adjust(left=0.06, right=right_margin, bottom=0.14, top=0.90)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    plt.close(fig)
