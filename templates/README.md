# Chart templates (TOML)

本目录用于 `finreport_charts run` 的模板文件：**一个模板一个 `.toml` 文件**。

## 1) 模板字段要求（你提出的约束）

- 必须有：
  - `type`：图表类型（`bar`/`pie`/`combo`）
  - `title`：标题（图表上方显示）
  - `x_label`、`y_label`：坐标轴名称（bar/combo 使用）
- `type = "bar"` 时还必须有：
  - `mode`：`trend`（趋势分析）或 `compare`（比较分析）
- 每根柱都用一个配置块表示：`[[bars]]`
  - `name`：显示名称
  - `expr`：取数/计算表达式（推荐用 key，如 `is.admin_expense + is.sell_expense`）
  - `transform`：`q|ytd|ttm|raw`（trend 用）

## 2) 最小示例（bar trend）

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
expr = "is.net_profit"
transform = "q"
```

## 3) 运行方式

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

## 4) 输出位置

默认输出到：`{data_dir}/{公司名}_{code6}/charts/`。

> 其中 `{公司名}_{code6}` 的公司名会尽量按 A 股正式简称解析；解析失败则退化为 code6。
