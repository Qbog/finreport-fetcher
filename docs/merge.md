# 图表合并：merge（双轴 PNG）

## 目标（v1）
- 输入：时间范围 + 两个模板（bar(trend) + line(price)）
- 自动补数：缺财报/缺股价会调用对应 fetcher 补齐
- 输出：单张 PNG（双 y 轴）

## 命令

```bash
# 推荐独立程序（finmerge）
finmerge merge \
  --bar-template net_profit_q \
  --line-template price_close_trend \
  --code 600036 \
  --start 2025-01-02 --end 2025-01-15 \
  --data-dir output

# 也兼容原入口（finchart / python -m finreport_charts）
finchart merge ...
python3 -m finreport_charts merge ...
```

### 输出
默认输出到公司 charts 目录：
- `output/{公司名}_{code6}/charts/merge_{barTpl}_{lineTpl}_{code6}_{start}_{end}.png`

## 模板约束（v1）
为了避免歧义，v1 做了收敛：
- bar 模板：必须 `type="bar"` 且 `mode="trend"`，并且只允许 **1 个叶子 bar**
- line 模板：必须 `type="line"` 且 `mode="price"`，并且只允许 **1 条 series**

后续可扩展：支持多条折线、多根柱、堆叠、以及多轴。
