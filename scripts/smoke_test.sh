#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH=.

OUT_DIR="${ROOT_DIR}/_smoke_output"
CHART_DIR="${ROOT_DIR}/_smoke_charts"
rm -rf "$OUT_DIR" "$CHART_DIR"
mkdir -p "$OUT_DIR" "$CHART_DIR"

# 1) fetch one period (no pdf for speed)
python3 -m finreport_fetcher fetch --code 600519 --date 2025-02-01 --out "$OUT_DIR" --no-clean

# 1b) also verify running from output/ works without PYTHONPATH (shim)
mkdir -p output
( cd output && python3 -m finreport_fetcher version >/dev/null )

# locate xlsx (new layout: _smoke_output/{公司名}_600519/reports/*.xlsx)
XLSX="$(ls -1 "$OUT_DIR"/*_600519/reports/600519_merged_*.xlsx 2>/dev/null | sort | tail -n 1 || true)"
if [ -z "$XLSX" ] || [ ! -f "$XLSX" ]; then
  echo "[smoke] expected xlsx not found under: $OUT_DIR/*_600519/reports/600519_merged_*.xlsx" >&2
  echo "[smoke] tree:" >&2
  find "$OUT_DIR" -maxdepth 4 -type f -print >&2 || true
  exit 1
fi

echo "[smoke] using xlsx: $XLSX"

# 2) validate columns exist + cashflow indent
python3 - "$XLSX" <<'PY'
import sys
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook

p = Path(sys.argv[1])

# column checks
for sheet in ['利润表','资产负债表','现金流量表']:
    df = pd.read_excel(p, sheet_name=sheet, header=2)
    need = ['科目','数值','key']
    missing = [c for c in need if c not in df.columns]
    assert not missing, f'[{sheet}] missing columns: {missing}'
    assert df['key'].isna().sum()==0, f'[{sheet}] key has empty rows'
    assert '科目_CN' not in df.columns, f'[{sheet}] 科目_CN should not be exported'
    assert '科目_EN' not in df.columns, f'[{sheet}] 科目_EN should not be exported'

# cashflow style/indent checks (openpyxl)
wb = load_workbook(p)
ws = wb['现金流量表']
header_row = 3
headers = [ws.cell(header_row, c).value for c in range(1, ws.max_column+1)]
cn_col = headers.index('科目_CN') + 1 if '科目_CN' in headers else headers.index('科目') + 1
subj_col = headers.index('科目') + 1

# find a known header row by 科目_CN, but validate indent on 科目列（真实展示列）
target = '一、经营活动产生的现金流量'
row_idx = None
for r in range(4, ws.max_row+1):
    v = ws.cell(r, cn_col).value
    if isinstance(v, str) and v.strip() == target:
        row_idx = r
        break
assert row_idx is not None, 'cashflow header row not found'

indent_header = ws.cell(row_idx, subj_col).alignment.indent or 0
indent_next = ws.cell(row_idx+1, subj_col).alignment.indent or 0
assert indent_header == 0, f'cashflow header indent expected 0, got {indent_header}'
assert indent_next >= 1, f'cashflow item indent expected >=1, got {indent_next}'

print('[smoke] fetcher excel columns OK + cashflow indent OK')
PY

# 3) charts run (template-only workflow)
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir "$OUT_DIR" --templates templates --template net_profit_q

RUN_PNG="$(ls -1 "$OUT_DIR"/*_600519/charts/net_profit_q_600519_20240101_20241231.png 2>/dev/null | head -n 1 || true)"
RUN_XLSX="$(ls -1 "$OUT_DIR"/*_600519/charts/net_profit_q_600519_20240101_20241231.xlsx 2>/dev/null | head -n 1 || true)"
if [ -z "$RUN_PNG" ] || [ ! -f "$RUN_PNG" ] || [ -z "$RUN_XLSX" ] || [ ! -f "$RUN_XLSX" ]; then
  echo "[smoke] run outputs not found under: $OUT_DIR/*_600519/charts/" >&2
  find "$OUT_DIR" -maxdepth 4 -type f -print >&2 || true
  exit 1
fi

echo "[smoke] OK"
