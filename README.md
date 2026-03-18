# A股财报工具集：finreport_fetcher + finreport_charts

本仓库包含两个相互配合的程序（不同目录）：

1) **finreport_fetcher**：抓取 A 股公司三大报表并导出 Excel，可选下载对应报告期 PDF 原文。
2) **finreport_charts**：基于 fetcher 产出的数据，按选项/模板生成漂亮图表（**PNG + Excel(含原始数据+Excel内置图表)**）。

---

## 目录结构

- `finreport_fetcher/`：财报抓取程序（已实现）
- `finreport_charts/`：图表生成程序（新增）
- `finprice_fetcher/`：股价抓取程序（新增）

文档：
- 快速开始：[`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- 模板说明：[`docs/TEMPLATE_GUIDE.md`](docs/TEMPLATE_GUIDE.md)
- 回归测试：[`docs/TESTING.md`](docs/TESTING.md)
- 股价抓取：见下文 `finprice`（输出 `output/{公司名}_{code6}/price/{code6}.csv` + 同名 `.xlsx` 供 combo 图使用/人工查看）

---

## 安装

建议虚拟环境（推荐安装为可执行命令，这样你在任何目录都能运行）：

```bash
cd a_share_finreport_fetcher
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel

# 安装为 editable（会提供 finfetch / finchart 命令；也支持 python -m finreport_fetcher / finreport_charts）
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
- 多数据源（避免 Sina 被墙导致 akshare 失败）：
  - `--provider auto`：按优先级自动兜底（默认：tushare → akshare_ths(同花顺) → akshare(Sina)）
  - 或手动指定 `--provider tushare|akshare_ths|akshare`
- 报表口径：默认合并；可切换 `--statement-type merged|parent`
- Excel 美化：标题行、冻结窗格、表头样式、交替底色、负数红色、千分位格式、自适应列宽
  - 不输出"报告期末日"列（改为每个 sheet 顶部标题展示）
  - 不输出 PDF 链接/本地路径列（改为标题下方注释行展示）
  - **新增**：每行包含稳定的模板键 `key`（ASCII-only，如 `is.revenue_total` / `bs.cash`；即使未命中词典也会生成可读英文 key）
  - **新增**：每行包含 `备注`（英文名称），用于你后续校对/补全词典映射；并且 **备注永远是最后一列**
  - **固定列顺序**（跨数据源保持一致）：`科目 | 数值 | (空白列) | key | 备注`
  - **约束**：不再导出 `科目_CN` / `科目_EN` 两列（避免重复）
- PDF：`--pdf` 下载，保存为 `output/{公司名}_{code6}/pdf/{code6}_{report_period}.pdf`

### 清理策略

- 默认：每次执行会先清理“本次公司(code6)”的历史文件（`{code6}_*.xlsx` / `{code6}_*.pdf`），不影响其他公司目录。
- 若需要增量写入（例如给图表程序补数据用）：加 `--no-clean`。

### 使用示例

```bash
# 推荐：模板驱动（run）
# （若已 `pip install -e .` 安装为命令，可把 `python3 -m finreport_charts` 换成 `finchart`）
python3 -m finreport_charts run \
  --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --data-dir output \
  --templates templates \
  --template net_profit_q

# 只想跑目录下全部模板：
python3 -m finreport_charts run \
  --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"

# 说明：finreport_charts 的 bar/pie/combo/template 子命令已弃用，会提示并以退出码 2 退出
```

### 公司分类配置（category）

项目根目录提供 `config/company_categories.toml` 作为全局分类配置：

```toml
[categories.net_security]
alias = "网络安全软件开发"
items = [
  { name = "天融信", code = "600533" },
  { name = "深信服", code = "300454" },
]
```

- `name` 是分类名（命令行 `--category` 使用）
- `alias` 为显示名（可选）
- `items` 为公司列表：`name` + `code`（6 位股票代码，可写字符串或数字）

命令示例：

```bash
# 批量抓取某一分类
python3 -m finreport_fetcher fetch \
  --category net_security \
  --start 2020-01-01 --end 2025-12-31 \
  --out output --no-clean

# 批量生成某一分类图表
python3 -m finreport_charts run \
  --category net_security \
  --start 2020-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*"
```

可用 `--category-config` 指定自定义配置文件路径。

> 说明：分类模式会根据分类内所有公司统一图表的纵轴范围与图幅尺寸，便于横向对比。

### 输出目录结构

默认输出到 `./output`，并按公司归档到 `{公司名}_{code6}` 目录：

```
output/
  {公司名}_600519/
    reports/
      600519_merged_20241231.xlsx
      600519_merged_20240930.xlsx
    pdf/
      600519_20241231.pdf
      600519_20240930.pdf
    charts/
      *.png
      *.xlsx
```


> 目录名中的 `{公司名}` 会尽量按 A 股正式简称解析；解析失败则退化为 code6。

### 占位符说明

文档中的 `{code6}` / `{公司名}` 均为**占位符**，用于说明文件路径/命名规则：
- `{code6}` = 6 位股票代码（文件名与路径里的实际值）
- `{公司名}` = 公司名称或简称（用于目录名）

它们只是文档里的“替换提示”，不是给人阅读时展示的字段名。

---

## 2) finreport_charts（图表生成）

### 核心需求对照

- 每张图输出 2 个文件：
  - `*.png`：图片
  - `*.xlsx`：原始数据 + Excel 内置图表
- 支持 `--start/--end` 时间范围
  - `mode=trend`：范围内生成 1 张趋势图（1 个 png + 1 个 xlsx）
  - `mode=compare`：范围内**每个报告期**生成 1 张比较图（每期 1 个 png + 1 个 xlsx）；如需单期末可用 `--as-of` 或模板 `period_end`
- 若 `--data-dir` 缺少所需报告期财报，程序会自动调用 `finreport_fetcher` 补齐（增量写入，不清空目录）
- 支持：
  - 柱状图趋势（bar）：按模板 `expr` 逐期取值/计算（不再使用 transform 口径配置）
  - 折线图趋势（line）：与 bar 共用 `[[bars]]` 配置，输出折线图
  - 同型分析饼图（pie）：范围内每期一张，支持 `section` 或 `items`，支持 TopN+其他
  - 合并双轴图（combo）：财务柱 + 股价折线，股价来自 CSV（列 `date,close`；同时会生成同名 `.xlsx` 便于人工查看）
- **模板驱动（推荐）**：每个模板一个 TOML 文件（`templates/*.toml`），通过 `finreport_charts run` 执行（支持跑全部模板或指定单个/多个模板）
- **新增**：支持使用 `key`（如 `is.revenue_total` / `bs.cash`）替代中文科目名，实现跨公司标准化引用

### 约定：数据目录（--data-dir）

`--data-dir` 需要指向 **finreport_fetcher** 的输出根目录：

- Excel：`output/{公司名}_{code6}/reports/{code6}_{statement}_{period}.xlsx`
- PDF：`output/{公司名}_{code6}/pdf/{code6}_{period}.pdf`（PDF 与 Excel 不同层级；PDF 统一放入 `pdf/` 子目录）

股价数据（由 `finprice fetch` 生成）默认约定位置（优先新路径，兼容旧路径）：

```
{data-dir}/{公司名}_{code6}/price/{code6}.csv
{data-dir}/{公司名}_{code6}/price/{code6}.xlsx
```

（兼容旧路径：`{data-dir}/price/{code6}.csv`）

CSV 列名要求：`date, close`。

### 常见报错：未映射科目缺少英文名称

当你看到类似错误：

- `未映射科目缺少英文名称，请补齐 subject_glossary 映射：XXX`

含义：当前数据源返回了科目 `XXX`，但我们的标准科目表（`finreport_fetcher/mappings/subject_glossary.py`）里没有对应的英文名与稳定 key。

处理方式：
1. 在 `subject_glossary.py` 新增一条 `SubjectSpec("<prefix>.<ascii_key>", "XXX", "<English>")`（prefix 为 `bs/is/cf`）。
2. 运行回归测试：`scripts/regression_test.sh` 或 `python3 -m pytest -q`。
3. 重新执行 `finreport_fetcher fetch ...`。

### 使用示例

```bash
# 推荐：模板驱动（run）
# （若已 `pip install -e .` 安装为命令，可把 `python3 -m finreport_charts` 换成 `finchart`）
python3 -m finreport_charts run \
  --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --data-dir output \
  --templates templates \
  --template net_profit_q

# 过滤输出报告期（仅影响绘图输出，不影响补数/取数）
python3 -m finreport_charts run \
  --code 600519 \
  --start 2023-01-01 --end 2025-12-31 \
  --data-dir output \
  --templates templates \
  --template "*" \
  --period q4,q2
```

### 模板化（TOML，推荐：单模板单文件）

- 模板目录：`templates/`（仓库根目录）
- 每个模板一个文件：`templates/<template_name>.toml`
- 输出文件名：优先使用 `alias`，否则用文件名（stem）

运行全部模板：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates
```

只运行指定模板（可多次）：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates \
  --template net_profit_q
```

> 兼容旧版：仍支持单文件多模板（`charts.toml` + `finreport_charts template --type xxx`），但不再推荐。

---

## 新增功能说明（v0.2）

### 1. 财报 Excel 固定格式（跨数据源一致）
导出列顺序固定为：`科目 | 数值 | (空白列) | key | 备注`（**备注永远在最后一列**）。

- `科目`：规范中文科目名（来自 `subject_glossary`，必要时保留“其中/加/减”前缀）
- `数值`：金额（自动格式化，负数红色，千分位）
- `key`：模板标准键（ASCII-only，如 `is.revenue_total` / `bs.cash`），且**每行都有 key**
- `备注`：英文名称（用于校对/补全映射）

### 2. 表达式跨期取数（替代 transform）
表达式里的标识符支持后缀，便于在 `expr` 内做差分/跨期：
- `.YYYY.MM.DD`：指定报告期末（例如 `bs.cash.2024.12.31`）
- `.prev`：上一季度（可链式：`.prev.prev`）
- `.prev_in_year`：同年上一季度（Q1 视为 0.0），适合把累计值差分为单季

示例（单季归母净利润）：
- `is.net_profit_parent - is.net_profit_parent.prev_in_year`

### 3. Key 引用
支持使用标准 key（如 `is.revenue_total` / `bs.cash`）替代中文科目名，实现：
- 跨公司标准化引用
- 避免中文科目名差异问题
- 便于模板复用

详见 [docs/README.md](docs/README.md) 与 [docs/TEMPLATE_GUIDE.md](docs/TEMPLATE_GUIDE.md)

---

## 3) finprice_fetcher（股价抓取）

用于给 `combo` 双轴图提供 `{data-dir}/{公司名}_{code6}/price/{code6}.csv`（兼容 `{data-dir}/price/{code6}.csv`）。

示例（日频）：

```bash
finprice fetch --code 600519 \
  --start 2024-01-01 --end 2024-12-31 \
  --frequency daily \
  --provider auto \
  --out output
```

- provider：`auto|akshare|tushare`（auto 默认 token 有则 tushare，否则 akshare）
- frequency：`daily|weekly|monthly`（tushare 目前仅支持 daily；周/月请用 akshare）

输出：

```
output/贵州茅台_600519/price/600519.csv
output/贵州茅台_600519/price/600519.xlsx
```

---

## 免责声明

本工具依赖公开数据源与第三方库；不同数据源字段口径可能存在差异。
程序会尽量统一与标注数据来源，但请以公司正式披露为准。
