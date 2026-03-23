from __future__ import annotations

import json
import mimetypes
import os
import re
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from finreport_charts.data.finreport_store import expected_xlsx_path, load_price_csv, read_statement_df
from finreport_charts.templates.config import BarBlock, Template, load_template_dir, template_lookup_names
from finreport_charts.utils.expr import ExprError, eval_expr, tokenize
from finreport_fetcher.global_datasets import load_company_basics_csv, load_financial_metrics_csv
from finreport_fetcher.utils.company_categories import CompanyCategory, CompanyCategoryItem, load_company_categories
from finreport_fetcher.utils.dates import parse_date, quarter_ends_between
from finreport_fetcher.utils.paths import safe_dir_component
from finreport_fetcher.utils.symbols import ResolvedSymbol, load_a_share_name_map, parse_code


_ID_DATE_SUFFIX = re.compile(r"^(?P<id>.+?)\.(?P<y>\d{4})\.(?P<m>\d{2})\.(?P<d>\d{2})$")


@dataclass(frozen=True)
class TemplateView:
    key: str
    label: str
    names: list[str]
    mode: str
    type: str


@dataclass
class AppContext:
    repo_root: Path
    data_dir: Path
    templates_dir: Path
    category_config: Path

    @property
    def static_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static"

    def index_path(self) -> Path:
        return self.static_dir / "index.html"

    def load_company_basics_payload(self) -> list[dict[str, Any]]:
        try:
            df = load_company_basics_csv(self.data_dir)
            if df.empty:
                raise RuntimeError("empty")
            out: list[dict[str, Any]] = []
            for _, row in df.fillna("").iterrows():
                out.append(
                    {
                        "code6": str(row.get("code6") or "").zfill(6),
                        "name": str(row.get("name") or "").strip(),
                        "industry": str(row.get("industry") or "").strip(),
                        "market": str(row.get("market") or "").strip(),
                        "listDate": str(row.get("list_date") or "").strip(),
                    }
                )
            return [x for x in out if x["code6"]]
        except Exception:
            df_map = load_a_share_name_map()
            return [
                {"code6": str(row["code"]).zfill(6), "name": str(row["name"]), "industry": "", "market": "", "listDate": ""}
                for _, row in df_map.iterrows()
            ]

    def load_financial_metrics_summary(self) -> dict[str, Any]:
        try:
            df = load_financial_metrics_csv(self.data_dir)
        except Exception:
            return {"rows": 0, "companies": 0}
        if df.empty:
            return {"rows": 0, "companies": 0}
        return {"rows": int(len(df.index)), "companies": int(df["code6"].astype(str).nunique()) if "code6" in df.columns else 0}

    def load_categories_payload(self) -> list[dict[str, Any]]:
        cats = load_company_categories(self.category_config)
        out: list[dict[str, Any]] = []
        for key, cat in sorted(cats.items()):
            out.append(
                {
                    "key": key,
                    "label": cat.alias or key,
                    "alias": cat.alias,
                    "items": [{"code6": it.code6, "name": it.name} for it in cat.items],
                }
            )
        return out

    def list_financial_templates(self) -> list[TemplateView]:
        loaded = load_template_dir(self.templates_dir)
        out: list[TemplateView] = []
        for tpl in loaded.values():
            mode = normalize_mode(getattr(tpl, "mode", None), type_=str(getattr(tpl, "type", None) or ""))
            if mode not in {"trend", "structure", "peer", "merge"}:
                continue
            label = str(getattr(tpl, "alias", None) or tpl.name)
            out.append(TemplateView(key=tpl.name, label=label, names=template_lookup_names(tpl), mode=mode, type=str(tpl.type)))
        order = {"trend": 0, "structure": 1, "peer": 2, "merge": 3}
        out.sort(key=lambda x: (order.get(x.mode, 99), x.label))
        return out

    def bootstrap_payload(self) -> dict[str, Any]:
        config_text = self.category_config.read_text(encoding="utf-8") if self.category_config.exists() else ""
        return {
            "categories": self.load_categories_payload(),
            "companyBasics": self.load_company_basics_payload(),
            "metricSummary": self.load_financial_metrics_summary(),
            "templates": [
                {"key": t.key, "label": t.label, "names": t.names, "mode": t.mode, "type": t.type}
                for t in self.list_financial_templates()
            ],
            "configText": config_text,
            "dataDir": str(self.data_dir),
            "templatesDir": str(self.templates_dir),
        }

    def save_category_config(self, text: str) -> dict[str, Any]:
        self.category_config.parent.mkdir(parents=True, exist_ok=True)
        self.category_config.write_text(text, encoding="utf-8")
        return {"ok": True, "categories": self.load_categories_payload()}

    def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = slugify_key(str(payload.get("key") or payload.get("label") or ""))
        if not key:
            raise ValueError("分类 key 不能为空")
        label = str(payload.get("label") or key).strip()
        companies = payload.get("companies") or []
        if not isinstance(companies, list) or not companies:
            raise ValueError("请至少选择一家公司")

        existing = load_company_categories(self.category_config) if self.category_config.exists() else {}
        items: list[CompanyCategoryItem] = []
        seen: set[str] = set()
        for row in companies:
            if not isinstance(row, dict):
                continue
            code6 = str(row.get("code6") or "").strip().zfill(6)
            if not re.fullmatch(r"\d{6}", code6) or code6 in seen:
                continue
            seen.add(code6)
            items.append(CompanyCategoryItem(code6=code6, name=str(row.get("name") or "").strip() or None))
        if not items:
            raise ValueError("没有可保存的公司")

        existing[key] = CompanyCategory(name=key, alias=label, items=items)
        self.category_config.parent.mkdir(parents=True, exist_ok=True)
        self.category_config.write_text(render_categories_toml(existing), encoding="utf-8")
        return {"ok": True, "categories": self.load_categories_payload(), "created": key}

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = normalize_mode(str(payload.get("mode") or ""), type_=str(payload.get("type") or ""))
        if mode not in {"trend", "structure", "peer", "merge"}:
            raise ValueError("模板类别仅支持 trend/structure/peer/merge")
        alias = str(payload.get("label") or payload.get("name") or "").strip()
        if not alias:
            raise ValueError("模板名称不能为空")
        key = slugify_key(str(payload.get("key") or alias))
        if not key:
            raise ValueError("模板 key 不能为空")
        expr = str(payload.get("expr") or "").strip()
        if mode != "merge" and not expr:
            raise ValueError("expr 不能为空")
        if mode == "merge":
            content = build_combo_template_text(key=key, alias=alias, bar_item=str(payload.get("barItem") or expr or "is.revenue_total"), line=str(payload.get("line") or "close"))
        else:
            statement = str(payload.get("statement") or guess_statement_from_expr(expr) or "利润表")
            content = build_bar_template_text(key=key, alias=alias, mode=mode, expr=expr, statement=statement)
        path = self.templates_dir / f"{key}.toml"
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "templates": [
            {"key": t.key, "label": t.label, "names": t.names, "mode": t.mode, "type": t.type}
            for t in self.list_financial_templates()
        ], "created": key}

    def _load_template_map(self) -> dict[str, Template]:
        return load_template_dir(self.templates_dir)

    def _select_templates(self, selected: list[str] | None) -> list[Template]:
        loaded = self._load_template_map()
        views = self.list_financial_templates()
        allowed = {v.key for v in views}
        if not selected:
            return [loaded[v.key] for v in views if v.key in loaded]
        norm_map: dict[str, Template] = {}
        for tpl in loaded.values():
            if tpl.name not in allowed:
                continue
            for nm in template_lookup_names(tpl):
                norm_map[nm.strip().lower()] = tpl
            norm_map[tpl.name.strip().lower()] = tpl
            norm_map[str(getattr(tpl, "alias", None) or tpl.name).strip().lower()] = tpl
        out: list[Template] = []
        seen: set[str] = set()
        for raw in selected:
            key = str(raw or "").strip().lower()
            if not key:
                continue
            tpl = norm_map.get(key)
            if not tpl:
                raise ValueError(f"未找到模板：{raw}")
            if tpl.name in seen:
                continue
            seen.add(tpl.name)
            out.append(tpl)
        return out

    def _category_symbols(self, category_key: str | None) -> list[ResolvedSymbol]:
        if not category_key:
            return []
        cats = load_company_categories(self.category_config)
        cat = cats.get(category_key)
        if not cat:
            return []
        out: list[ResolvedSymbol] = []
        for it in cat.items:
            rs = parse_code(it.code6)
            if rs:
                out.append(ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=it.name))
        return out

    def generate_reports(self, payload: dict[str, Any]) -> dict[str, Any]:
        category_key = str(payload.get("category") or "").strip() or None
        start = str(payload.get("start") or "").strip()
        end = str(payload.get("end") or "").strip()
        selected_templates = payload.get("templates") if isinstance(payload.get("templates"), list) else None

        if not category_key:
            raise ValueError("公司类别不能为空")
        if not start or not end:
            raise ValueError("开始/结束日期不能为空")
        start_d = parse_date(start)
        end_d = parse_date(end)
        if start_d > end_d:
            raise ValueError("开始日期不能晚于结束日期")

        periods = quarter_ends_between(start_d, end_d)
        if not periods:
            raise ValueError("所选时间范围内没有标准报告期末日（03-31/06-30/09-30/12-31）")

        companies = self._category_symbols(category_key)
        if not companies:
            raise ValueError(f"分类 {category_key} 未配置公司")
        templates = self._select_templates(selected_templates)
        if not templates:
            raise ValueError("未选中任何分析内容")

        request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_root = self.data_dir / "_global" / "web_runs" / request_id
        run_root.mkdir(parents=True, exist_ok=True)

        errors: list[dict[str, Any]] = []
        section_defs = {
            "trend": [tpl for tpl in templates if normalize_mode(tpl.mode, type_=tpl.type) == "trend"],
            "structure": [tpl for tpl in templates if normalize_mode(tpl.mode, type_=tpl.type) == "structure"],
            "peer": [tpl for tpl in templates if normalize_mode(tpl.mode, type_=tpl.type) == "peer"],
            "merge": [tpl for tpl in templates if normalize_mode(tpl.mode, type_=tpl.type) == "merge"],
        }

        trend_matrix: dict[str, dict[str, dict[str, Any]]] = {}
        structure_matrix: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        peer_matrix: dict[str, dict[str, dict[str, Any]]] = {}
        merge_matrix: dict[str, dict[str, dict[str, Any]]] = {}

        for tpl in section_defs["trend"]:
            trend_matrix[tpl.name] = {}
            for comp in companies:
                try:
                    item = build_trend_chart(self, tpl, comp, periods, run_root / "trend" / tpl.name / comp.code6)
                    if item:
                        trend_matrix[tpl.name][comp.code6] = item
                except Exception as exc:  # noqa: BLE001
                    errors.append({"template": tpl.name, "label": tpl.alias or tpl.name, "company": comp.name or comp.code6, "stderr": str(exc)})

        for tpl in section_defs["structure"]:
            structure_matrix[tpl.name] = {}
            for comp in companies:
                structure_matrix[tpl.name][comp.code6] = {}
                for pe in periods:
                    pe_s = pe.strftime("%Y-%m-%d")
                    try:
                        item = build_structure_chart(self, tpl, comp, pe, run_root / "structure" / tpl.name / comp.code6 / pe_s)
                        if item:
                            item["time"] = pe_s
                            structure_matrix[tpl.name][comp.code6][pe_s] = item
                    except Exception as exc:  # noqa: BLE001
                        errors.append({"template": tpl.name, "label": tpl.alias or tpl.name, "company": comp.name or comp.code6, "time": pe_s, "stderr": str(exc)})

        for tpl in section_defs["peer"]:
            peer_matrix[tpl.name] = {}
            for pe in periods:
                pe_s = pe.strftime("%Y-%m-%d")
                try:
                    item = build_peer_chart(self, tpl, companies, pe, run_root / "peer" / tpl.name / pe_s)
                    if item:
                        item["time"] = pe_s
                        peer_matrix[tpl.name][pe_s] = item
                except Exception as exc:  # noqa: BLE001
                    errors.append({"template": tpl.name, "label": tpl.alias or tpl.name, "time": pe_s, "stderr": str(exc)})

        for tpl in section_defs["merge"]:
            merge_matrix[tpl.name] = {}
            for comp in companies:
                try:
                    item = build_merge_chart(self, tpl, comp, periods, run_root / "merge" / tpl.name / comp.code6)
                    if item:
                        merge_matrix[tpl.name][comp.code6] = item
                except Exception as exc:  # noqa: BLE001
                    errors.append({"template": tpl.name, "label": tpl.alias or tpl.name, "company": comp.name or comp.code6, "stderr": str(exc)})

        return {
            "ok": True,
            "category": category_key,
            "start": start,
            "end": end,
            "reportDir": f"/files/{run_root.resolve().relative_to(self.repo_root.resolve()).as_posix()}",
            "sections": {
                "trend": {
                    "templates": [{"key": tpl.name, "label": str(getattr(tpl, 'alias', None) or tpl.name)} for tpl in section_defs["trend"]],
                    "companies": [{"code6": comp.code6, "name": comp.name or comp.code6} for comp in companies],
                    "matrix": trend_matrix,
                },
                "structure": {
                    "templates": [{"key": tpl.name, "label": str(getattr(tpl, 'alias', None) or tpl.name)} for tpl in section_defs["structure"]],
                    "companies": [{"code6": comp.code6, "name": comp.name or comp.code6} for comp in companies],
                    "times": [pe.strftime("%Y-%m-%d") for pe in periods],
                    "matrix": structure_matrix,
                },
                "peer": {
                    "templates": [{"key": tpl.name, "label": str(getattr(tpl, 'alias', None) or tpl.name)} for tpl in section_defs["peer"]],
                    "times": [pe.strftime("%Y-%m-%d") for pe in periods],
                    "matrix": peer_matrix,
                },
                "merge": {
                    "templates": [{"key": tpl.name, "label": str(getattr(tpl, 'alias', None) or tpl.name)} for tpl in section_defs["merge"]],
                    "companies": [{"code6": comp.code6, "name": comp.name or comp.code6} for comp in companies],
                    "matrix": merge_matrix,
                },
            },
            "errors": errors,
        }


class JsonHttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class RequestMixin:
    server: "WebServer"

    def _write_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise JsonHttpError(400, f"JSON 解析失败：{exc}")
        if not isinstance(data, dict):
            raise JsonHttpError(400, "请求体必须是 JSON object")
        return data

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            raise JsonHttpError(404, f"文件不存在：{path}")
        ctype, _ = mimetypes.guess_type(str(path))
        ctype = ctype or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _resolve_safe_repo_path(self, raw_path: str) -> Path:
        rel = Path(unquote(raw_path.lstrip("/")))
        path = (self.server.ctx.repo_root / rel).resolve()
        repo_root = self.server.ctx.repo_root.resolve()
        if repo_root not in path.parents and path != repo_root:
            raise JsonHttpError(403, "禁止访问仓库外部路径")
        return path


class WebServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls, ctx: AppContext):
        super().__init__(server_address, handler_cls)
        self.ctx = ctx


def create_handler():
    class Handler(RequestMixin, BaseHTTPRequestHandler):
        server: WebServer

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            os.sys.stderr.write("[finreport-web] " + fmt % args + "\n")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            try:
                self._handle_get()
            except JsonHttpError as exc:
                self._write_json({"ok": False, "error": exc.message}, status=exc.status)
            except Exception as exc:  # noqa: BLE001
                self._write_json({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, status=500)

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._handle_post()
            except JsonHttpError as exc:
                self._write_json({"ok": False, "error": exc.message}, status=exc.status)
            except Exception as exc:  # noqa: BLE001
                self._write_json({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, status=500)

        def _handle_get(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                return self._serve_file(self.server.ctx.index_path())
            if path.startswith("/static/"):
                return self._serve_file(self.server.ctx.static_dir / path.removeprefix("/static/"))
            if path == "/api/bootstrap":
                return self._write_json(self.server.ctx.bootstrap_payload())
            if path == "/api/categories":
                text = self.server.ctx.category_config.read_text(encoding="utf-8") if self.server.ctx.category_config.exists() else ""
                return self._write_json({"ok": True, "text": text, "categories": self.server.ctx.load_categories_payload()})
            if path.startswith("/files/"):
                repo_path = self._resolve_safe_repo_path(path.removeprefix("/files/"))
                return self._serve_file(repo_path)
            raise JsonHttpError(404, f"未找到路径：{path}")

        def _handle_post(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            payload = self._read_json_body()
            if path == "/api/generate":
                return self._write_json(self.server.ctx.generate_reports(payload))
            if path == "/api/categories/save":
                text = str(payload.get("text") or "")
                if not text.strip():
                    raise JsonHttpError(400, "配置内容不能为空")
                return self._write_json(self.server.ctx.save_category_config(text))
            if path == "/api/categories/create":
                return self._write_json(self.server.ctx.create_category(payload))
            if path == "/api/templates/create":
                return self._write_json(self.server.ctx.create_template(payload))
            raise JsonHttpError(404, f"未找到路径：{path}")

    return Handler


def normalize_mode(mode: str | None, *, type_: str | None = None) -> str:
    m = str(mode or "").strip().lower().replace("compare", "structure")
    t = str(type_ or "").strip().lower()
    if t == "combo" or m == "merge":
        return "merge"
    return m


def slugify_key(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(text or "").strip()).strip("_").lower()
    return s or "item"


def render_categories_toml(categories: dict[str, CompanyCategory]) -> str:
    lines = ["# 公司分类配置（由 Web 端保存）", ""]
    for key in sorted(categories):
        cat = categories[key]
        lines.append(f"[categories.{cat.name}]")
        if cat.alias:
            lines.append(f'alias = "{cat.alias}"')
        lines.append("items = [")
        for item in cat.items:
            if item.name:
                lines.append(f'  {{ name = "{item.name}", code = "{item.code6}" }},')
            else:
                lines.append(f'  {{ code = "{item.code6}" }},')
        lines.append("]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def guess_statement_from_expr(expr: str) -> str:
    ss = str(expr or "").strip().lower()
    if ss.startswith("bs."):
        return "资产负债表"
    if ss.startswith("cf."):
        return "现金流量表"
    return "利润表"


def build_bar_template_text(*, key: str, alias: str, mode: str, expr: str, statement: str) -> str:
    title = alias + ("趋势" if mode == "trend" else "分析")
    return f'''name = "{key}"
alias = "{alias}"

type = "bar"
mode = "{mode}"

title = "{title}"
x_label = "{'报告期' if mode == 'trend' else '科目'}"
y_label = "数值"

statement = "{statement}"

[[bars]]
name = "{alias}"
expr = "{expr}"
'''


def build_combo_template_text(*, key: str, alias: str, bar_item: str, line: str) -> str:
    return f'''name = "{key}"
alias = "{alias}"

type = "combo"
mode = "merge"

title = "{alias}（财务 + 股价）"
x_label = "报告期"
y_label = "财务数值"

bar_item = "{bar_item}"
line = "{line}"
'''


def flatten_bars(blocks: list[BarBlock] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def visit(block: BarBlock, inherited_color: str | None = None) -> None:
        color = block.color or inherited_color
        if block.children:
            for child in block.children:
                visit(child, color)
        elif block.expr:
            out.append({"name": block.name, "expr": block.expr, "statement": block.statement, "color": color})

    for b in blocks or []:
        visit(b)
    return out


def latest_quarter_end_on_or_before(d: date) -> date:
    qs = quarter_ends_between(date(d.year - 2, 1, 1), d)
    if not qs:
        raise RuntimeError(f"无法推断季末：{d}")
    return qs[-1]


def prev_quarter_end(pe: date) -> date:
    pe0 = latest_quarter_end_on_or_before(pe)
    mmdd = pe0.strftime("%m%d")
    if mmdd == "0331":
        return date(pe0.year - 1, 12, 31)
    if mmdd == "0630":
        return date(pe0.year, 3, 31)
    if mmdd == "0930":
        return date(pe0.year, 6, 30)
    return date(pe0.year, 9, 30)


def prev_in_year_quarter_end(pe: date) -> date | None:
    pe0 = latest_quarter_end_on_or_before(pe)
    mmdd = pe0.strftime("%m%d")
    if mmdd == "0331":
        return None
    if mmdd == "0630":
        return date(pe0.year, 3, 31)
    if mmdd == "0930":
        return date(pe0.year, 6, 30)
    if mmdd == "1231":
        return date(pe0.year, 9, 30)
    return None


def split_id_date(s: str) -> tuple[str, date | None]:
    m = _ID_DATE_SUFFIX.match(str(s or ""))
    if not m:
        return str(s or ""), None
    return m.group("id"), date(int(m.group("y")), int(m.group("m")), int(m.group("d")))


def statement_from_key(key0: str, default_statement: str) -> str:
    k2 = str(key0 or "").strip().lower()
    if k2.startswith("is."):
        return "利润表"
    if k2.startswith("bs."):
        return "资产负债表"
    if k2.startswith("cf."):
        return "现金流量表"
    return default_statement


class CompanyDataResolver:
    def __init__(self, ctx: AppContext, rs: ResolvedSymbol):
        self.ctx = ctx
        self.rs = rs
        self._sheet_cache: dict[tuple[date, str], pd.DataFrame] = {}
        self._price_cache: pd.DataFrame | None = None

    def xlsx_for(self, pe: date) -> Path:
        return expected_xlsx_path(self.ctx.data_dir, self.rs.code6, "merged", pe, name=self.rs.name)

    def _load_statement_df(self, pe: date, statement: str) -> pd.DataFrame:
        key = (pe, statement)
        if key not in self._sheet_cache:
            xlsx = self.xlsx_for(pe)
            if not xlsx.exists():
                raise FileNotFoundError(f"缺少财报文件：{xlsx}")
            self._sheet_cache[key] = read_statement_df(xlsx, statement)
        return self._sheet_cache[key]

    def _value_map(self, pe: date, statement: str) -> dict[str, float]:
        df = self._load_statement_df(pe, statement)
        m: dict[str, float] = {}
        if "key" in df.columns:
            for k2, v2 in zip(df["key"].astype(str), df["数值"]):
                if pd.isna(v2) or v2 is None:
                    continue
                try:
                    m[str(k2)] = float(v2)
                except Exception:
                    continue
        return m

    def _get_subject_value(self, pe: date, statement: str, item: str) -> float | None:
        df = self._load_statement_df(pe, statement)
        if "key" in df.columns and "." in item:
            sub = df[df["key"].astype(str) == item]
        else:
            sub = df[df["科目"].astype(str) == item]
        if sub.empty:
            return None
        v = sub.iloc[0]["数值"]
        if pd.isna(v):
            return None
        return float(v)

    def resolve_ident(self, ident: str, *, current_pe: date, default_statement: str) -> float | None:
        ident_s = str(ident or "").strip()
        if not ident_s:
            return None
        prev_in_year = False
        if ident_s.endswith(".prev_in_year"):
            prev_in_year = True
            ident_s = ident_s[: -len(".prev_in_year")]
        prev_n = 0
        while ident_s.endswith(".prev"):
            prev_n += 1
            ident_s = ident_s[: -len(".prev")]
        base, specified_date = split_id_date(ident_s)
        statement = statement_from_key(base, default_statement)
        target_pe = latest_quarter_end_on_or_before(specified_date) if specified_date else current_pe
        if prev_in_year:
            target_pe = prev_in_year_quarter_end(target_pe) or target_pe
            if prev_in_year_quarter_end(current_pe) is None and specified_date is None:
                return 0.0
        for _ in range(prev_n):
            target_pe = prev_quarter_end(target_pe)
        m = self._value_map(target_pe, statement)
        if base in m:
            return float(m[base])
        return self._get_subject_value(target_pe, statement, base)

    def eval_expr(self, expr: str, *, current_pe: date, default_statement: str) -> float | None:
        expr_s = str(expr or "").strip()
        if not expr_s:
            return None
        if re.search(r"[\+\-\*/\(\)]", expr_s):
            toks = tokenize(expr_s)
            ids = [t for t in toks if t not in {"+", "-", "*", "/", "(", ")"} and not re.fullmatch(r"\d+(?:\.\d+)?", t)]
            vals: dict[str, float] = {}
            for ident in ids:
                val = self.resolve_ident(ident, current_pe=current_pe, default_statement=default_statement)
                if val is None:
                    raise ExprError(f"缺少变量: {ident}")
                vals[ident] = float(val)
            return float(eval_expr(expr_s, vals))
        if "." in expr_s:
            return self.resolve_ident(expr_s, current_pe=current_pe, default_statement=default_statement)
        return self._get_subject_value(current_pe, default_statement, expr_s)

    def load_price(self) -> pd.DataFrame:
        if self._price_cache is not None:
            return self._price_cache
        candidates = list((self.ctx.data_dir / f"{safe_dir_component((self.rs.name or self.rs.code6) + '_' + self.rs.code6)}" / "price").glob(f"{self.rs.code6}*.csv"))
        if not candidates:
            company_matches = list(self.ctx.data_dir.glob(f"*_{self.rs.code6}/price/{self.rs.code6}*.csv"))
            candidates = sorted(company_matches)
        if not candidates:
            raise FileNotFoundError(f"缺少股价 CSV：{self.rs.code6}")
        self._price_cache = load_price_csv(candidates[0])
        return self._price_cache

    def price_series(self, periods: list[date], field: str = "close") -> list[float | None]:
        df = self.load_price()
        if field != "close" and field not in df.columns:
            raise ValueError(f"股价字段不存在：{field}")
        out: list[float | None] = []
        for pe in periods:
            sub = df[df["date"] <= pe]
            if sub.empty:
                out.append(None)
                continue
            val = sub.iloc[-1][field if field in sub.columns else "close"]
            out.append(None if pd.isna(val) else float(val))
        return out


def save_plot_with_excel(fig, df: pd.DataFrame, *, out_dir: Path, stem: str, repo_root: Path, title: str, mode: str, company: str | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    xlsx = out_dir / f"{stem}.xlsx"
    fig.savefig(png, bbox_inches="tight", dpi=160)
    plt.close(fig)
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
    return {
        "title": title,
        "template": stem,
        "label": title,
        "company": company,
        "image": f"/files/{png.resolve().relative_to(repo_root.resolve()).as_posix()}",
        "xlsx": f"/files/{xlsx.resolve().relative_to(repo_root.resolve()).as_posix()}",
        "filename": png.name,
        "mode": mode,
    }


def build_trend_chart(ctx: AppContext, tpl: Template, rs: ResolvedSymbol, periods: list[date], out_dir: Path) -> dict[str, Any] | None:
    resolver = CompanyDataResolver(ctx, rs)
    bars = flatten_bars(tpl.bars)
    if not bars:
        raise RuntimeError("趋势模板缺少 bars")
    labels = [pe.strftime("%Y-%m-%d") for pe in periods]
    data = {"period": labels}
    for bar in bars:
        values = []
        for pe in periods:
            values.append(resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or tpl.statement or "利润表")))
        data[bar["name"]] = values
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for bar in bars:
        ax.plot(df["period"], df[bar["name"]], marker="o", label=bar["name"])
    ax.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name}")
    ax.set_xlabel(tpl.x_label or "报告期")
    ax.set_ylabel(tpl.y_label or "数值")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate(rotation=30)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="trend", company=rs.name or rs.code6)


def build_structure_chart(ctx: AppContext, tpl: Template, rs: ResolvedSymbol, pe: date, out_dir: Path) -> dict[str, Any] | None:
    resolver = CompanyDataResolver(ctx, rs)
    bars = flatten_bars(tpl.bars)
    if not bars:
        raise RuntimeError("结构模板缺少 bars")
    rows = []
    for bar in bars:
        rows.append({"item": bar["name"], "value": resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or tpl.statement or "利润表"))})
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(df["item"], df["value"], color="#4E79A7")
    ax.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name} · {pe.strftime('%Y-%m-%d')}")
    ax.set_xlabel(tpl.x_label or "科目")
    ax.set_ylabel(tpl.y_label or "数值")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.25)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}_{pe.strftime('%Y%m%d')}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="structure", company=rs.name or rs.code6)


