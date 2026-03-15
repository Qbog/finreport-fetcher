# 4) 常见报错与排查

本页只收录“高频且可操作”的排查路径。

---

## 4.1 未映射科目缺少英文名称

报错示例：

- `未映射科目缺少英文名称，请补齐 subject_glossary 映射：XXX`

含义：数据源返回了科目 `XXX`，但我们的标准科目表（`finreport_fetcher/mappings/subject_glossary.py`）没有该科目的英文翻译与稳定 key。

处理方式：

1. 打开 `finreport_fetcher/mappings/subject_glossary.py`，新增一条：

```py
SubjectSpec(
    "bs.some_key",
    "XXX",
    "English name",
    common=False,
    note="非通用科目：仅部分公司披露...",
)
```

2. 跑测试：

```bash
scripts/regression_test.sh
```

3. 重新抓取该报告期：

```bash
python3 -m finreport_fetcher fetch --code 002594 --start 2020-03-31 --end 2020-03-31 --out output --no-clean
```

---

## 4.2 缺失财报 / 跳过缺失期

现象：

- `发现缺失财报 N 期...`
- `补齐后仍缺失 M 期财报，将跳过缺失期继续绘图`

原因：
- `data-dir` 下确实没有该期 Excel；或者
- 数据源在该期没有披露；或者
- 数据源接口波动/限流。

排查建议：

1) 先看该期 Excel 是否存在：

```
ls -la output/{公司名}_{code6}/reports
```

2) 单期重试抓取，观察错误尾行：

```bash
python3 -m finreport_fetcher -l warning fetch --code 002594 --start 2020-03-31 --end 2020-03-31 --out output --no-clean
```

3) 若你希望“缺一期就报错退出”，在 charts 里使用 `--strict`。

---

## 4.3 模板提示“在该区间内没有可用数据”

含义：模板所需科目/表达式在区间内每一期都无法计算出有效值。

常见原因：
- 财报缺失（Excel 不存在）
- 模板引用的 `key` 不存在（科目未出现在该期报表）
- 表达式失败（变量缺失/除零等）

排查建议：

1) 先确认 Excel 中是否存在对应 `key`：打开某一期 `reports/*.xlsx`，查看该科目行的 `key` 列。

2) 尽量使用 `key` 写模板（不要用中文科目名）：

- ✅ `expr = "bs.cash"`
- ❌ `expr = "货币资金"`

3) 若该科目是非通用科目（Excel 淡黄色行），建议在模板里做容错或只对特定行业使用。

---

## 4.4 combo 找不到股价 CSV

报错示例：

- `未找到股价 CSV: ...`

解决：

1) 先跑股价抓取：

```bash
python3 -m finprice_fetcher fetch --code 002594 --start 2024-01-01 --end 2024-12-31 --out output
```

2) 默认位置：

- `output/{公司名}_{code6}/price/{code6}.csv`

（兼容旧路径 `output/price/{code6}.csv`）
