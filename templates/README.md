# Chart templates (TOML)

本目录用于 `finreport_charts run` 的模板文件：**一个模板一个 `.toml` 文件**。

模板文件名统一使用：`{english}#{中文}.toml`。
例如：`income_trend#收入趋势.toml`。

## 1) 模板字段要求（当前规则）

- 必须有：
  - `type`：图表类型（`bar`/`line`/`pie`/`combo`）
  - `title`：标题（图表上方显示）
  - `x_label`、`y_label`：坐标轴名称（bar/line/combo 使用）
- `type = "bar"` / `type = "line"` 时还必须有：
  - `mode`：`trend`（趋势分析）、`structure`（结构分析，旧 compare）、或 `peer`（同业分析）
  - 当 `mode = "peer"`：同业公司列表只在命令行里指定：`--peer 600519 --peer 601318 ...`（可重复；支持代码或简称）
  - peer 模式横轴默认显示公司简称（若无法解析简称，则回退显示 6 位代码）
- 每个序列都用一个配置块表示：`[[series]]`（旧的 `[[bars]]` 仅兼容，不再推荐）
  - `name`：显示名称
  - `expr`：取数/计算表达式（推荐用 key，如 `is.admin_expense + is.sell_expense`）
- 模板名支持多种写法：
  - `name`：英文主名（推荐用于脚本）
  - `alias`：中文显示名（也可直接 `--template 中文名` 使用）
  - `names`：额外别名列表（可同时放英文/中文同义名）
  - 文件名使用 `{english}#{中文}.toml`，但运行时仍可只传英文名或中文名

> 说明：不再使用 `transform=ttm/ytd/q/raw` 这类配置；现在 **只按 expr 取值**。

## 2) 表达式取值增强（推荐）

表达式里的标识符支持一些后缀，便于在 **expr 内** 做“差分/跨期取数”：

- `is.xxx.2024.12.31`：指定报告期末（YYYY.MM.DD）
- `is.xxx.prev`：上一季度（可链式：`.prev.prev`）
- `is.xxx.prev_in_year`：同年上一季度。例：Q3 → 当年 Q2；Q1 → `0.0`。主要用于把累计值差分为单季值。
- `is.xxx.prev_year`：上一年同一季度
- `is.xxx.prev_year.q1/q2/q3/q4`：上一年指定季度

## 3) 内置模板（按“财报分析”分类）

### 外部价格 / 商品 / 指数标识

除了公司股价 `px.close`，模板表达式现在还支持：

- 指数：`idx.sh000001.close` / `idx.sz399001.close` / `idx.sz399006.close` / `idx.bj899050.close`
- 商品：`com.gold.close` / `com.silver.close` / `com.oil.close`

这些标识表示“取当前日期/报告期末及之前最近一个可用值”。

### 趋势分析
- `income_trend.toml`：收入趋势（营业总收入，单季）
- `profit_trend.toml`：利润趋势（归母净利润，单季）
- `net_assets_trend.toml`：资产趋势（净资产）
- `cashflow_trend.toml`：现金流趋势（总现金流 + 经营现金流，单季）

### 结构分析
- `asset_structure.toml`：资产结构（更完整的主要资产科目）
- `liability_structure.toml`：负债结构（更完整的主要负债科目）
- `expense_structure.toml`：成本结构（三费：销售/管理/研发，单季）
- `cashflow_structure.toml`：现金流结构（经营/投资/融资，单季）
- `bs_key_items_structure.toml`：资产负债表关键科目结构分析（bar structure；同次批量输出会自动统一纵轴）
- `balance_sheet_analysis.toml`：资产负债表分析（bar structure，含嵌套分组 + 颜色示例）

### 公司对比
- `revenue_peer.toml`：收入对比
- `profit_peer.toml`：利润对比
- `roe_peer.toml`：ROE 对比（近似）
- `asset_scale_peer.toml`：资产规模对比
- `net_profit_peer.toml`：净利润同业分析示例

## 4) 最小示例（bar trend：单季 = 当期累计 - 同年上期累计）

```toml
name = "net_profit_q"
alias = "net_profit_q"

type = "bar"
mode = "trend" # Modes include "structure" (旧 compare) and "peer" (同业分析)

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

[[series]]
name = "归母净利润"
expr = "is.net_profit_parent - is.net_profit_parent.prev_in_year"
```

## 5) 运行方式

> 若已通过 `pip install -e .` 安装为命令，可把 `python3 -m finreport_charts` 换成 `finchart`。

- 运行模板目录下全部模板：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates
```

- 使用 "*" 通配符（等价于全部）：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates --template "*"
```

- 只运行指定模板（可重复多次）：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates --template net_profit_q
```

- 也可以直接用中文模板名：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates --template 收入趋势 --template 负债结构
```

## 6) 输出位置

默认输出到：`{data_dir}/{公司名}_{code6}/charts/`。

> 其中 `{公司名}_{code6}` 的公司名会尽量按 A 股正式简称解析；解析失败则退化为 code6。