def build_peer_chart(ctx: AppContext, tpl: Template, companies: list[ResolvedSymbol], pe: date, out_dir: Path) -> dict[str, Any] | None:
    bars = flatten_bars(tpl.bars)
    if not bars:
        raise RuntimeError("同业模板缺少 bars")
    rows: list[dict[str, Any]] = []
    for comp in companies:
        resolver = CompanyDataResolver(ctx, comp)
        row = {"company": comp.name or comp.code6}
        for bar in bars:
            row[bar["name"]] = resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or tpl.statement or "利润表"))
        rows.append(row)
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    if len(bars) == 1:
        ax.bar(df["company"], df[bars[0]["name"]], color="#4E79A7")
    else:
        base = range(len(df.index))
        width = 0.8 / max(len(bars), 1)
        for idx, bar in enumerate(bars):
            pos = [x + idx * width for x in base]
            ax.bar(pos, df[bar["name"]], width=width, label=bar["name"])
        ax.set_xticks([x + width * (len(bars) - 1) / 2 for x in base], df["company"])
        ax.legend(loc="best")
    ax.set_title(f"{tpl.alias or tpl.name} · {pe.strftime('%Y-%m-%d')}")
    ax.set_xlabel(tpl.x_label or "公司")
    ax.set_ylabel(tpl.y_label or "数值")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{pe.strftime('%Y%m%d')}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="peer")


