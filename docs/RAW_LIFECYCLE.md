# Raw 数据生命周期（重要）

这份文档只讲一件事：**所有抓取程序的 raw 应该怎么存、什么时候全量、什么时候增量、什么时候清理。**

如果以后又要改 raw 路径、更新逻辑、Web 面板，先看这里，别再踩同一类坑。

---

## 1. 总原则

### 1.1 第一次抓取：拿完整历史

第一次某个标的 / 某个 provider 没有 raw 缓存时：

- **report**：抓该公司的完整历史财报 raw
- **price**：抓该公司的完整历史日线 raw
- **metrics**：抓该公司的完整历史指标 raw
- **commodity / index**：抓该标的完整历史 raw

也就是说：**raw 是“原始历史仓库”，不是单次查询的临时切片。**

### 1.2 再次更新：优先增量合并

有 raw 以后：

- 正常 `fetch` 时，如果发现请求日期超出当前 raw 覆盖范围，应该**优先做增量补齐**。
- 显式 `--update-raw` 时，也应该**优先做增量更新**，然后和旧 raw 合并。
- 只有 provider 本身不支持按日期/报告期增量接口时，才退回“重新拉当前全量源，再与旧 raw 合并”的兼容策略。

目标不是“每次联网都只拿 100% 增量”，而是：

1. 本地 raw 始终保存**完整历史**
2. 更新时尽量只补新日期 / 新报告期
3. 即使 provider 只能返回全量，也要在本地做**去重合并**，不要破坏 raw 生命周期

### 1.3 current / snapshots / latest.json 的职责

每个 raw provider 目录都遵循：

- `current/`：当前可用的最新合并结果
- `snapshots/{timestamp}/`：手动更新时保留的历史快照
- `latest.json`：最新一次 current/snapshot 的元信息

推荐理解：

- `current` = 工作面
- `snapshots` = 备份历史
- `latest.json` = 当前状态说明

### 1.4 clear-raw 的定义

`--clear-raw` 只做一件事：

- **删除旧 snapshots**
- **保留 current 和 latest.json**

它不是“清空 raw 重新来”。

---

## 2. 各程序的 raw 目录

## 2.1 财报（finreport_fetcher）

```text
output/{公司名}_{code6}/raw/report/{provider}/
  current/
    bs.pkl|csv
    is.pkl|csv
    cf.pkl|csv
  snapshots/{timestamp}/
    bs.pkl|csv
    is.pkl|csv
    cf.pkl|csv
  latest.json
```

说明：

- `bs/is/cf` 分别是资产负债表 / 利润表 / 现金流量表 raw
- 第一次抓取时写入完整历史
- 之后如果遇到新的报告期：
  - **tushare**：优先按 `end_date` 增量补单期并合并
  - **akshare / akshare_ths**：由于上游接口更偏全量宽表，当前采用“重新取源 + 本地 merge 去重”的兼容策略

### 财报 raw 维护开关

- `--update-raw`：更新 current，并写一份 snapshot
- `--clear-raw`：清理旧 snapshot，只保留最新 snapshot + current

---

## 2.2 股价（finprice_fetcher / A 股公司）

```text
output/{公司名}_{code6}/raw/price/{provider}/
  current/
    daily.pkl|csv
  snapshots/{timestamp}/
    daily.pkl|csv
  latest.json
```

说明：

- raw 一律保存**完整历史日线**
- 日常输出（`price/{code6}.csv/.xlsx`）只是从 raw 裁切/聚合出来的使用文件
- 第二次更新默认按 `max(date)+1 ~ today` 做**增量追加**，再去重合并

频率（weekly/monthly/5d/10d...）不另存 raw 历史仓，只基于 daily raw 生成使用输出。

---

## 2.3 财务指标（finmetrics_fetcher）

```text
output/{公司名}_{code6}/raw/metrics/{provider}/
  current/
    source.pkl|csv
    metrics.pkl|csv
  snapshots/{timestamp}/
    source.pkl|csv
    metrics.pkl|csv
  latest.json
```

说明：

