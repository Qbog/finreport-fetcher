# 3) fetch/run/模板工作流

本项目推荐工作流：

1. 用 `finfetch`（或 `python3 -m finreport_fetcher`）抓取财报 Excel（作为“单一事实来源”）
2. （可选）用 `finprice`（或 `python3 -m finprice_fetcher`）抓取股价（给 combo 图用）
3. 用 `finchart run`（或 `python3 -m finreport_charts run`）基于模板批量产出 PNG + Excel 图表

---

## 3.0 短命令 vs 长命令

如果你已经执行过：

```bash
python3 -m pip install -e .
```

推荐优先使用短命令：

- `finfetch` = `python3 -m finreport_fetcher`
- `finchart` = `python3 -m finreport_charts`
- `finprice` = `python3 -m finprice_fetcher`
- `finindex` = `python3 -m finindex_fetcher`
- `finmerge` = `python3 -m finchart_merge`
- `finweb` = `python3 -m finreport_web`

下面文档里的命令，你都可以在短命令和长命令之间自由切换。

## 3.1 抓取财报（finreport_fetcher）

**原始报表缓存与 PDF 复用**

- `finreport_fetcher` 会把每个数据源（akshare、akshare_ths、tushare）的原始宽表保存到 `output/{公司名}_{code6}/raw/{provider}/`（bs.pkl/is.pkl/cf.pkl）。如缓存已包含匹配的报告期/口径，就直接从本地解析，无需再次访问网络。
- PDF 也保留在 `output/{公司名}_{code6}/raw/pdf/{code6}_{period}.pdf`，成功下载后不再自动删除；程序启动时会先检查该路径，以复用历史下载。
- `RawReportStore` 还会记住 PDF 的元信息（URL/标题/备注），方便复核和诊断，`finreport_charts` 亦会共享这份缓存用于补数。

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

- `output/比亚迪_002594/raw/price/{provider}/daily.pkl`（首次无缓存时保存整家公司全历史日线 raw）
- `output/比亚迪_002594/raw/price/{provider}/daily.json`
- `output/比亚迪_002594/price/002594.csv`
- `output/比亚迪_002594/price/002594.xlsx`

> 后续再抓 daily/weekly/monthly/Nd 时，会直接从 raw 中裁切/聚合，不再重复访问远端。

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
  - 同一家公司在一次运行中批量生成的 structure 图，会自动统一纵轴范围/单位/图宽，便于直接横向比较不同日期。
  - 若要“单期末 structure”，需要：`--as-of` 或模板内 `period_end`
- `mode=peer`：输出 **1 张**同业分析图（横轴=公司），同业公司列表可来自：
  - 模板内 `peers = [...]`
  - 或命令行 `--peer ...`（可重复；支持代码或简称）

详细模板写法见：[TEMPLATE_GUIDE.md](TEMPLATE_GUIDE.md)
