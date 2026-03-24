#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DST_DIR="/mnt/hgfs/share_with_vm/a_share_finreport_fetcher"

# Sync project code to the VM shared folder.
# Requirement:
# - keep user's output data intact (do not wipe output/*.xlsx)

rsync -a --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '_smoke_output/' \
  --exclude '_smoke_charts/' \
  --exclude '_chart_data/' \
  --exclude '_charts_out/' \
  --exclude '_charts_pie/' \
  --exclude '_charts_combo/' \
  --exclude '_charts_tpl/' \
  --exclude 'charts_output/' \
  \
  --include 'output/' \
  --exclude 'output/**' \
  \
  "${SRC_DIR}/" "${DST_DIR}/"

echo "[sync] synced to ${DST_DIR}"