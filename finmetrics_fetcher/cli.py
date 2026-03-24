from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from finshared.global_datasets import fetch_financial_metrics_dataset

app = typer.Typer(add_completion=False)
console = Console()


@app.callback()
def _root():
    """全局财报指标抓取程序。"""


@app.command("fetch")
def fetch(
    out_dir: Path = typer.Option(Path("output"), "--out", help="输出根目录"),
    tushare_token: str | None = typer.Option(None, "--tushare-token", help="Tushare token"),
    limit: int | None = typer.Option(None, "--limit", help="仅抓前 N 家公司，便于调试"),
):
    """抓取公司财报指标，输出到独立全局目录。"""

    paths = fetch_financial_metrics_dataset(
        data_dir=out_dir.resolve(),
        tushare_token=tushare_token,
        limit=limit,
    )
    console.print(f"已输出财报指标 CSV: {paths.csv_path}")
    console.print(f"raw 目录: {paths.raw_dir}")


def main():
    app()


if __name__ == "__main__":
    main()
