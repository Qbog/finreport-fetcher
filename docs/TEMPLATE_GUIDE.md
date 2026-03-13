# 财报模板使用说明（Template Usage Guide）

本文档说明如何使用 finreport_fetcher 和 finreport_charts 的模板系统来生成个性化的财务报表图表。

---

## 1. 财报 Excel 格式（Fetcher 输出）

运行 `finreport_fetcher fetch` 后，生成的 Excel 包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| `key` | 模板使用的标准键（每行都有） | `is.revenue` / `bs.cash` |
| `科目` | 显示用科目名（中文 + 可选英文括号；无翻译不加括号） | `营业收入 (Operating revenue)` |
| `数值` | 财务数值 | `174144069958.25` |

### Key 命名规则

- `is.xxx` - 利润表 (Income Statement)
- `bs.xxx` - 资产负债表 (Balance Sheet)
- `cf.xxx` - 现金流量表 (Cash Flow)

常见 Key 示例：
```
is.revenue          # 营业收入
is.cogs             # 营业成本
is.net_profit       # 净利润
bs.cash             # 货币资金
bs.advance_receipts # 预收款项
bs.prepayments      # 预付款项
cf.net_cash_from_ops # 经营活动现金流量净额
```

完整的科目映射表见：`finreport_fetcher/mappings/subject_glossary.py`

---

## 2. 模板文件（推荐：templates/*.toml）

我们推荐 **一个模板一个 TOML 文件**，统一放在仓库根目录 `templates/` 下，并用 `finreport_charts run` 执行。

> 强烈建议在 `[[bars]]` 里优先写 `expr = "<key>"`（例如 `is.net_profit`），而不是中文科目名，以保证跨公司复用与稳定匹配。
>
> 支持跨期取数：`is.admin_expense.2024.12.31`（在 key 后追加 `.YYYY.MM.DD`）。

### 2.1 柱状图趋势（bar）

`templates/revenue_ttm.toml` 示例：

```toml
name = "revenue_ttm"
alias = "revenue_ttm"

type = "bar"           # bar|pie|combo
mode = "trend"         # trend|compare

title = "营业收入（TTM）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "营业收入"
expr = "is.revenue"     # 推荐用 key；也支持表达式：is.sell_expense + is.admin_expense
transform = "ttm"       # ttm|ytd|q|raw
```

**transform 选项说明：**
- `ttm`：滚动12个月（Trailing Twelve Months）
- `ytd` / `raw`：累计值（Year to Date；raw 视为 ytd）
- `q`：单季值（Quarter，通过差分计算）

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

title = "营业收入（TTM）vs 股价"
x_label = "报告期"
y_label = "金额"

statement = "利润表"
bar_item = "is.revenue"
transform = "ttm"
# 股价线自动读取 data-dir/price/{code6}.csv
```

> 说明：旧版 `charts.toml`（单文件多模板）解析器仍保留，但 CLI 仅支持 `finreport_charts run`；旧的 `bar/pie/combo/template` 子命令已弃用并会直接退出。

---

## 3. 命令行使用

### 3.1 基础命令

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

### 3.2 Transform 详解

```bash
# TTM（滚动12个月）- 适合利润表、现金流量表
--transform ttm

# YTD（累计值）- 报表原始累计值
--transform ytd

# 单季值 - 通过差分计算（Q2-Q1, Q3-Q2, Q4-Q3）
--transform q
```

**注意：**
- TTM 计算需要上一年数据，程序会自动补齐
- 单季计算需要当年 Q1 数据，程序会自动从当年 1/1 开始补齐
- 资产负债表通常不需要 TTM（存量科目），建议使用 `ytd` 或 `point`

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

`templates/revenue_ttm.toml`

```toml
name = "revenue_ttm"
alias = "revenue_ttm"

type = "bar"
mode = "trend"

title = "营业收入（TTM）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "营业收入"
expr = "is.revenue"
transform = "ttm"
```

`templates/profit_quarter.toml`

```toml
name = "profit_quarter"
alias = "profit_quarter"

type = "bar"
mode = "trend"

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
name = "归母净利润"
expr = "is.net_profit"
transform = "q"
```

`templates/current_assets.toml`

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


---

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

---

## 7. 常见问题

### Q1: 如何查看所有可用的 key？
打开生成的财报 Excel，查看 `key` 列。或在代码中查看 `subject_glossary.py`。

### Q2: expr/key 找不到怎么办？
- 优先使用 Excel 里的 `key` 列（每行都有 key）
- 确认 key 前缀对应报表：`is.*`=利润表，`bs.*`=资产负债表，`cf.*`=现金流量表
- 如果确实缺少映射：在 `finreport_fetcher/mappings/subject_glossary.py` 里补充 key→中文/英文映射

### Q3: TTM 计算失败？
- 确保数据包含上一年同季度和年报数据
- 程序会自动尝试补齐缺失数据

### Q4: 如何添加新的科目映射？
编辑 `finreport_fetcher/mappings/subject_glossary.py`，添加新的 `SubjectSpec`：
```python
SubjectSpec("is.your_key", "中文科目名", "English Name")
```

---

## 8. 命令速查表

| 命令 | 用途 |
|------|------|
| `finreport_fetcher fetch --code XXX --start YYYY-MM-DD --end YYYY-MM-DD` | 抓取财报 |
| `finreport_charts bar --code XXX --item XXX --transform ttm` | 柱状图趋势 |
| `finreport_charts pie --code XXX --section XXX` | 饼图占比 |
| `finreport_charts combo --code XXX --bar-item XXX` | 双轴组合图 |
| `finreport_charts run --templates templates [--template xxx]` | 使用模板（推荐：单文件模板） |

---

**提示：** 所有命令都支持 `--help` 查看详细参数说明。