- `source.*` 保存 provider 原始指标数据
- `metrics.*` 保存整理后的统一指标表
- 第一次抓取写完整历史
- 后续更新时：优先把新抓到的 period 与旧 `metrics` 按 `end_date` 合并去重
- 如果 provider 原始 `source` 不是按 period 行存储（例如宽表），允许直接用最新全量 source 覆盖 current，但 `metrics` 仍要保持完整历史 + 去重

---

## 2.4 商品（finprice_fetcher commodity）

```text
output/global/commodities/{slug}/
  price/{slug}.csv
  price/{slug}.xlsx
  raw/price/{provider}/
    current/daily.pkl|csv
    snapshots/{timestamp}/...
    latest.json
```

当前内置 slug：

- `gold`
- `silver`
- `oil`

---

## 2.5 指数（finindex_fetcher）

```text
output/global/indexes/{code}/
  index/{code}.csv
  index/{code}.xlsx
  raw/{provider}/
    current/daily.pkl|csv
    snapshots/{timestamp}/...
    latest.json
```

注意：

- **这里已经去掉了多余的 `raw/index/` 这一层**
- 正确路径是：`raw/tencent/current/...`
- 不是：`raw/index/tencent/current/...`

当前默认 provider：`tencent`

更新逻辑：

- 第一次抓取：完整历史
- 后续更新：按 `max(date)+1 ~ today` 走**增量拉取 + 本地 merge**

---

## 3. Web 端如何使用 raw

Web 现在有“raw 更新 / 清理”的实时日志面板。

前端点按钮后：

1. 后端启动对应 fetcher 子进程
2. 进程 stdout/stderr 实时写入任务日志
3. 前端轮询任务状态并显示日志
4. 任务结束后保留最近日志，便于排查

Web 面板的 raw 维护动作只负责：

- 发起 `--update-raw`
- 发起 `--clear-raw`
- 展示日志

它不改变 raw 生命周期规则。

---

## 4. 模板里怎么引用价格 / 商品 / 指数

除了公司股价 `px.close` 之外，现在还支持：

### 4.1 公司股价

- `px.close`
- `px.open`
- `px.high`
- `px.low`
- `price.amount`

### 4.2 指数

- `idx.sh000001.close`
- `idx.sz399001.close`
- `idx.sz399006.close`
- `idx.bj899050.close`

也支持 `index.` 前缀：

- `index.sh000001.close`

### 4.3 商品

- `com.gold.close`
- `com.silver.close`
- `com.oil.close`

也支持 `commodity.` 前缀：

- `commodity.gold.close`

### 4.4 在模板中的含义

这些标识在模板表达式里都表示：

- **取该序列在当前日期 / 当前报告期末及之前最近一个可用值**

所以你可以直接写：

```toml
expr = "is.revenue_total / idx.sh000001.close"
expr = "px.close / com.gold.close"
expr = "is.net_profit_parent / idx.sz399006.close"
```

---

## 5. 模板文件命名规则

模板文件名统一使用：

```text
{english}#{中文}.toml
```

例如：

- `income_trend#收入趋势.toml`
- `asset_structure#资产结构.toml`
- `price_close_trend#股价-收盘.toml`

但加载模板时仍然支持：

- 英文 `name`
- 中文 `alias`
- `names = []` 里的别名
- 只传英文名（例如 `income_trend`）
- 只传中文名（例如 `收入趋势`）

也就是说：**文件名规范统一了，但调用方式仍然保持中英文都能用。**

---

## 6. 改 raw 相关代码时的检查清单

以后如果你再改 raw，请先确认下面这些点：

1. **第一次抓取是不是完整历史？**
2. **再次更新是不是优先增量？**
3. **current / snapshots / latest.json 是否同步更新？**
4. **clear-raw 是否只清旧 snapshots？**
5. **README / docs / Web 提示语是否一起更新？**
6. **模板引用标识（px/idx/com）是否仍然可用？**
7. **路径有没有出现重复层级（比如 `raw/index/...` 这种）？**

如果这 7 个问题里有一个答不上来，就先别提交。