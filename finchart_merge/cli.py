from __future__ import annotations

import typer

from finshared.cli_entry import run_typer_app_with_default_command
from finreport_charts.cli import merge as _merge_impl

app = typer.Typer(add_completion=False)


@app.command("version")
def version():
    """Show version."""

    try:
        from importlib.metadata import version as _v

        typer.echo(_v("finreport-fetcher"))
    except Exception:
        typer.echo("unknown")


@app.command("merge")
def merge(
    bar_template: str = typer.Option(..., "--bar-template", "-b", help="柱状图模板（bar + mode=trend）模板名或文件路径"),
    line_template: str = typer.Option(..., "--line-template", "-l", help="折线图模板（line + mode=price）模板名或文件路径"),
    templates: str = typer.Option("templates", "--templates", "-T", help="模板目录（单模板单文件 *.toml）"),
    code: str | None = typer.Option(None, "--code", "-c"),
    name: str | None = typer.Option(None, "--name", "-n"),
    category: str | None = typer.Option(None, "--category", "-g", help="公司分类名（见 config/company_categories.toml）"),
    category_config: str | None = typer.Option(None, "--category-config", "-G", help="分类配置文件路径（默认：config/company_categories.toml）"),
    start: str = typer.Option(..., "--start", "-s"),
    end: str = typer.Option(..., "--end", "-e"),
    data_dir: str | None = typer.Option(None, "--data-dir", "-d", help="财报数据目录（默认：若 ./output 存在则用 output，否则用当前目录）"),
    out_dir: str | None = typer.Option(None, "--out", "-o", help="输出目录（默认：每家公司输出到 {data_dir}/{公司名}_{code6}/charts/）"),
    provider: str = typer.Option("auto", "--provider", "-p"),
    statement_type: str = typer.Option("merged", "--statement-type", "-S"),
    tushare_token: str | None = typer.Option(None, "--tushare-token", "-k"),
    strict: bool = typer.Option(False, "--strict", "-x"),
):
    """独立的合并程序：将 bar(trend) + line(price) 合并为双轴 PNG。

    - 支持 --category 批量
    - 默认输出到每家公司 charts 目录
    """

    from pathlib import Path

    _merge_impl(
        bar_template=bar_template,
        line_template=line_template,
        templates=Path(templates),
        code=code,
        name=name,
        category=category,
        category_config=Path(category_config) if category_config else None,
        start=start,
        end=end,
        data_dir=Path(data_dir) if data_dir else None,
        out_dir=Path(out_dir) if out_dir else None,
        provider=provider,
        statement_type=statement_type,
        tushare_token=tushare_token,
        strict=strict,
    )


def main():
    run_typer_app_with_default_command(app, default_command="merge")


if __name__ == "__main__":
    main()
