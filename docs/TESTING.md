# 回归测试（Regression Testing）

目标：每次改动代码后，都能用**离线**方式快速发现类似“导出 Excel 报错 / 行数不一致 / 列顺序变了 / 列宽异常”这类回归问题。

## 1) 安装测试依赖

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
pip install -e ".[dev]"
```

## 2) 运行单元测试（推荐每次提交前都跑）

```bash
pytest -q
```

当前测试覆盖重点：
- `enrich_statement_df` 去重/插行逻辑不会再触发 `Length of values ... does not match length of index ...`
- Excel 导出列顺序固定为：`科目 | 数值 | (空白列) | key | 备注`，且 `备注` 永远在最后一列
- 财报 sheet 的列宽自适应不会被 A1/A2 标题/注释行错误撑爆
- THS 资产负债表结构整理：插入【报表核心指标】与【股东权益】标题行

## 3) 手动 smoke（可选，有网络时）

```bash
python3 -m finreport_fetcher -l info fetch --code 300454 --date 2024-12-31 --provider auto --statement-type merged --out output --no-clean
python3 -m finreport_charts -l info run --code 300454 --start 2023-01-01 --end 2024-12-31 --data-dir output --templates templates --template "*"
```
