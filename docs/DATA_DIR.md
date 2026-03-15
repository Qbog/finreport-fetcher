# 2) 数据目录规范（data-dir / out）

本项目所有工具都围绕一个“输出根目录”工作：

- `finreport_fetcher fetch --out output`
- `finprice fetch --out output`
- `finreport_charts run --data-dir output`

> 约定：文档中用 `{data-dir}` 表示该根目录（默认 `output/`）。

---

## 2.1 公司归档目录

所有数据会按公司归档：

```
{data-dir}/{公司名}_{code6}/
```

示例：

```
output/比亚迪_002594/
```

该目录名会做安全清洗（避免 `/`、`:` 等非法路径字符）。

---

## 2.2 财报 Excel（finreport_fetcher）

```
{data-dir}/{公司名}_{code6}/reports/
  {code6}_{statement_type}_{period_end}.xlsx
```

示例：

```
output/比亚迪_002594/reports/002594_merged_20200331.xlsx
```

- `statement_type`：`merged`（合并口径）或 `parent`（母公司口径）
- `period_end`：报告期末（`YYYYMMDD`）

### Excel 表头/列说明

每个 sheet 都会固定列顺序：

`科目 | 数值 | (空白列) | key | 备注 | 英文`

- `key`：稳定 ASCII-only（模板建议使用）
- `备注`：中文说明（口径/出现条件等；非通用科目会尽量写明）
- `英文`：英文翻译（便于对照/模板编写）

并且：
- **非通用科目**会整行淡黄色高亮（用于提示“不是每家公司都有”）。

---

## 2.3 股价数据（finprice_fetcher）

```
{data-dir}/{公司名}_{code6}/price/
  {code6}.csv
  {code6}.xlsx
```

CSV 列：`date, close`（combo 图读取 CSV）。

---

## 2.4 图表输出（finreport_charts）

默认输出到：

```
{data-dir}/{公司名}_{code6}/charts/
```

每张图输出两个文件：
- `*.png`
- `*.xlsx`（原始数据 + Excel 图表）
