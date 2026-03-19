#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/3] compileall"
python3 -m compileall -q finreport_fetcher finreport_charts finprice_fetcher

echo "[2/3] pytest"
python3 -m pytest -q

echo "[3/3] OK"