def build_merge_chart(ctx: AppContext, tpl: Template, rs: ResolvedSymbol, periods: list[date], out_dir: Path) -> dict[str, Any] | None:
    resolver = CompanyDataResolver(ctx, rs)
    bar_item = str(tpl.bar_item or "").strip()
    line_field = str(tpl.line or "close").strip() or "close"
    if not bar_item:
        raise RuntimeError("合并模板缺少 bar_item")
    labels = [pe.strftime("%Y-%m-%d") for pe in periods]
    fin_values = [resolver.eval_expr(bar_item, current_pe=pe, default_statement=guess_statement_from_expr(bar_item)) for pe in periods]
    px_values = resolver.price_series(periods, field=line_field)
    df = pd.DataFrame({"period": labels, "financial": fin_values, line_field: px_values})
    fig, ax1 = plt.subplots(figsize=(10, 4.8))
    ax1.bar(df["period"], df["financial"], color="#4E79A7", alpha=0.8, label="financial")
    ax1.set_ylabel(tpl.y_label or "财务数值")
    ax2 = ax1.twinx()
    ax2.plot(df["period"], df[line_field], color="#E15759", marker="o", label=line_field)
    ax2.set_ylabel(line_field)
    ax1.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name}")
    ax1.tick_params(axis="x", rotation=30)
    ax1.grid(axis="y", alpha=0.25)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="merge", company=rs.name or rs.code6)


def serve_app(*, host: str, port: int, data_dir: Path, templates_dir: Path, category_config: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ctx = AppContext(repo_root=repo_root, data_dir=data_dir, templates_dir=templates_dir, category_config=category_config)
    handler = create_handler()
    httpd = WebServer((host, port), handler, ctx)
    print(f"finreport-web 已启动: http://{host}:{port}")
    print(f"data_dir={data_dir}")
    print(f"templates_dir={templates_dir}")
    print(f"category_config={category_config}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nfinreport-web 已停止")
    finally:
        httpd.server_close()
