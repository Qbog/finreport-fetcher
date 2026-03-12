from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..utils.mpl_style import apply_pretty_style


def render_bar_png(df: pd.DataFrame, *, title: str, x_col: str, y_col: str, out_png: Path, y_label: str = ""):
    import matplotlib.pyplot as plt

    apply_pretty_style()

    x = df[x_col].astype(str).tolist()
    y = df[y_col].tolist()

    fig, ax = plt.subplots()
    ax.bar(x, y, color="#1F77B4")
    ax.set_title(title)
    ax.set_xlabel("时间")
    ax.set_ylabel(y_label or y_col)
    ax.tick_params(axis="x", rotation=45)

    # 数值标签（可选：只标注少量点避免拥挤）
    if len(y) <= 16:
        for i, v in enumerate(y):
            if v is None:
                continue
            ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=9, rotation=0)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def write_bar_excel(df: pd.DataFrame, *, title: str, x_col: str, y_col: str, out_xlsx: Path, y_label: str = ""):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill

    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    # 标题
    ws["A1"].value = title
    ws.merge_cells("A1:B1")
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="0B2F4F")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    # 写数据
    ws.append([x_col, y_col])
    for _, r in df.iterrows():
        ws.append([str(r[x_col]), float(r[y_col]) if pd.notna(r[y_col]) else None])

    # 格式
    for row in ws.iter_rows(min_row=3, min_col=2, max_col=2, max_row=ws.max_row):
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
    chart.y_axis.title = y_label or y_col
    chart.x_axis.title = "时间"

    data = Reference(ws, min_col=2, min_row=2, max_row=ws.max_row)
    cats = Reference(ws, min_col=1, min_row=3, max_row=ws.max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width = 22
    chart.height = 12

    ws_chart.add_chart(chart, "A3")

    wb.save(out_xlsx)
