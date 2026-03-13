# Chart templates (TOML)

本目录用于 `finreport_charts run` 的模板文件：**一个模板一个 `.toml` 文件**。

## 1) 最小示例（bar）

```toml
alias = "net_profit_q"
chart = "bar"          # bar|pie|combo
statement = "利润表"
item = "is.net_profit" # 推荐填 key
transform = "q"        # q|ytd|ttm|raw
```

## 2) 运行方式

- 运行整个目录下全部模板：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates
```

- 只运行一个模板文件（可重复多次）：

```bash
python3 -m finreport_charts run --code 600519 --start 2024-01-01 --end 2024-12-31 \
  --data-dir output --templates templates --template net_profit_q
```

## 3) 输出位置

默认输出到：`{data_dir}/{公司名}_{code6}/charts/`。

> 其中 `{公司名}_{code6}` 的公司名会尽量按 A 股正式简称解析；解析失败则退化为 code6。
