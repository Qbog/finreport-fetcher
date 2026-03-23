# Price 折线图（mode=price）

## 目标
- 折线图不再“挤”：
  - x 轴刻度自动稀疏显示（不会每个交易日都打印）
  - 默认不画 marker 点（避免太乱）
  - 纵轴默认每家公司独立范围（更饱满）；需要统一尺度再开启 `--share-axis`
- 支持按频率拉取/补齐股价：daily/weekly/monthly 以及自定义 Nd（例如 5d/7d/10d）

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

# 推荐写法：[[series]]（[[bars]] 也兼容）
[[series]]
name = "close"
expr = "px.close"
```

## expr 可用变量
- 基准频率数据：
  - `px.close`, `px.open`, `px.high`, `px.low`, `px.volume`, `px.amount` ...
- 显式引用其它频率（会自动触发补数并加载）：
  - `px_5d.close` / `px_10d.close` / `price_7d.amount` ...
  - 约定：`px_1d.*` 等价于日频。
- 也可混合财报表达式（按日期映射到“最近季末值”）：
  - `is.net_profit`, `bs.cash`, `cf.net_cash_flow_from_operating` ...

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
