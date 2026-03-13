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

XLSX="$OUT_DIR/600519_merged_20241231.xlsx"
if [ ! -f "$XLSX" ]; then
  echo "[smoke] expected xlsx not found: $XLSX" >&2
  exit 1
fi

# 2) validate columns exist
python3 - <<'PY'
import pandas as pd
from pathlib import Path
p = Path('_smoke_output/600519_merged_20241231.xlsx')
df = pd.read_excel(p, sheet_name='利润表', header=2)
need = ['key','科目','数值','科目_CN','科目_EN']
missing = [c for c in need if c not in df.columns]
assert not missing, f'missing columns: {missing}'
assert df['key'].isna().sum()==0, 'key has empty rows'
print('[smoke] fetcher excel columns OK')
PY

# 3) optional: charts bar using key
python3 -m finreport_charts bar --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --statement 利润表 --item is.net_profit --transform q \
  --data-dir "$OUT_DIR" --out "$CHART_DIR"

echo "[smoke] OK"