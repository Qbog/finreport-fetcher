# Web 报表分析台

`finreport_web` 现在是一个按“类别批量分析”驱动的本地 Web 服务。

核心变化：

- 开始分析前只保留 3 个配置：
  - 公司类别
  - 时间范围
  - 分析内容
- 不再依赖“先手动选择一个公司”
- Web 端会直接读取 `output/` 下的财报 Excel / 股价 CSV 原始数据生成图表
- 支持 4 类内容：
  - 趋势分析
  - 结构分析
  - 同业分析
  - 合并报表（财务数据 + 股价）
- 支持：
  - 创建公司类别
  - 模板创建
  - 直接保存 `config/company_categories.toml`

---

## 1. 启动前准备

建议先准备全局公司总表：

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
fincompany fetch --out output
```

如果要在 Web 中看到全量财报指标汇总，也可以补抓：

```bash
finmetrics fetch --out output
```

同时，Web 分析仍然依赖 `output/{公司名}_{code6}/reports/*.xlsx` 和 `output/{公司名}_{code6}/price/{code6}.csv`。
这些底层数据仍由现有抓取程序维护：

```bash
finfetch fetch --category test --start 2024-01-01 --end 2024-12-31 --out output --no-clean
finprice fetch --category test --start 2024-01-01 --end 2024-12-31 --out output
```

---

## 2. 启动服务

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
python3 -m finreport_web serve \
  --host 0.0.0.0 \
  --port 8787 \
  --data-dir output \
  --templates templates \
  --category-config config/company_categories.toml
```

如果已 `pip install -e .`：

```bash
finweb serve --host 0.0.0.0 --port 8787 --data-dir output --templates templates
```

打开：

```text
http://127.0.0.1:8787
```

---

## 3. 页面说明

### 左侧：分析设置

只有三组主配置：

1. **公司类别**
2. **时间范围**
3. **分析内容**（来自 `templates/*.toml`）

辅助功能：

- **创建公司类别**：从全局公司总表里挑选公司，写回 `config/company_categories.toml`
- **模板创建**：快速生成一个 `templates/{name}.toml`
- **保存 TOML**：直接保存分类配置文本

### 右侧：报表浏览区

自动按四类内容分区展示：

- 趋势分析
- 结构分析
- 同业分析
- 合并报表

每张图都保留：

- PNG 图
- 对应 Excel 数据表

---

## 4. 导航规则

### 趋势分析

- `← / →`：切换同一家公司、不同分析内容的趋势
- `↑ / ↓`：切换不同公司（对比相同内容）

### 结构分析

- `← / →`：切换不同时间的结构图
- `↑ / ↓`：切换不同公司

### 同业分析

- `← / →`：切换不同时间
- `↑ / ↓`：切换不同分析内容

### 合并报表

当前 MVP 采用与趋势分析一致的导航：

- `← / →`：切换不同合并内容
- `↑ / ↓`：切换不同公司

> 当输入框或文本框聚焦时，方向键不会抢焦点。

---

## 5. 模板类别

模板创建按钮支持以下类别：

- `trend`
- `structure`
- `peer`
- `merge`

其中：

- `trend/structure/peer` 生成 `type = "bar"`
- `merge` 生成 `type = "combo"`

MVP 里模板创建采用“最少输入”模式：

- 输入名称
- 输入表达式（或 bar_item + line）
- 自动生成模板文件

复杂模板仍建议直接编辑 `templates/*.toml`。

---

## 6. 输出目录

每次 Web 发起分析，都会单独输出到全局目录：

```text
output/_global/web_runs/{时间戳}/
```

优点：

- 不和单家公司目录混在一起
- 可保留多次分析快照
- 同一次分析的趋势 / 结构 / 同业 / 合并结果在一起

---

## 7. 说明与边界

- 当前实现优先做端到端可跑 MVP，继续复用现有 `templates/*.toml` 作为“分析内容”配置源
- Web 不再调用旧的 `finreport_charts run`，而是自己读取底层数据生成图表
- 财报指标全局 CSV 目前主要用于启动信息展示和后续扩展；MVP 图表仍主要基于现有财报 Excel / 股价 CSV
- 如果某家公司缺少底层财报/股价数据，对应图会在错误区显示缺失原因
