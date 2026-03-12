# finreport-fetcher (A股财报抓取工具)

按**股票代码或名称**抓取 A 股公司三大报表：
- 资产负债表
- 利润表
- 现金流量表

并导出为 Excel（每张表一个 sheet），以及可选下载对应报告期的**财报 PDF 原文**（尽量从交易所/巨潮公告中解析）。

## 功能概览

- 支持输入：
  - 代码：`600519` / `600519.SH` / `sh600519` / `000001.SZ` 等
  - 名称模糊匹配：如 `茅台`（重名会列出候选供选择）
- 日期逻辑：
  - `--date`：取该日期**之前最近一期已披露**（通过“能否抓到数据”做可用性判断）的报告期末日
  - `--start --end`：取范围内所有报告期末日（03-31/06-30/09-30/12-31）逐个导出
- 多数据源：
  - `--provider auto`：按优先级自动兜底（默认：tushare -> akshare）
  - 或手动指定 `--provider tushare|akshare`
- 命令形态：`python3 -m finreport_fetcher fetch ...`（无需安装本项目也可运行）
- 报表口径：默认合并；可切换 `--statement-type merged|parent`
- Excel 美化：冻结窗格、表头样式、交替底色、负数红色、千分位格式、自适应列宽
- PDF：`--pdf` 下载，并在 Excel 里写入 PDF 链接/本地路径（若获取成功）

## 安装

建议使用虚拟环境：

```bash
cd a_share_finreport_fetcher
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
# 如需 tushare：
pip install tushare

# 也可以尝试直接安装本项目（若你的 pip/setuptools 支持 pyproject）：
# pip install .
```

> 如使用 tushare，需要设置环境变量 `TUSHARE_TOKEN`，或在运行时传入 `--tushare-token`。

## 使用示例

### 1) 单个日期：取最近一期报告期

```bash
python3 -m finreport_fetcher fetch --name 茅台 --date 2025-02-01 --pdf
```

### 2) 日期范围：导出范围内所有报告期

```bash
python3 -m finreport_fetcher fetch --code 600519 --start 2023-01-01 --end 2025-12-31 --pdf
```

### 3) 手动指定数据源 + 母公司口径

```bash
python3 -m finreport_fetcher fetch --code 600519.SH --date 2024-08-01 --provider akshare --statement-type parent
```

## 输出目录结构

默认输出到 `./output`：

```
output/
  600519_merged_20241231.xlsx
  600519_merged_20240930.xlsx
  pdf/
    600519/
      20241231/
        report.pdf
```

## 免责声明

本工具依赖公开数据源（Sina/巨潮/交易所等）与第三方库；不同数据源字段口径可能存在差异。
程序会尽量统一与标注数据来源，但请以公司正式披露为准。
