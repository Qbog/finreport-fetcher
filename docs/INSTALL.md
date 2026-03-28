# 1) 安装与环境检查

## 1.1 运行环境

- Python：建议 **3.10+**
- OS：Linux/macOS/Windows（本项目在 Linux 上开发与验证更充分）

依赖项由 `pyproject.toml` 管理。

## 1.2 安装方式

推荐在仓库根目录使用可编辑安装（开发/调试最方便）：

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
python3 -m pip install -U pip
python3 -m pip install -e .
```

安装后可使用短命令（也可 `python3 -m ...` 运行）：

- `finfetch` / `python3 -m finreport_fetcher`
- `finchart` / `python3 -m finreport_charts`
- `finprice` / `python3 -m finprice_fetcher`
- `finindex` / `python3 -m finindex_fetcher`
- `finmerge` / `python3 -m finchart_merge`
- `finweb` / `python3 -m finreport_web`

## 1.3 可选：Tushare Token

若你希望使用 tushare 拉取数据（尤其股价日频），设置环境变量：

```bash
export TUSHARE_TOKEN="xxxx"
```

不设置也可以：
- `provider=auto` 会在缺少 token 时自动回退到 akshare。

## 1.4 安装后自检

```bash
python3 -m finreport_fetcher --help
python3 -m finreport_charts --help
python3 -m finprice_fetcher --help
```

运行回归测试（推荐首次安装后先跑一次）：

```bash
scripts/regression_test.sh
```

> 若提示 `pytest: command not found`：请使用 `python3 -m pytest -q`（本项目脚本已统一用该方式调用）。
