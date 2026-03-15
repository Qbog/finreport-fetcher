# 6) 测试与 CI

本项目对稳定性要求很高（模板化、跨 provider、一旦财报结构错了会造成级联错误）。因此约定：

- **每次改代码后必须跑回归测试**（至少本地）。

---

## 6.1 本地测试（推荐）

一条命令跑全套：

```bash
scripts/regression_test.sh
```

该脚本会依次执行：

1. `python3 -m compileall`（语法/导入层面的快速检查）
2. `python3 -m pytest -q`（单元/回归测试）

---

## 6.2 测试覆盖建议

新增功能时，优先补以下类型测试：

- **enrich/去重/结构修补**：防止“长度不一致”“结构标题插入错位”等回归
- **Excel schema 固定**：列顺序、必需列是否存在（`key/备注/英文`），列宽是否合理
- **provider 后处理**：例如 akshare_ths 的资产负债表结构注入逻辑

---

## 6.3 CI（GitHub Actions）建议

建议在仓库根目录添加：`.github/workflows/tests.yml`（示例）

```yaml
name: tests
on:
  push:
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: python -m pip install -U pip
      - run: python -m pip install -e .
      - run: scripts/regression_test.sh
```

> 注意：CI 环境通常不具备 tushare token。测试应尽量使用“构造 df/本地逻辑”，避免依赖真实联网数据源。
