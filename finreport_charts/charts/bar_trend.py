from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..utils.mpl_style import apply_pretty_style


def render_bar_png(
    df: pd.DataFrame,
    *,
    title: str,
    x_col: str,
    y_col: str,
    out_png: Path,
    y_label: str = "",
    x_label: str = "",
):
    """Single-series bar chart (backward compatible)."""

    render_bars_png(
        df,
        title=title,
        x_col=x_col,
        series=[(y_col, y_col)],
        out_png=out_png,
        x_label=x_label,
        y_label=y_label or y_col,
    )


def render_bars_png(
    df: pd.DataFrame,
    *,
    title: str,
    x_col: str,
    series: list[tuple[str, str]],
    out_png: Path,
    x_label: str = "时间",
    y_label: str = "",
):
    """Multi-series (grouped) bar chart.

    series: [(col_name_in_df, display_label), ...]
    """

    import matplotlib.pyplot as plt
    import numpy as np

    apply_pretty_style()

    x = df[x_col].astype(str).tolist()
    n = len(x)
    k = max(1, len(series))

    idx = np.arange(n)
    width = 0.8 / k

    fig, ax = plt.subplots(figsize=(max(6, min(22, 0.7 * n + 4)), 5))

    for j, (col, label) in enumerate(series):
        y = df[col].tolist()
        offset = (j - (k - 1) / 2) * width
        ax.bar(idx + offset, y, width=width, label=label)

    ax.set_title(title)
    ax.set_xlabel(x_label or "时间")
    ax.set_ylabel(y_label)
    ax.set_xticks(idx)
    ax.set_xticklabels(x, rotation=45, ha="right")

    if k > 1:
        ax.legend(loc="best")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def write_bar_excel(
    df: pd.DataFrame,
    *,
    title: str,
    x_col: str,
    y_col: str,
    out_xlsx: Path,
    y_label: str = "",
    x_label: str = "",
):
    """Single-series Excel output (backward compatible)."""

    write_bars_excel(
        df,
        title=title,
        x_col=x_col,
        series=[(y_col, y_col)],
        out_xlsx=out_xlsx,
        x_label=x_label,
        y_label=y_label or y_col,
    )


def write_bars_excel(
    df: pd.DataFrame,
    *,
    title: str,
    x_col: str,
    series: list[tuple[str, str]],
    out_xlsx: Path,
    x_label: str = "时间",
    y_label: str = "",
):
    """Multi-series bar chart exported to Excel.

    series: [(col_name_in_df, display_label), ...]
    """

    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    # 标题
    # 写入宽度取决于列数
    ncols = 1 + max(1, len(series))
    ws["A1"].value = title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="0B2F4F")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    # 表头
    header = [x_col] + [label for _, label in series]
    ws.append(header)

    # 数据
    for _, r in df.iterrows():
        row = [str(r[x_col])]
        for col, _label in series:
            v = r.get(col)
            row.append(float(v) if pd.notna(v) else None)
        ws.append(row)

    # number formats
    for row in ws.iter_rows(min_row=3, min_col=2, max_col=ncols, max_row=ws.max_row):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "#,##0"

    # 图表
    ws_chart = wb.create_sheet("chart")
    ws_chart["A1"].value = title
    ws_chart["A1"].font = Font(bold=True, size=14)

    chart = BarChart()
    chart.type = "col"
    chart.title = title
    chart.y_axis.title = y_label
    chart.x_axis.title = x_label or "时间"

    data = Reference(ws, min_col=2, min_row=2, max_col=ncols, max_row=ws.max_row)
    cats = Reference(ws, min_col=1, min_row=3, max_row=ws.max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width = 22
    chart.height = 12

    ws_chart.add_chart(chart, "A3")

    wb.save(out_xlsx)
