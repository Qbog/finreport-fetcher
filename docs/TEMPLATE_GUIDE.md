# 财报模板使用说明（Template Usage Guide）

本文档说明如何使用 finreport_fetcher 和 finreport_charts 的模板系统来生成个性化的财务报表图表。

---

## 1. 财报 Excel 格式（Fetcher 输出）

运行 `finreport_fetcher fetch` 后，生成的 Excel 包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| `key` | 模板使用的标准键 | `is.revenue` / `bs.cash` |
| `科目` | 显示用科目名（中文+英文） | `营业收入 (Operating revenue)` |
| `数值` | 财务数值 | `174144069958.25` |
| `科目_CN` | 原始中文科目名 | `营业收入` |
| `科目_EN` | 英文翻译 | `Operating revenue` |

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

## 2. 模板配置文件（charts.toml）

模板使用 TOML 格式，支持三种图表类型：

### 2.1 柱状图趋势（bar）

```toml
[templates.yingyee]
alias = "yingyee"        # 输出文件名前缀
chart = "bar"            # 图表类型
statement = "利润表"      # 报表类型
item = "营业总收入"       # 科目（可用中文或 key，如 is.revenue_total）
transform = "ttm"        # 转换方式: ttm / ytd / q
```

**transform 选项说明：**
- `ttm` - 滚动12个月（Trailing Twelve Months）
- `ytd` / `raw` - 累计值（Year to Date）
- `q` - 单季值（Quarter，通过差分计算）

### 2.2 饼图占比（pie）

```toml
[templates.liudong_zichan]
alias = "liudong_zichan"
chart = "pie"
statement = "资产负债表"
section = "流动资产"      # 按分组标题取子项
top_n = 10               # 显示前N项，其余合并为"其他"
```

或使用自定义科目列表：
```toml
[templates.zidingyi]
alias = "custom"
chart = "pie"
statement = "资产负债表"
items = ["货币资金", "应收账款", "存货"]  # 自定义科目列表
```

### 2.3 双轴组合图（combo）

```toml
[templates.yingyee_vs_price]
alias = "yingyee_vs_price"
chart = "combo"
statement = "利润表"
bar_item = "营业总收入"    # 柱状图科目
transform = "ttm"          # 转换方式: ttm / ytd / q
# 股价线自动读取 data-dir/price/{code6}.csv
```

---

## 3. 命令行使用

### 3.1 基础命令

```bash
# 柱状图（单科目趋势）
python3 -m finreport_charts bar \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 \
  --item 营业总收入 \
  --transform ttm \
  --data-dir output \
  --out charts_output

# 使用 key 替代中文科目名
python3 -m finreport_charts bar \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 \
  --item is.net_profit \
  --transform q \
  --data-dir output \
  --out charts_output
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

### 3.3 使用模板配置文件

```bash
python3 -m finreport_charts template \
  --type yingyee \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --config charts.toml \
  --data-dir output \
  --out charts_output
```

---

## 4. 高级用法

### 4.1 模糊匹配科目

```bash
python3 -m finreport_charts bar \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 \
  --item-like "营收" \
  --transform ttm
```

### 4.2 下载 PDF 原文

```bash
python3 -m finreport_fetcher fetch \
  --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --pdf
```

PDF 保存在 `output/pdf/{code6}_{date}.pdf`

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

```toml
# charts.toml 完整示例

# 1. 营业收入 TTM 趋势
[templates.revenue_ttm]
alias = "revenue_ttm"
chart = "bar"
statement = "利润表"
item = "is.revenue_total"  # 使用 key
transform = "ttm"

# 2. 净利润单季趋势
[templates.profit_quarter]
alias = "profit_quarter"
chart = "bar"
statement = "利润表"
item = "is.net_profit"
transform = "q"

# 3. 流动资产构成饼图
[templates.current_assets]
alias = "current_assets"
chart = "pie"
statement = "资产负债表"
section = "流动资产"
top_n = 10

# 4. 营收 vs 股价双轴图
[templates.revenue_price]
alias = "revenue_price"
chart = "combo"
statement = "利润表"
bar_item = "is.revenue_total"
transform = "ttm"

# 5. 预收+预付（使用表达式风格的 key）
[templates.advances]
alias = "advances"
chart = "bar"
statement = "资产负债表"
item = "bs.advance_receipts"  # 预收款项
transform = "ytd"
```

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

---

## 7. 常见问题

### Q1: 如何查看所有可用的 key？
打开生成的财报 Excel，查看 `key` 列。或在代码中查看 `subject_glossary.py`。

### Q2: 科目找不到怎么办？
- 检查报表类型是否正确（利润表/资产负债表/现金流量表）
- 尝试使用模糊匹配 `--item-like`
- 检查 Excel 中的实际科目名

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
| `finreport_charts template --type XXX` | 使用模板 |

---

**提示：** 所有命令都支持 `--help` 查看详细参数说明。
