# 财报模板使用说明（Template Usage Guide）

本文档说明如何使用 finreport_fetcher 和 finreport_charts 的模板系统来生成个性化的财务报表图表。

---

## 1. 财报 Excel 格式（Fetcher 输出）

运行 `finreport_fetcher fetch` 后，生成的 Excel **列顺序已固定**（不同数据源/不同平台导出保持一致）：

| 列名 | 说明 | 示例 |
|------|------|------|
| `科目` | 规范中文科目名（来自 `subject_glossary`；必要时保留“其中/加/减”前缀） | `应收账款` / `其中：固定资产` |
| `数值` | 财务数值 | `174144069958.25` |
| ` ` | 空白分隔列（便于肉眼阅读；不参与计算） | *(空)* |
| `key` | **稳定的模板 key（ASCII-only）**，强烈建议模板里使用 | `is.revenue_total` / `bs.cash` |
| `备注` | 科目英文名称（用于校对/补全映射） | `Operating revenue` |

### Key 命名规则

- `is.xxx` - 利润表 (Income Statement)
- `bs.xxx` - 资产负债表 (Balance Sheet)
- `cf.xxx` - 现金流量表 (Cash Flow)

常见 Key 示例：
```
is.revenue          # 营业收入
is.cogs             # 营业成本
is.net_profit       # 净利润
is.net_profit_parent # 归母净利润
bs.cash             # 货币资金
bs.advance_receipts # 预收款项
bs.prepayments      # 预付款项
cf.net_cash_from_ops # 经营活动现金流量净额
```

完整的科目映射表见：`finreport_fetcher/mappings/subject_glossary.py`

---

## 2. 模板文件（推荐：templates/*.toml）

我们推荐 **一个模板一个 TOML 文件**，统一放在仓库根目录 `templates/` 下，并用 `finreport_charts run` 执行。

本仓库自带示例模板：
- `net_profit_q.toml`：归母净利润趋势（bar trend）
- `revenue_total_trend.toml`：营业总收入趋势（bar trend）
- `bs_key_items_compare.toml`：资产负债表关键科目对比（bar compare）

图表渲染的默认风格约定：
- **暗色主题**（深色背景 + 亮色文字），便于在深色界面/投影里阅读。
- 金额类 Y 轴刻度会自动按数量级显示中文单位（`亿/万/元`）。
- 柱状图会在柱子上方显示数值标签（同样按单位缩放）。

> 强烈建议在 `[[bars]]` 里优先写 `expr = "<key>"`（例如 `is.net_profit_parent`），而不是中文科目名，以保证跨公司复用与稳定匹配。
>
> 支持跨期取数：`is.admin_expense.2024.12.31`（在 key 后追加 `.YYYY.MM.DD`）。

### 2.1 柱状图趋势（bar）与折线图（line）

bar 与 line 共用相同的 `[[bars]]` 配置，仅输出图表样式不同（柱状图 vs 折线图）。

示例：单季归母净利润（由累计值差分得到）

```toml
name = "net_profit_q"
alias = "net_profit_q"

type = "bar"
mode = "trend"

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "归母净利润"
expr = "is.net_profit_parent - is.net_profit_parent.prev_in_year"
```

> 说明：不再使用 `transform=ttm/ytd/q/raw` 这类配置；现在 **只按 expr 取值**。

表达式里的标识符支持一些后缀，便于跨期取数：
- `is.xxx.2024.12.31`：指定报告期末（YYYY.MM.DD）
- `is.xxx.prev`：上一季度（可链式：`.prev.prev`）
- `is.xxx.prev_in_year`：同年上一季度（Q1 视为 0.0）

### 2.2 饼图占比（pie）

`templates/current_assets.toml` 示例（按分组标题取子项）：

```toml
name = "current_assets"
alias = "current_assets"

type = "pie"

title = "流动资产构成"
x_label = "项目"   # pie 里目前不使用，但字段要求必须存在
y_label = "金额"   # 同上

statement = "资产负债表"
section = "流动资产"
top_n = 10
```

