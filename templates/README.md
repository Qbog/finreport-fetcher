# Chart templates (TOML)

本目录用于 `finreport_charts run` 的模板文件：**一个模板一个 `.toml` 文件**。

## 1) 模板字段要求（当前规则）

- 必须有：
  - `type`：图表类型（`bar`/`line`/`pie`/`combo`）
  - `title`：标题（图表上方显示）
  - `x_label`、`y_label`：坐标轴名称（bar/line/combo 使用）
- `type = "bar"` / `type = "line"` 时还必须有：
  - `mode`：`trend`（趋势分析）、`structure`（结构分析，旧 compare）、或 `peer`（同业分析）
  - 当 `mode = "peer"`：需要指定同业公司列表：
    - 模板内：`peers = ["600519", "601318", ...]`
    - 或命令行：`--peer 600519 --peer 601318 ...`（可重复；支持代码或简称）
  - peer 模式横轴默认显示公司简称（若无法解析简称，则回退显示 6 位代码）
- 每根柱都用一个配置块表示：`[[bars]]`
  - `name`：显示名称
  - `expr`：取数/计算表达式（推荐用 key，如 `is.admin_expense + is.sell_expense`）

> 说明：不再使用 `transform=ttm/ytd/q/raw` 这类配置；现在 **只按 expr 取值**。

## 2) 表达式取值增强（推荐）

表达式里的标识符支持一些后缀，便于在 **expr 内** 做“差分/跨期取数”：

- `is.xxx.2024.12.31`：指定报告期末（YYYY.MM.DD）
- `is.xxx.prev`：上一季度（可链式：`.prev.prev`）
- `is.xxx.prev_in_year`：同年上一季度（Q1 视为 0.0）

## 3) 内置示例模板（本目录已有）

- `net_profit_q.toml`：归母净利润趋势（bar trend）
- `revenue_total_trend.toml`：营业总收入趋势（bar trend）
- `bs_key_items_structure.toml`：资产负债表关键科目结构分析（bar structure）
- `balance_sheet_analysis.toml`：资产负债表分析（bar structure，含嵌套分组 + 颜色示例）
- `net_profit_peer.toml`：净利润同业分析示例（bar peer）

## 4) 最小示例（bar trend：单季 = 当期累计 - 同年上期累计）

```toml
name = "net_profit_q"
alias = "net_profit_q"

type = "bar"
mode = "trend" # Modes include "structure" (旧 compare) and "peer" (同业分析)

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"

[[bars]]
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

## 6) 输出位置

默认输出到：`{data_dir}/{公司名}_{code6}/charts/`。

> 其中 `{公司名}_{code6}` 的公司名会尽量按 A 股正式简称解析；解析失败则退化为 code6。
