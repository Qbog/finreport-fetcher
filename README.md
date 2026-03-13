# A股财报工具集：finreport_fetcher + finreport_charts

本仓库包含两个相互配合的程序（不同目录）：

1) **finreport_fetcher**：抓取 A 股公司三大报表并导出 Excel，可选下载对应报告期 PDF 原文。
2) **finreport_charts**：基于 fetcher 产出的数据，按选项/模板生成漂亮图表（**PNG + Excel(含原始数据+Excel内置图表)**）。

---

## 目录结构

- `finreport_fetcher/`：财报抓取程序（已实现）
- `finreport_charts/`：图表生成程序（新增）

---

## 安装

建议虚拟环境（推荐安装为可执行命令，这样你在任何目录都能运行）：

```bash
cd a_share_finreport_fetcher
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip

# 安装为 editable（会提供 finfetch 命令；也支持 python -m finreport_fetcher）
pip install -e .

# 如需 tushare（可选）：
pip install tushare
```

> 如果你不想安装，也可以在项目根目录用：
> `PYTHONPATH=. python3 -m finreport_fetcher fetch ...`
>
> 已兼容一种常见误用：如果你 `cd output` 后运行 `python3 -m finreport_fetcher ...`，
> 仓库内提供了 `output/finreport_fetcher.py` shim，会自动切回项目根目录执行。
> （但更推荐在项目根目录运行，或用 `pip install -e .` 安装后用 `finfetch` 命令运行。）

> 如使用 tushare，需要设置环境变量 `TUSHARE_TOKEN`，或在运行时传入 `--tushare-token`。

---

## 1) finreport_fetcher（财报抓取）

### 功能概览

- 支持输入：
  - 代码：`600519` / `600519.SH` / `sh600519` / `000001.SZ` 等
  - 名称模糊匹配：如 `茅台`（重名会列出候选供选择）
- 日期逻辑：
  - `--date`：取该日期**之前最近一期已披露**（通过"能否抓到数据"做可用性判断）的报告期末日
  - `--start --end`：取范围内所有报告期末日（03-31/06-30/09-30/12-31）逐个导出
- 多数据源：
  - `--provider auto`：按优先级自动兜底（默认：tushare -> akshare）
  - 或手动指定 `--provider tushare|akshare`
- 报表口径：默认合并；可切换 `--statement-type merged|parent`
- Excel 美化：标题行、冻结窗格、表头样式、交替底色、负数红色、千分位格式、自适应列宽
  - 不输出"报告期末日"列（改为每个 sheet 顶部标题展示）
  - 不输出 PDF 链接/本地路径列（改为标题下方注释行展示）
  - **新增**：每行包含 `key` 列（模板标准键，如 `is.revenue`）
  - **新增**：`科目` 列显示中英文对照（如 `营业收入 (Operating revenue)`）
  - **新增**：`科目_CN` 和 `科目_EN` 列分别存储中文和英文
- PDF：`--pdf` 下载，保存为 `output/pdf/{code6}_{report_period}.pdf`

### 清理策略

- 默认：每次执行会先清空 `--out` 输出目录，再生成新结果（避免旧数据混淆）。
- 若需要增量写入（例如给图表程序补数据用）：加 `--no-clean`。

### 使用示例

```bash
# 单个日期：取最近一期报告期
python3 -m finreport_fetcher fetch --name 茅台 --date 2025-02-01 --pdf

# 日期范围：导出范围内所有报告期
python3 -m finreport_fetcher fetch --code 600519 --start 2023-01-01 --end 2025-12-31 --pdf

# 增量写入（不清空 output）
python3 -m finreport_fetcher fetch --code 600519 --start 2024-01-01 --end 2024-12-31 --pdf --out output --no-clean
```

### 输出目录结构

默认输出到 `./output`：

```
output/
  600519_merged_20241231.xlsx
  600519_merged_20240930.xlsx
  pdf/
    600519_20241231.pdf
    600519_20240930.pdf
```

---

## 2) finreport_charts（图表生成）

### 核心需求对照

- 每张图输出 2 个文件：
  - `*.png`：图片
  - `*.xlsx`：原始数据 + Excel 内置图表
- 支持 `--start/--end` 时间范围
- 若 `--data-dir` 缺少所需报告期财报，程序会自动调用 `finreport_fetcher` 补齐（增量写入，不清空目录）
- 支持：
  - 财务科目趋势柱状图（支持 **TTM / YTD / 单季** 三种口径切换）
  - 同型分析饼图（范围内每期一张，支持 `section` 或 `items`，支持 TopN+其他）
  - 合并双轴图（财务柱 + 股价折线，股价来自 CSV：列 `date,close`）
- 可选模板化：TOML 配置 + `template --type xxx`
- **新增**：支持使用 `key`（如 `is.revenue`）替代中文科目名，实现跨公司标准化引用

### 约定：数据目录（--data-dir）

`--data-dir` 需要指向 **finreport_fetcher** 的输出目录（同一个目录里放 xlsx/pdf）。

股价 CSV（未来由你的股价 fetcher 产生）默认约定位置：

```
{data-dir}/price/{code6}.csv
```

列名要求：`date, close`。

### 使用示例

```bash
# 1) 财务科目趋势柱状图（支持三种口径）
python3 -m finreport_charts bar --code 600519 --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 --item 营业总收入 --transform ttm \
  --data-dir output --out charts_output

# 1a) 单季值（Q）- 通过差分计算
python3 -m finreport_charts bar --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --statement 利润表 --item is.net_profit --transform q \
  --data-dir output --out charts_output

# 1b) 使用 key 替代中文科目名
python3 -m finreport_charts bar --code 600519 --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 --item is.revenue_total --transform ttm \
  --data-dir output --out charts_output

# 2) 饼图：按分组标题（范围内每期一张）
python3 -m finreport_charts pie --name 茅台 --start 2024-01-01 --end 2024-12-31 \
  --statement 资产负债表 --section 流动资产 --top-n 10 \
  --data-dir output --out charts_output

# 3) 合并双轴图：财务(柱) + 股价(线)
python3 -m finreport_charts combo --code 600519 --start 2023-01-01 --end 2025-12-31 \
  --statement 利润表 --bar-item 营业总收入 --bar-transform ttm \
  --data-dir output --out charts_output \
  --price-csv output/price/600519.csv
```

### 模板化（TOML）

- 示例配置见：`charts.toml.example`
- 文件命名：优先用模板的 `alias`，没有则用模板名。

运行模板：

```bash
python3 -m finreport_charts template --type yingyee --name 茅台 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output --out charts_output \
  --config charts.toml
```

---

## 新增功能说明（v0.2）

### 1. 财报 Excel 新增列
- `key`：模板标准键（如 `is.revenue`, `bs.cash`）
- `科目`：中英文对照显示（`中文 (English)`）
- `科目_CN`：纯中文科目名
- `科目_EN`：英文翻译

### 2. Transform 口径切换
柱状图和组合图支持三种数据口径：
- `ttm` - 滚动12个月（默认）
- `ytd` / `raw` - 累计值
- `q` - 单季值（通过差分计算：Q2-Q1, Q3-Q2, Q4-Q3）

### 3. Key 引用
支持使用标准 key（如 `is.revenue`）替代中文科目名，实现：
- 跨公司标准化引用
- 避免中文科目名差异问题
- 便于模板复用

详见 [docs/TEMPLATE_GUIDE.md](docs/TEMPLATE_GUIDE.md)

---

## 免责声明

本工具依赖公开数据源与第三方库；不同数据源字段口径可能存在差异。
程序会尽量统一与标注数据来源，但请以公司正式披露为准。