或使用自定义科目列表：

```toml
name = "custom"
alias = "custom"

type = "pie"

title = "自定义科目占比"
x_label = "项目"
y_label = "金额"

statement = "资产负债表"
items = ["货币资金", "应收账款", "存货"]
```

### 2.3 双轴组合图（combo）

`templates/revenue_price.toml` 示例：

```toml
name = "revenue_price"
alias = "revenue_price"

type = "combo"

title = "营业收入 vs 股价"
x_label = "报告期"
y_label = "金额"

statement = "利润表"
# bar_item 支持 key/中文科目名/表达式
bar_item = "is.revenue - is.revenue.prev_in_year"   # 单季营业收入
# 股价线自动读取 data-dir/price/{code6}.csv
```

> 说明：旧版 `charts.toml`（单文件多模板）解析器仍保留，但 CLI 仅支持 `finreport_charts run`；旧的 `bar/pie/combo/template` 子命令已弃用并会直接退出。

### 2.4 折线图（line）

折线图与 bar 共用 `[[bars]]` 配置（`trend`/`compare` 均可用），但输出为折线图样式。

示例：单季营业收入（折线）

```toml
name = "revenue_q_line"
alias = "revenue_q_line"

type = "line"
mode = "trend"

title = "营业收入（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "营业收入"
expr = "is.revenue - is.revenue.prev_in_year"
```

---

## 3. 命令行使用

### 3.1 基础命令

> 若已通过 `pip install -e .` 安装为命令，可把 `python3 -m finreport_charts` 换成 `finchart`。
>
> 缺失财报处理（默认行为）：
> - 如果 `--end` 对应的最新报告期尚未披露/数据源缺失，会**自动跳过缺失期**，并把输出截至到最近可用报告期。
> - 如需“只要缺失就报错退出”，请加 `--strict`。

```bash
# 运行模板目录下全部模板
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates

# 使用 "*" 通配符（等价于全部模板）
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"

# 仅过滤输出的报告期：例如只画 Q4 和 Q2（不影响自动补数）
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*" \
  --period q4,q2
```

### 3.2 表达式跨期取数 / 差分

`finreport_charts run` 不再提供 `--transform`，也不再在模板里使用 `transform` 字段。

如果你需要“单季/差分/跨期”口径，请直接在 `expr` 里写：

- 单季（适用于利润表/现金流量表的累计口径）：
  - `is.net_profit_parent - is.net_profit_parent.prev_in_year`
  - `is.revenue - is.revenue.prev_in_year`
- 取上一季度值：`bs.cash.prev`
- 取指定期末：`bs.cash.2024.12.31`

> `--period` 仍然存在：它只过滤绘图输出的报告期，不影响自动补数/取数。

### 3.3 使用模板（推荐：run）

运行模板目录下全部模板：

```bash
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates
```

只运行单个模板（可重复多次）：

```bash
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template net_profit_q
```

> 说明：本项目已切换为模板驱动 `run`；旧的 `bar/pie/combo/template` 子命令已弃用并会直接退出。

---

## 4. 高级用法

### 4.1（建议）使用 key 避免模糊匹配

`finreport_charts` 已切换为模板驱动，建议在模板里使用 `expr = "is.xxx"` 这样的 **key**，避免中文同义词/别名导致的模糊匹配不稳定。

### 4.2 下载 PDF 原文

```bash
python3 -m finreport_fetcher fetch \
  --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --pdf
```

PDF 保存在 `output/{公司名}_{code6}/pdf/{code6}_{date}.pdf`

### 4.3 股价数据

股价 CSV 格式要求（列名：date, close）：
```csv
date,close
2024-01-02,150.50
2024-01-03,152.30
...
```

保存位置：`data-dir/price/{code6}.csv`

---

## 5. 完整示例配置

推荐把每个模板拆成单独文件，放到 `templates/` 目录。例如：

