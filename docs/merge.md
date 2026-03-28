# 图表合并：merge（双轴 / 多轴 PNG）

## 目标
- 输入：时间范围 + 模板引用
- 自动补数：缺财报 / 缺股价 / 缺指数 / 缺商品序列时自动尝试补齐
- 输出：PNG + xlsx（run 模式下）
- 支持：
  - 财务柱 + 1 条价格线
  - 财务柱 + 多条价格线
  - 财务柱 + 股价 + 商品价格 + 指数

## 推荐用法：`run` + `type="combo"` + `mode="merge"`

现在更推荐直接通过模板驱动：

```bash
python3 -m finreport_charts run \
  --code 600988 \
  --start 2015-01-01 \
  --end now \
  --data-dir output \
  --template nonfin-merge-revenue_vs_price_close_vs_gold
```

### 当前行为（重要）
- 只要 merge 里的折线模板是 `type="line"` 且 `mode="price"`，折线就会按**完整日频日期**绘制。
- 不再压缩成“只在报告期取点”的季度折线。
- 默认不画折线转折点 marker。
- `-e now` 会使用**实际可用的最新交易日**作为折线尾部日期，而不是停在最近财报季末。

## 示例模板

### 1) 收入趋势 + 股价收盘
- `templates/merge_templates#合并模板/nonfin-merge-revenue_vs_price_close.toml`

### 2) 收入趋势 + 股价收盘 + 黄金价格
- `templates/gold_enterprises#黄金企业/nonfin-merge-revenue_vs_price_close_vs_gold.toml`

> 注意：为了让黄金价格也走完整日频，`nonfin-trend-gold_price.toml` 现在应使用：
>
> - `type = "line"`
> - `mode = "price"`
>
> 这样它在 merge 中会被当作日频外部序列来处理，而不是季度 trend。

### 3) 收入趋势 + 股价收盘 + 黄金价格 + 上证指数
- `templates/gold_enterprises#黄金企业/nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index.toml`

```toml
name = "nonfin-merge-revenue_vs_price_close_vs_gold_vs_sh_index"
alias = "收入趋势+股价-收盘+黄金价格+上证指数"
type = "combo"
mode = "merge"

[[series]]
expr = "nonfin-trend-income"

[[series]]
expr = "nonfin-trend-price_close"

[[series]]
expr = "nonfin-trend-gold_price"

[[series]]
name = "上证指数"
expr = "idx.sh000001.close"
```

## `run` 输出
默认输出到公司 charts 目录：
- `output/{公司名}_{code6}/charts/{template}_{code6}_{actual_start}_{actual_end}.png`
- `output/{公司名}_{code6}/charts/{template}_{code6}_{actual_start}_{actual_end}.xlsx`

其中：
- `actual_start` / `actual_end` 取实际绘制出来的数据区间
- 当 `--end now` 时，`actual_end` 通常会落在最近一个可用交易日

## 兼容旧命令：`merge`

仓库仍保留旧的 `python3 -m finreport_charts merge ...` 入口，适合：
- 一个 bar(trend) 模板
- 一个 line(price) 模板
- 快速拼单图

```bash
finmerge merge \
  --bar-template net_profit_q \
  --line-template price_close_trend \
  --code 600036 \
  --start 2025-01-02 --end 2025-01-15 \
  --data-dir output
```

但如果你要：
- 多条折线
- 模板级组合复用
- 商品 / 指数 / 股价一起叠加

建议统一改用 `run`。
