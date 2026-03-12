from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ExcelExportResult:
    path: str


def _autofit_worksheet(ws):
    # 简单自适应列宽：按单元格字符串长度估算
    for col_cells in ws.columns:
        max_len = 0
        col_letter = col_cells[0].column_letter
        for cell in col_cells:
            v = cell.value
            if v is None:
                continue
            s = str(v)
            if len(s) > max_len:
                max_len = len(s)
        ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), 60)


def export_bundle_to_excel(
    out_path: Path,
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    cashflow_statement: pd.DataFrame,
    meta: dict,
):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        balance_sheet.to_excel(writer, sheet_name="资产负债表", index=False)
        income_statement.to_excel(writer, sheet_name="利润表", index=False)
        cashflow_statement.to_excel(writer, sheet_name="现金流量表", index=False)

    # 美化（openpyxl）
    from openpyxl import load_workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = load_workbook(out_path)

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    zebra_fill = PatternFill("solid", fgColor="F7F7F7")

    for sname in ["资产负债表", "利润表", "现金流量表"]:
        ws = wb[sname]
        ws.freeze_panes = "C2"  # 冻结首行 + 前两列（报告期末日/科目）

        # 表头
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment

        # 交替底色（数据行）
        for r in range(2, ws.max_row + 1):
            if (r - 2) % 2 == 1:
                for c in range(1, ws.max_column + 1):
                    ws.cell(r, c).fill = zebra_fill

        # 数字列格式：对“数值”列做千分位
        # 默认列结构: 报告期末日 / 科目 / 数值 / (可选: PDF链接/本地路径/备注)
        # 找到名为“数值”的列
        value_col = None
        for c in range(1, ws.max_column + 1):
            if ws.cell(1, c).value == "数值":
                value_col = c
                break
        if value_col:
            for r in range(2, ws.max_row + 1):
                cell = ws.cell(r, value_col)
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "#,##0.00" if isinstance(cell.value, float) else "#,##0"
                    cell.alignment = Alignment(horizontal="right")

            # 负数红色
            col_letter = ws.cell(1, value_col).column_letter
            rng = f"{col_letter}2:{col_letter}{ws.max_row}"
            ws.conditional_formatting.add(
                rng,
                CellIsRule(operator="lessThan", formula=["0"], font=Font(color="9C0006")),
            )

        _autofit_worksheet(ws)

    # meta sheet
    ws_meta = wb.create_sheet("META")
    ws_meta.append(["key", "value"])
    for k, v in meta.items():
        ws_meta.append([str(k), str(v)])
    ws_meta.freeze_panes = "A2"
    _autofit_worksheet(ws_meta)

    wb.save(out_path)

    return ExcelExportResult(path=str(out_path))
