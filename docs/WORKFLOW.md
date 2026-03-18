# 3) fetch/run/模板工作流

本项目推荐工作流：

1. 用 `finreport_fetcher` 抓取财报 Excel（作为“单一事实来源”）
2. （可选）用 `finprice` 抓取股价（给 combo 图用）
3. 用 `finreport_charts run` 基于模板批量产出 PNG + Excel 图表

---

## 3.1 抓取财报（finreport_fetcher）

抓取单个报告期：

```bash
python3 -m finreport_fetcher -l warning fetch \
  --code 002594 --date 2024-12-31 \
  --provider auto \
  --statement-type merged \
  --out output \
  --no-clean
```

抓取一个区间（按季度末逐期拉取）：

```bash
python3 -m finreport_fetcher -l warning fetch \
  --code 002594 --start 2020-01-01 --end 2025-12-31 \
  --provider auto \
  --statement-type merged \
  --out output \
  --no-clean
```

按分类批量抓取：

```bash
python3 -m finreport_fetcher -l warning fetch \
  --category net_security \
  --start 2020-01-01 --end 2025-12-31 \
  --out output \
  --no-clean
```

> 分类配置见 `config/company_categories.toml`，可用 `--category-config` 指定自定义路径。

> `--no-clean` 建议默认开启：避免重复抓取时清空历史数据。

---

## 3.2 抓取股价（finprice_fetcher）

```bash
python3 -m finprice_fetcher -l info fetch \
  --code 002594 \
  --start 2024-01-01 --end 2024-12-31 \
  --provider auto \
  --frequency daily \
  --out output
```

输出到：

- `output/比亚迪_002594/price/002594.csv`
- `output/比亚迪_002594/price/002594.xlsx`

---

## 3.3 运行模板出图（finreport_charts run）

推荐：运行单个模板：

```bash
python3 -m finreport_charts -l info run \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template balance_sheet_analysis
```

运行所有模板：

```bash
python3 -m finreport_charts -l info run \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"
```

按分类批量生成图表：

```bash
python3 -m finreport_charts -l info run \
  --category net_security \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"
```

> 分类模式会根据分类内所有公司统一图表的纵轴范围与图幅尺寸，并尽量补齐缺失期为空值以保持横轴点数一致，便于横向对比。

### 缺失报告期的自动补数

当 `data-dir` 下缺少某些期的财报 Excel 时，`finreport_charts` 会自动调用 `finreport_fetcher` **仅补齐缺失期**。

- 如果某些期源头确实没有数据，会提示“补数失败”并跳过该期，继续输出其它可用期。
- 若你需要严格模式（缺一期就失败），可加 `--strict`。

---

## 3.4 trend / structure / peer 语义

- `mode=trend`：给定 `--start/--end` 输出 **1 张**跨期趋势图（横轴=时间）
- `mode=structure`（旧 compare）：给定 `--start/--end` 输出 **每个报告期 1 张**结构分析图（横轴=科目）
  - 若要“单期末 structure”，需要：`--as-of` 或模板内 `period_end`
- `mode=peer`：输出 **1 张**同业分析图（横轴=公司），同业公司列表可来自：
  - 模板内 `peers = [...]`
  - 或命令行 `--peer ...`（可重复；支持代码或简称）

详细模板写法见：[TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md)