`templates/revenue_q.toml`（单季营业收入）

```toml
name = "revenue_q"
alias = "revenue_q"

type = "bar"
mode = "trend"

title = "营业收入（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "营业收入"
expr = "is.revenue - is.revenue.prev_in_year"
```

`templates/net_profit_q.toml`（单季归母净利润）

```toml
name = "net_profit_q"
alias = "net_profit_q"

type = "bar"
mode = "trend"

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "归母净利润"
expr = "is.net_profit_parent - is.net_profit_parent.prev_in_year"
```

`templates/current_assets.toml`（流动资产构成：pie）

```toml
name = "current_assets"
alias = "current_assets"

type = "pie"

title = "流动资产构成"
x_label = "项目"
y_label = "金额"

statement = "资产负债表"
section = "流动资产"
top_n = 10
```

> 说明：旧版 `charts.toml` 写法的解析器仍保留，但 CLI 仅支持 `run`；建议统一迁移到单文件模板（templates/*.toml）。


## 6. 输出文件说明

每个图表生成两个文件：

1. **PNG 图片** - 可视化图表
2. **Excel 文件** - 包含：
   - `data` sheet：原始数据
   - `chart` sheet：Excel 内置图表

文件名格式：
```
{alias}_{code6}_{start}_{end}.png
{alias}_{code6}_{start}_{end}.xlsx
```

默认输出目录（`finreport_charts run`）：
```
{data_dir}/{公司名}_{code6}/charts/
```

### 数据目录结构

finreport_fetcher 输出的财报数据与图表结果都放在同一个公司目录下：

```
output/
  {公司名}_{code6}/
    reports/
      {code6}_{statement}_{period}.xlsx
    pdf/
      {code6}_{period}.pdf
    charts/             # charts 输出目录
      *.png
      *.xlsx
```

---

## 7. 常见问题

### Q1: 如何查看所有可用的 key？
打开生成的财报 Excel，查看 `key` 列。

说明：
- `key` **保证为 ASCII**（只包含英文/数字/点号/下划线），便于模板引用。
- 已映射科目会使用 `subject_glossary.py` 里定义的稳定 key（例如 `is.revenue`）。
- 未映射科目会生成形如 `is.unk.<hash>` / `bs.unk.<hash>` 的 key（同一科目在不同数据源只要名称一致就会一致）。

### Q2: expr/key 找不到怎么办？
- 优先使用 Excel 里的 `key` 列（每行都有 key）
- 确认 key 前缀对应报表：`is.*`=利润表，`bs.*`=资产负债表，`cf.*`=现金流量表
- 如果你看到的是 `*.unk.<hash>`：说明该科目还没有被“标准化映射”，建议补齐映射
- 补映射方式：在 `finreport_fetcher/mappings/subject_glossary.py` 里添加 `SubjectSpec(key, cn, en, aliases=...)`

### Q3: 如何画“单季”而不是累计？
利润表/现金流量表很多口径是累计值（YTD）。推荐在 expr 里用差分：
- `is.net_profit_parent - is.net_profit_parent.prev_in_year`
- `is.revenue - is.revenue.prev_in_year`

### Q4: 如何添加新的科目映射？
编辑 `finreport_fetcher/mappings/subject_glossary.py`，添加新的 `SubjectSpec`：
```python
SubjectSpec("is.your_key", "中文科目名", "English Name")
```

## 8. 命令速查表

| 命令 | 用途 |
|------|------|
| `finreport_fetcher fetch --code XXX --start YYYY-MM-DD --end YYYY-MM-DD [--pdf]` | 抓取财报（可选下载 PDF） |
| `finreport_charts run --templates templates [--template xxx] --code XXX --start ... --end ...` | 使用模板生成图表（推荐方式） |

> 说明：`finreport_charts bar/pie/combo/template` 子命令已弃用，会提示并以退出码 2 退出。

**提示：** 所有命令都支持 `--help` 查看详细参数说明。
