# Web 报表分析台

`finreport_web` 提供一个本地 Web 服务界面，用于：

- 选择公司、时间范围、公司分类
- 读取/编辑 `config/company_categories.toml`
- 一次性运行全部财报分析模板
- 按 **趋势分析 / 结构分析 / 同业分析** 三类显示图表
- 用键盘方向键切换图表

---

## 1. 启动服务

```bash
cd /mnt/hgfs/share_with_vm/a_share_finreport_fetcher
python3 -m finreport_web serve \
  --host 0.0.0.0 \
  --port 8787 \
  --data-dir output \
  --templates templates \
  --category-config config/company_categories.toml
```

如果你已 `pip install -e .`，也可以用：

```bash
finweb serve --host 0.0.0.0 --port 8787 --data-dir output --templates templates
```

打开：

```text
http://127.0.0.1:8787
```

---

## 2. 页面说明

### 左侧：分析设置

- 公司（支持代码/名称）
- 时间范围
- 公司分类（用于同业对比模板）
- 模板选择（默认全选）
- 分类配置编辑器（直接保存到 TOML 文件）

### 右侧：报表浏览区

- 自动按三类展示：
  - 趋势分析
  - 结构分析
  - 同业分析
- 当前图支持：
  - 打开原图
  - 下载对应 Excel

---

## 3. 键盘操作

- `←` / `→`：在当前分析类目内切换图片
- `↑` / `↓`：切换分析类目（趋势 / 结构 / 同业）

> 当输入框或文本框聚焦时，方向键不会抢输入焦点。

---

## 4. 输出目录

每次 Web 端发起生成，都会把结果单独输出到：

```text
output/{公司名}_{code6}/charts/web/{时间戳}/
```

这样可以：

- 保留历史 Web 生成记录
- 避免和手工命令行生成的旧图互相覆盖
- 页面可以稳定只显示本次生成结果

---

## 5. 同业对比逻辑

当你在页面里选择了公司分类，例如 `test` / `net_security`：

- peer 模板会自动把该分类下的其它公司作为 `--peer`
- 当前公司会自动去重，不会重复加入

如果不选分类：

- peer 模板会使用模板 TOML 中写死的 `peers = [...]`

---

## 6. 模板选择逻辑

Web 端默认只展示 **财报分析模板**，即 `mode` 为：

- `trend`
- `structure`
- `peer`

不会把 `mode=price`、`pie`、`combo` 这些混进主界面，避免分类混乱。

---

## 7. 备注

- 页面是轻量本地服务，不依赖数据库
- 配置持久化到仓库里的 TOML 文件
- 图表仍然调用现有的 `finreport_charts run`，所以命令行和 Web 结果保持一致
