from __future__ import annotations

from pathlib import Path

import typer

from finshared.cli_entry import run_typer_app_with_default_command
from finshared.company_categories import default_company_categories_path

from .server import serve_app

app = typer.Typer(add_completion=False)


@app.callback()
def _root():
    """财报分析 Web 服务。"""


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="监听地址"),
    port: int = typer.Option(8787, "--port", "-p", help="监听端口"),
    data_dir: Path = typer.Option(Path("output"), "--data-dir", "-d", help="财报/图表数据根目录"),
    templates_dir: Path = typer.Option(Path("templates"), "--templates", "-T", help="模板目录"),
    category_config: Path = typer.Option(default_company_categories_path(), "--category-config", "-G", help="公司分类配置文件"),
):
    """启动财报分析 Web 服务。"""

    serve_app(
        host=host,
        port=port,
        data_dir=data_dir.resolve(),
        templates_dir=templates_dir.resolve(),
        category_config=category_config.resolve(),
    )


def main():
    run_typer_app_with_default_command(app, default_command="serve")


if __name__ == "__main__":
    main()
