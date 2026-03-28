# 快速上手（Quickstart）

想系统了解：请从 [docs/README.md](README.md) 开始。

---

## 1) 安装（一次性）

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
python3 -m pip install -e .
```

可选：设置 tushare token（股价日频更稳）：

```bash
export TUSHARE_TOKEN="xxxx"
```

---

## 2) 抓取财报（先有 Excel 才能做一切）

推荐短命令：

```bash
finfetch -l warning fetch \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --provider auto \
  --statement-type merged \
  --out output \
  --no-clean
```

等价长命令：

```bash
python3 -m finreport_fetcher -l warning fetch \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --provider auto \
  --statement-type merged \
  --out output \
  --no-clean
```

导出目录：`output/比亚迪_002594/reports/`。

---

## 3) （可选）抓取股价（combo 双轴图需要）

推荐短命令：

```bash
finprice -l info fetch \
  --code 002594 \
  --start 2024-01-01 --end 2024-12-31 \
  --provider auto \
  --frequency daily \
  --out output
```

等价长命令：

```bash
python3 -m finprice_fetcher -l info fetch \
  --code 002594 \
  --start 2024-01-01 --end 2024-12-31 \
  --provider auto \
  --frequency daily \
  --out output
```

输出：

- `output/比亚迪_002594/price/002594.csv`（combo 读取）
- `output/比亚迪_002594/price/002594.xlsx`（便于人工查看）

---

## 4) 跑模板出图（PNG + Excel 图表）

推荐短命令：

```bash
finchart -l info run \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template balance_sheet_analysis
```

等价长命令：

```bash
python3 -m finreport_charts -l info run \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template balance_sheet_analysis
```

输出目录：`output/比亚迪_002594/charts/`。

> 若缺少报告期，charts 会自动调用 fetcher 补齐缺失期；源头没有数据的期会跳过。

---

## 5) 下一步

- 工作流细节：见 [WORKFLOW.md](WORKFLOW.md)
- 模板写法：见 [TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md)
- 报错排查：见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 测试与 CI：见 [TESTING.md](TESTING.md)
