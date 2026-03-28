# Price 折线图（mode=price）

## 目标
- 折线图不再“挤”：
  - x 轴刻度自动稀疏显示（不会每个交易日都打印）
  - 默认不画 marker 点（避免太乱）
  - 纵轴默认每家公司独立范围（更饱满）；需要统一尺度再开启 `--share-axis`
- 支持按频率拉取/补齐股价：daily/weekly/monthly 以及自定义 Nd（例如 5d/7d/10d）
- 支持把**外部时间序列**也按日频方式绘制在 line / merge 中：
  - 商品：如黄金 / 白银 / 原油
  - 指数：如上证 / 深证 / 创业板 / 北证

> 经验规则：凡是你希望在 merge 里画“完整日期折线”的模板，都应该优先做成 `type="line" + mode="price"`，而不是 `mode="trend"`。

## 模板字段（templates/*.toml）

```toml
name = "price_close_trend"
type = "line"
mode = "price"

# 可选：控制“基准股价频率”
# - daily / weekly / monthly / 5d / 7d / 10d ...
frequency = "daily"

title = "股价-收盘"
x_label = "日期"
y_label = "价格"

# 推荐写法：[[series]]（旧的 [[bars]] 仅兼容，不再推荐）
[[series]]
name = "close"
expr = "px.close"
```

商品 / 指数这类“非公司股价”的外部序列，如果也想走完整日频折线，同样建议写成：

```toml
name = "nonfin-trend-gold_price"
type = "line"
mode = "price"

title = "黄金价格走势"
x_label = "日期"
y_label = "价格"

[[series]]
name = "黄金价格"
expr = "commodity.黄金.close"
```

## expr 可用变量
- 基准频率数据：
  - `px.close`, `px.open`, `px.high`, `px.low`, `px.volume`, `px.amount` ...
- 显式引用其它频率（会自动触发补数并加载）：
  - `px_5d.close` / `px_10d.close` / `price_7d.amount` ...
  - 约定：`px_1d.*` 等价于日频。
- 也可混合财报表达式（按日期映射到“最近季末值”）：
  - `is.net_profit`, `bs.cash`, `cf.net_cash_flow_from_operating` ...
- 也可引用外部序列：
  - 财报指标：`metrics.roe`, `metrics.roa`, `metrics.ev`
  - 指数：`idx.sh000001.close`, `idx.sz399001.close`, `index.上证.close`
  - 商品：`com.gold.close`, `com.oil.close`, `commodity.黄金.close`

## CLI 关键开关
- 默认每家公司独立 y 轴（更饱满）
- `--share-axis` 主要用于**多家公司**共享同一纵轴；单家公司在一次 run 中批量输出的 structure 图，会自动统一纵轴。
- 若多家公司需要共享 y 轴范围：

```bash
python3 -m finreport_charts run \
  --template price_close_trend \
  --category test \
  --start 2025-01-02 --end 2025-01-15 \
  --share-axis
```
