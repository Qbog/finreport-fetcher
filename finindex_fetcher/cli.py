from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", message=r"Pandas requires version.*", category=UserWarning)

import pandas as pd
import typer
from rich.console import Console

from .raw_store import RawIndexStore

app = typer.Typer(add_completion=False)
console = Console()

INDEX_MAP = {
    '上证': ('sh000001', '上证综指'),
    '上证综指': ('sh000001', '上证综指'),
    'sh000001': ('sh000001', '上证综指'),
    '深证': ('sz399001', '深证成指'),
    '深证成指': ('sz399001', '深证成指'),
    'sz399001': ('sz399001', '深证成指'),
    '创业板': ('sz399006', '创业板指'),
    '创业板指': ('sz399006', '创业板指'),
    'sz399006': ('sz399006', '创业板指'),
    '北证': ('bj899050', '北证50'),
    '北证50': ('bj899050', '北证50'),
    'bj899050': ('bj899050', '北证50'),
}
DEFAULT_INDEXES = ['上证', '深证', '创业板', '北证']


def log_info(msg: str):
    console.print(msg)


def parse_date_local(s: str):
    return datetime.strptime(str(s).strip(), '%Y-%m-%d').date()


def resolve_indexes(items: list[str] | None) -> list[tuple[str, str]]:
    out = []
    seen = set()
    for raw in (items or DEFAULT_INDEXES):
        key = str(raw).strip()
        if key not in INDEX_MAP:
            raise typer.BadParameter(f'不支持的指数：{raw}（当前支持：上证/深证/创业板/北证）')
        code, label = INDEX_MAP[key]
        if code in seen:
            continue
        seen.add(code)
        out.append((code, label))
    return out


def fetch_index_full_history(symbol: str) -> pd.DataFrame:
    import akshare as ak
    df = ak.stock_zh_index_daily_tx(symbol=symbol)
    out = df.rename(columns={'date':'date','open':'open','close':'close','high':'high','low':'low','amount':'amount'}).copy()
    out['date'] = pd.to_datetime(out['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    return out.dropna(subset=['date']).sort_values('date').reset_index(drop=True)


@app.callback()
def _root():
    """大盘指数抓取程序。"""


@app.command('fetch')
def fetch(
    index: list[str] = typer.Option(None, '--index', help='可重复：上证/深证/创业板/北证 或对应代码'),
    start: str | None = typer.Option(None, '--start'),
    end: str | None = typer.Option(None, '--end'),
    out: Path = typer.Option(Path('output'), '--out'),
    no_clean: bool = typer.Option(False, '--no-clean'),
    update_raw: bool = typer.Option(False, '--update-raw'),
    clear_raw: bool = typer.Option(False, '--clear-raw'),
):
    maintenance_only = (update_raw or clear_raw) and not start and not end
    if not maintenance_only and ((start and not end) or (end and not start)):
        raise typer.BadParameter('--start 与 --end 必须同时提供')
    if not maintenance_only and not start and not end:
        raise typer.BadParameter('必须提供 --start/--end；若仅维护 raw，可使用 --update-raw/--clear-raw')
    targets = resolve_indexes(index)
    for code, label in targets:
        root = out.resolve() / '_global' / 'indexes' / code
        out_dir = root / 'index'
        out_dir.mkdir(parents=True, exist_ok=True)
        store = RawIndexStore(root)
        if maintenance_only and clear_raw and not update_raw:
            providers = store.available_providers()
            if not providers:
                log_info(f'未发现可清理的指数原始数据：{label}')
                continue
            for p in providers:
                removed = store.clear_old_snapshots(p)
                log_info(f'{label} 指数 provider={p} 清理旧快照 {len(removed)} 个')
            continue
        if update_raw:
            df_raw = fetch_index_full_history(code)
            sid = store.save('tencent', df_raw, snapshot=True, metadata={'scope':'full_history','symbol':code,'label':label,'provider':'tencent'})
            log_info(f'已更新指数原始数据：{label} snapshot={sid}')
        else:
            df_raw = store.load('tencent')
            if df_raw is None or df_raw.empty:
                df_raw = fetch_index_full_history(code)
                store.save('tencent', df_raw, snapshot=False, metadata={'scope':'full_history','symbol':code,'label':label,'provider':'tencent'})
        if clear_raw:
            removed = store.clear_old_snapshots('tencent')
            log_info(f'{label} 指数清理旧快照 {len(removed)} 个')
        if maintenance_only:
            continue
        s = parse_date_local(start)
        e = parse_date_local(end)
        sub = df_raw[(pd.to_datetime(df_raw['date']) >= pd.Timestamp(s)) & (pd.to_datetime(df_raw['date']) <= pd.Timestamp(e))].copy()
        out_csv = out_dir / f'{code}.csv'
        out_xlsx = out_dir / f'{code}.xlsx'
        if no_clean and out_csv.exists():
            log_info(f'已存在，跳过重生成：{out_csv}')
            continue
        sub.to_csv(out_csv, index=False, encoding='utf-8-sig')
        with pd.ExcelWriter(out_xlsx, engine='openpyxl') as w:
            sub.to_excel(w, sheet_name='index', index=False)
        log_info(f'已输出: {out_csv} / {out_xlsx} (rows={len(sub)})')


def main():
    app()


if __name__ == '__main__':
    main()
