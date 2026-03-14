# 快速开始（Quickstart）

这份文档给你一条**最短路径**：从“抓财报”到“用模板出图”。

> 你只需要关心两个命令：
> - 抓财报：`finfetch fetch ...`（或 `python3 -m finreport_fetcher fetch ...`）
> - 画图：`finchart run ...`（或 `python3 -m finreport_charts run ...`）

---

## 0) 环境准备

建议使用虚拟环境，并升级 pip/setuptools（否则旧环境可能无法 `pip install -e .`）：

```bash
cd a_share_finreport_fetcher
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
```

安装依赖（开发时推荐 editable）：

```bash
pip install -e .
```

> 如果你不想安装，也可以在仓库根目录直接运行：
> - `PYTHONPATH=. python3 -m finreport_fetcher ...`
> - `PYTHONPATH=. python3 -m finreport_charts ...`

---

## 1) 抓取某家公司财报（导出 Excel，可选 PDF）

示例：抓取贵州茅台 2024 年四个季度（合并报表）：

```bash
finfetch fetch --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --statement-type merged \
  --out output
```

如需同时下载对应期末的 PDF 原文：

```bash
finfetch fetch --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --pdf \
  --out output
```

输出目录结构（按公司归档）：

```
output/
  贵州茅台_600519/
    reports/
      600519_merged_20240331.xlsx
      ...
    pdf/
      600519_20240331.pdf
      ...
```

---

## 2) 用模板生成图表（PNG + Excel）

示例：跑单个模板 `net_profit_q`：

```bash
finchart run --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --data-dir output \
  --templates templates \
  --template net_profit_q
```

一次跑完整个模板目录：

```bash
finchart run --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"
```

> 若 `output/` 里缺少某些报告期，`finreport_charts` 会自动调用 `finreport_fetcher` 增量补齐（不会清空历史数据）。

图表输出位置：

```
output/贵州茅台_600519/charts/
  net_profit_q_600519_20240101_20241231.png
  net_profit_q_600519_20240101_20241231.xlsx
```

---

## 3) 下一步：写你自己的模板

- 模板目录：`templates/`
- 模板说明：见 [TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md)

推荐优先使用 Excel 里的 `key`（例如 `is.revenue`），模板更稳定、跨公司复用更好。
