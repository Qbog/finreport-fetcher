from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from finshared.cli_entry import run_typer_app_with_default_command

from finshared.global_datasets import clear_dataset_raw_files, fetch_company_basics_dataset, resolve_existing_dataset_paths

app = typer.Typer(add_completion=False)
console = Console()


@app.callback()
def _root():
    """全局公司基础信息抓取程序。"""


@app.command("fetch")
def fetch(
    out_dir: Path = typer.Option(Path("output"), "--out", "-o", help="输出根目录"),
    tushare_token: str | None = typer.Option(None, "--tushare-token", "-k", help="Tushare token，可选"),
    clear_raw: bool = typer.Option(False, "--clear-raw", "-x", help="清理旧 raw 文件，仅保留 latest.json 指向的最新 raw"),
):
    """抓取全部公司基础信息，输出到独立全局目录。"""

    paths = fetch_company_basics_dataset(data_dir=out_dir.resolve(), tushare_token=tushare_token)
    console.print(f"已输出公司基础信息 CSV: {paths.csv_path}")
    console.print(f"raw 目录: {paths.raw_dir}")
    if clear_raw:
        current_paths = resolve_existing_dataset_paths(out_dir.resolve(), "company_basics", "company_basics.csv")
        removed = clear_dataset_raw_files(current_paths)
        console.print(f"已清理旧 raw 文件 {len(removed)} 个")


def main():
    run_typer_app_with_default_command(app, default_command="fetch")


if __name__ == "__main__":
    main()
