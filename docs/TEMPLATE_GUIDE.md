# 5) 模板规范与最佳实践（finreport_charts）

模板用于把“财报 Excel（单一事实来源）”转换为可复用的图表（PNG + Excel 图表）。

推荐：**一个模板一个 TOML 文件**，放在仓库根目录 `templates/`。

---

## 5.1 模板基本结构

最常用的字段：

```toml
name = "net_profit_q"
alias = "net_profit_q"

type = "bar"        # bar|line|pie|combo
mode = "trend"      # trend|compare（仅对 bar/line 有意义）

title = "归母净利润（单季）趋势"
x_label = "报告期"
y_label = "金额"

statement = "利润表"  # 默认取数报表：资产负债表/利润表/现金流量表

[[bars]]
name = "归母净利润"
expr = "is.net_profit_parent - is.net_profit_parent.prev_in_year"
```

- **强烈建议** `expr` 使用 Excel 中的 `key`（如 `is.net_profit_parent`），不要写中文科目名。
- `mode=trend` 会把区间内每个报告期算出一个点，然后画一张趋势图。

---

## 5.2 表达式语法（expr）

`expr` 支持：

- 单个 key：`bs.cash`
- 四则运算：`is.revenue_total - is.cogs`

并支持一些后缀，便于跨期取值：

- `.YYYY.MM.DD`：指定报告期末（例如 `bs.cash.2024.12.31`）
- `.prev`：上一季度（可链式：`.prev.prev`）
- `.prev_in_year`：同年上一季度（Q1 视为 0.0；适合把累计值差分为单季）

---

## 5.3 bar/line 的 trend / structure / peer

- `mode=trend`（趋势分析）：区间内输出 **1 张**趋势图（横轴=时间）
- `mode=structure`（结构分析，旧 compare）：区间内输出 **每个报告期 1 张**结构图（横轴=科目）
  - 如果你要只输出“单期末 structure”，用：
    - CLI：`--as-of 2024-12-31`
    - 或模板：`period_end = "2024-12-31"`
- `mode=peer`（同业分析）：输出 **1 张**同业对比图（横轴=公司）
  - 需要模板里配置 `peers = ["600519", "601318", ...]`
  - 期末选择同上（`--as-of` / `period_end`；不传则取 end 对应最近季末）

> `structure` / `peer` 模式必须显式配置 `[[bars]]`（不会自动枚举所有科目）。

---

## 5.4 bars 颜色与嵌套（分组）

`[[bars]]` 支持 `color`，并支持分组子项 `[[bars.children]]`：

```toml
[[bars]]
name = "资产"
color = "#7bdff2"

  [[bars.children]]
  name = "货币资金"
  expr = "bs.cash"

  [[bars.children]]
  name = "应收账款"
  expr = "bs.accounts_receivable"
```

约定：
- 分组节点（父 bars）不出柱子，只负责组织/继承
- 子项可覆盖父颜色

---

## 5.5 非通用科目（Excel 高亮）与模板建议

导出的财报 Excel 会用淡黄色标记“非通用科目”（仅部分公司/行业/准则下出现），并在 `备注` 列尽量说明口径。

模板建议：
- 对非通用科目，尽量写成“行业专用模板”或在模板说明里标注适用范围。
- 若某公司缺失该科目，表达式会失败导致该期被跳过；必要时可拆成专用模板。

---

## 5.6 内置示例模板

仓库自带示例：

- `templates/net_profit_q.toml`：归母净利润趋势（bar trend）
- `templates/revenue_total_trend.toml`：营业总收入趋势（bar trend）
- `templates/bs_key_items_structure.toml`：资产负债表关键科目结构分析（bar structure）
- `templates/balance_sheet_analysis.toml`：资产负债表分析（bar structure，按期输出）
- `templates/net_profit_peer.toml`：净利润同业分析示例（bar peer）

运行示例：

```bash
python3 -m finreport_charts run \
  --code 002594 \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template net_profit_q
```
