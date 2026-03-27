from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
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
from finreport_charts.templates.config import BarBlock, Template, list_template_categories, load_template_dir, template_filename, template_lookup_names
from finreport_charts.utils.expr import ExprError, eval_expr, tokenize
from finreport_charts.utils.mpl_style import apply_pretty_style
from finshared.global_datasets import load_company_basics_csv
from finshared.company_categories import CompanyCategory, CompanyCategoryItem, load_company_categories, resolve_company_category_symbols
from finshared.global_series import global_series_value_on_or_before, load_global_series_csv, parse_global_series_ident, resolve_global_series_csv
from finreport_fetcher.utils.dates import parse_date, quarter_ends_between
from finreport_fetcher.utils.paths import safe_dir_component
from finshared.symbols import ResolvedSymbol, load_a_share_name_map, parse_code


_ID_DATE_SUFFIX = re.compile(r"^(?P<id>.+?)\.(?P<y>\d{4})\.(?P<m>\d{2})\.(?P<d>\d{2})$")


@dataclass(frozen=True)
class TemplateView:
    key: str
    label: str
    names: list[str]
    mode: str
    type: str
    category: str | None = None
    categoryAlias: str | None = None
    categoryPath: str | None = None


@dataclass
class RawTask:
    task_id: str
    label: str
    category: str
    kind: str
    action: str
    args: list[str]
    status: str = "running"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)


@dataclass
class AppContext:
    repo_root: Path
    data_dir: Path
    templates_dir: Path
    category_config: Path

    def __post_init__(self) -> None:
        self._raw_tasks: dict[str, RawTask] = {}
        self._raw_tasks_lock = threading.Lock()

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
        files = sorted(self.data_dir.glob("*_*/metrics/*_financial_metrics.csv"))
        if not files:
            return {"rows": 0, "companies": 0}
        rows = 0
        companies = 0
        for p in files:
            try:
                df = pd.read_csv(p)
                rows += int(len(df.index))
                companies += 1
            except Exception:
                continue
        return {"rows": rows, "companies": companies}

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
            out.append(
                TemplateView(
                    key=tpl.name,
                    label=label,
                    names=template_lookup_names(tpl),
                    mode=mode,
                    type=str(tpl.type),
                    category=getattr(tpl, 'category', None),
                    categoryAlias=getattr(tpl, 'category_alias', None),
                    categoryPath=getattr(tpl, 'category_path', None),
                )
            )
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
                {"key": t.key, "label": t.label, "names": t.names, "mode": t.mode, "type": t.type, "category": t.category, "categoryAlias": t.categoryAlias, "categoryPath": t.categoryPath}
                for t in self.list_financial_templates()
            ],
            "templateCategories": list_template_categories(self.templates_dir),
            "rawTasks": self.list_raw_tasks(limit=5),
            "configText": config_text,
            "dataDir": str(self.data_dir),
            "templatesDir": str(self.templates_dir),
        }

    def _raw_task_payload(self, task: RawTask) -> dict[str, Any]:
        return {
            "taskId": task.task_id,
            "label": task.label,
            "category": task.category,
            "kind": task.kind,
            "action": task.action,
            "status": task.status,
            "startedAt": task.started_at,
            "finishedAt": task.finished_at,
            "returncode": task.returncode,
            "logText": "\n".join(task.logs[-400:]),
            "logLines": task.logs[-400:],
        }

    def list_raw_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._raw_tasks_lock:
            tasks = list(self._raw_tasks.values())
        tasks.sort(key=lambda t: t.started_at, reverse=True)
        return [self._raw_task_payload(t) for t in tasks[:limit]]

    def get_raw_task(self, task_id: str) -> dict[str, Any]:
        with self._raw_tasks_lock:
            task = self._raw_tasks.get(task_id)
        if task is None:
            raise ValueError(f"未找到 raw 任务：{task_id}")
        return self._raw_task_payload(task)

    def _append_raw_task_log(self, task_id: str, line: str) -> None:
        text = str(line or "").rstrip("\n")
        if not text:
            return
        with self._raw_tasks_lock:
            task = self._raw_tasks.get(task_id)
            if task is None:
                return
            task.logs.append(text)
            if len(task.logs) > 800:
                task.logs[:] = task.logs[-800:]

    def _build_exec_env(self) -> dict[str, str]:
        env = os.environ.copy()
        py_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.repo_root) + (os.pathsep + py_path if py_path else "")
        return env

    def _run_raw_task(self, task_id: str) -> None:
        with self._raw_tasks_lock:
            task = self._raw_tasks.get(task_id)
        if task is None:
            return
        try:
            proc = subprocess.Popen(
                task.args,
                cwd=str(self.repo_root),
                env=self._build_exec_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append_raw_task_log(task_id, line)
            proc.wait()
            with self._raw_tasks_lock:
                cur = self._raw_tasks.get(task_id)
                if cur is not None:
                    cur.returncode = proc.returncode
                    cur.status = "success" if proc.returncode == 0 else "failed"
                    cur.finished_at = datetime.now().isoformat(timespec="seconds")
                    if proc.returncode == 0 and not cur.logs:
                        cur.logs.append("任务完成，没有额外日志输出。")
        except Exception as exc:  # noqa: BLE001
            with self._raw_tasks_lock:
                cur = self._raw_tasks.get(task_id)
                if cur is not None:
                    cur.status = "failed"
                    cur.finished_at = datetime.now().isoformat(timespec="seconds")
                    cur.logs.append(f"任务异常：{exc}")

    def _start_raw_task(self, *, label: str, category: str, kind: str, action: str, args: list[str]) -> dict[str, Any]:
        task = RawTask(task_id=uuid.uuid4().hex[:12], label=label, category=category, kind=kind, action=action, args=args)
        with self._raw_tasks_lock:
            self._raw_tasks[task.task_id] = task
        thread = threading.Thread(target=self._run_raw_task, args=(task.task_id,), daemon=True)
        thread.start()
        return self._raw_task_payload(task)

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
            refs_raw = payload.get('refs') or []
            refs: list[str] = []
            if isinstance(refs_raw, list):
                refs.extend([str(x).strip() for x in refs_raw if str(x).strip()])
            if expr:
                refs.extend([x.strip() for x in re.split(r'[\n,]+', expr) if x.strip()])
            if not refs:
                for x in [payload.get('barItem'), payload.get('line')]:
                    s = str(x or '').strip()
                    if s:
                        refs.append(s)
            if not refs:
                raise ValueError('merge 模板至少需要一个引用模板名')
            content = build_combo_template_text(key=key, alias=alias, refs=refs)
        else:
            content = build_bar_template_text(key=key, alias=alias, mode=mode, expr=expr)
        path = self.templates_dir / template_filename(key, alias)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "templates": [
            {"key": t.key, "label": t.label, "names": t.names, "mode": t.mode, "type": t.type}
            for t in self.list_financial_templates()
        ], "created": key, "filename": path.name}

    def _load_template_map(self) -> dict[str, Template]:
        return load_template_dir(self.templates_dir)

    def _select_templates(self, selected: list[str] | None) -> list[Template]:
        loaded = self._load_template_map()
        views = self.list_financial_templates()
        allowed = {v.key for v in views}
        if not selected:
            return [loaded[v.key] for v in views if v.key in loaded]
        norm_map: dict[str, Template] = {}
        cat_map: dict[str, list[Template]] = {}
        for tpl in loaded.values():
            if tpl.name not in allowed:
                continue
            for nm in template_lookup_names(tpl):
                norm_map[nm.strip().lower()] = tpl
            norm_map[tpl.name.strip().lower()] = tpl
            norm_map[str(getattr(tpl, "alias", None) or tpl.name).strip().lower()] = tpl
            for ck in category_lookup_names(getattr(tpl, 'category', None), getattr(tpl, 'category_alias', None), Path(str(getattr(tpl, 'category_path', '') or '')).name or None):
                cat_map.setdefault(ck.strip().lower(), []).append(tpl)
        out: list[Template] = []
        seen: set[str] = set()
        for raw in selected:
            key = str(raw or "").strip().lower()
            if not key:
                continue
            if key in cat_map:
                for tpl in cat_map[key]:
                    if tpl.name in seen:
                        continue
                    seen.add(tpl.name)
                    out.append(tpl)
                continue
            tpl = norm_map.get(key)
            if not tpl:
                raise ValueError(f"未找到模板或模板分类：{raw}")
            if tpl.name in seen:
                continue
            seen.add(tpl.name)
            out.append(tpl)
        return out

    def _category_symbols(self, category_key: str | None) -> list[ResolvedSymbol]:
        if not category_key:
            return []
        try:
            resolved = resolve_company_category_symbols(category_key, self.category_config)
        except Exception:
            return []
        return resolved.symbols

    def _run_fetcher(self, args: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(
            args,
            cwd=str(self.repo_root),
            env=self._build_exec_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def ensure_finreport_ready(self, rs: ResolvedSymbol, pe: date) -> None:
        xlsx = expected_xlsx_path(self.data_dir, rs.code6, "merged", pe, name=rs.name)
        if xlsx.exists():
            return
        rc, out, err = self._run_fetcher([
            sys.executable,
            "-m",
            "finreport_fetcher",
            "fetch",
            "--code",
            rs.code6,
            "--start",
            pe.strftime("%Y-%m-%d"),
            "--end",
            pe.strftime("%Y-%m-%d"),
            "--out",
            str(self.data_dir),
            "--no-clean",
        ])
        if rc != 0:
            raise RuntimeError(f"自动补抓财报失败：{rs.code6} {pe.strftime('%Y-%m-%d')}\n{(err or out).strip()[-1200:]}")
        xlsx = expected_xlsx_path(self.data_dir, rs.code6, "merged", pe, name=rs.name)
        if not xlsx.exists():
            raise FileNotFoundError(f"自动补抓后仍缺少财报文件：{xlsx}")

    def ensure_price_ready(self, rs: ResolvedSymbol, start: date, end: date) -> None:
        company_dir = self.data_dir / f"{safe_dir_component((rs.name or rs.code6) + '_' + rs.code6)}" / "price"
        cand = company_dir / f"{rs.code6}.csv"
        if cand.exists():
            return
        rc, out, err = self._run_fetcher([
            sys.executable,
            "-m",
            "finprice_fetcher",
            "fetch",
            "--code",
            rs.code6,
            "--start",
            start.strftime("%Y-%m-%d"),
            "--end",
            end.strftime("%Y-%m-%d"),
            "--out",
            str(self.data_dir),
        ])
        if rc != 0:
            raise RuntimeError(f"自动补抓股价失败：{rs.code6}\n{(err or out).strip()[-1200:]}")
        if not cand.exists():
            raise FileNotFoundError(f"自动补抓后仍缺少股价 CSV：{cand}")

    def manage_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        category_key = str(payload.get("category") or "").strip() or None
        kind = str(payload.get("kind") or "").strip().lower()
        action = str(payload.get("action") or "").strip().lower()
        if not category_key:
            raise ValueError("公司类别不能为空")
        if kind not in {"report", "price"}:
            raise ValueError("kind 仅支持 report/price")
        if action not in {"update", "clear"}:
            raise ValueError("action 仅支持 update/clear")

        args = [sys.executable, "-m", "finreport_fetcher" if kind == "report" else "finprice_fetcher", "fetch", "--category", category_key, "--category-config", str(self.category_config), "--out", str(self.data_dir)]
        args.append("--update-raw" if action == "update" else "--clear-raw")
        label = f"{'财报' if kind == 'report' else '股价'} raw{'更新' if action == 'update' else '清理'}"
        task = self._start_raw_task(label=label, category=category_key, kind=kind, action=action, args=args)
        return {"ok": True, "message": f"已启动：{label}（{category_key}）", "task": task}

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
        run_root = self.data_dir / "global" / "web_runs" / request_id
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
            if path == "/api/raw/tasks":
                return self._write_json({"ok": True, "tasks": self.server.ctx.list_raw_tasks(limit=10)})
            if path.startswith("/api/raw/tasks/"):
                task_id = path.removeprefix("/api/raw/tasks/").strip()
                return self._write_json({"ok": True, "task": self.server.ctx.get_raw_task(task_id)})
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
            if path == "/api/raw/manage":
                return self._write_json(self.server.ctx.manage_raw(payload))
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
            if item.name and item.code6:
                lines.append(f'  {{ name = "{item.name}", code = "{item.code6}" }},')
            elif item.name:
                lines.append(f'  {{ name = "{item.name}" }},')
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
    if ss.startswith(("metrics.", "metric.", "mt.")):
        return "财报指标"
    return "利润表"


def build_bar_template_text(*, key: str, alias: str, mode: str, expr: str) -> str:
    title = alias + ("趋势" if mode == "trend" else "分析")
    return f'''name = "{key}"
alias = "{alias}"

type = "bar"
mode = "{mode}"

title = "{title}"
x_label = "{'报告期' if mode == 'trend' else '科目'}"
y_label = "数值"

[[series]]
name = "{alias}"
expr = "{expr}"
'''


def build_combo_template_text(*, key: str, alias: str, refs: list[str]) -> str:
    lines = [
        f'name = "{key}"',
        f'alias = "{alias}"',
        '',
        'type = "combo"',
        'mode = "merge"',
        '',
        f'title = "{alias}（统一合并）"',
        'x_label = "报告期"',
        'y_label = "数值"',
        '',
    ]
    for ref in refs:
        lines.extend([
            '[[series]]',
            f'expr = "{ref}"',
            '',
        ])
    return "\n".join(lines).rstrip() + "\n"


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


def quarter_end_for_q(year: int, q: int) -> date:
    if q == 1:
        return date(year, 3, 31)
    if q == 2:
        return date(year, 6, 30)
    if q == 3:
        return date(year, 9, 30)
    return date(year, 12, 31)


def prev_year_same_quarter_end(pe: date) -> date:
    pe0 = latest_quarter_end_on_or_before(pe)
    mmdd = pe0.strftime("%m%d")
    q = {"0331": 1, "0630": 2, "0930": 3, "1231": 4}.get(mmdd, 4)
    return quarter_end_for_q(pe0.year - 1, q)


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
    if k2.startswith(("metrics.", "metric.", "mt.")):
        return "财报指标"
    return default_statement


class CompanyDataResolver:
    def __init__(self, ctx: AppContext, rs: ResolvedSymbol):
        self.ctx = ctx
        self.rs = rs
        self._sheet_cache: dict[tuple[date, str], pd.DataFrame] = {}
        self._price_cache: pd.DataFrame | None = None
        self._global_series_cache: dict[tuple[str, str], pd.DataFrame] = {}

    def xlsx_for(self, pe: date) -> Path:
        xlsx = expected_xlsx_path(self.ctx.data_dir, self.rs.code6, "merged", pe, name=self.rs.name)
        if not xlsx.exists():
            self.ctx.ensure_finreport_ready(self.rs, pe)
            xlsx = expected_xlsx_path(self.ctx.data_dir, self.rs.code6, "merged", pe, name=self.rs.name)
        return xlsx

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
        prev_year_same_q = False
        prev_year_fixed_q: int | None = None
        m_prev_year_q = re.search(r"\.prev_year\.q([1-4])$", ident_s)
        if m_prev_year_q:
            prev_year_fixed_q = int(m_prev_year_q.group(1))
            ident_s = ident_s[: m_prev_year_q.start()]
        elif ident_s.endswith(".prev_year"):
            prev_year_same_q = True
            ident_s = ident_s[: -len(".prev_year")]
        elif ident_s.endswith(".prev_in_year"):
            prev_in_year = True
            ident_s = ident_s[: -len(".prev_in_year")]
        prev_n = 0
        while ident_s.endswith(".prev"):
            prev_n += 1
            ident_s = ident_s[: -len(".prev")]
        base, specified_date = split_id_date(ident_s)
        if base.startswith("metric."):
            base = "metrics." + base.split(".", 1)[1]
        elif base.startswith("mt."):
            base = "metrics." + base.split(".", 1)[1]
        statement = statement_from_key(base, default_statement)
        target_pe = latest_quarter_end_on_or_before(specified_date) if specified_date else current_pe
        if prev_year_fixed_q is not None:
            pe0 = latest_quarter_end_on_or_before(target_pe)
            target_pe = quarter_end_for_q(pe0.year - 1, prev_year_fixed_q)
        elif prev_year_same_q:
            target_pe = prev_year_same_quarter_end(target_pe)
        elif prev_in_year:
            prev_pe = prev_in_year_quarter_end(target_pe)
            if prev_pe is None:
                return 0.0
            target_pe = prev_pe
        for _ in range(prev_n):
            target_pe = prev_quarter_end(target_pe)

        if base.startswith(("px.", "price.")):
            field = base.split(".", 1)[1]
            return self._price_value_on_or_before(target_pe, field)

        parsed_global = parse_global_series_ident(base)
        if parsed_global is not None:
            kind, symbol, field = parsed_global
            return self._global_series_value_on_or_before(kind, symbol, target_pe, field)

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
            # 股价默认补到最近两年，足够当前 Web 趋势/合并分析使用。
            self.ctx.ensure_price_ready(self.rs, date(date.today().year - 2, 1, 1), date.today())
            candidates = list((self.ctx.data_dir / f"{safe_dir_component((self.rs.name or self.rs.code6) + '_' + self.rs.code6)}" / "price").glob(f"{self.rs.code6}*.csv"))
            if not candidates:
                company_matches = list(self.ctx.data_dir.glob(f"*_{self.rs.code6}/price/{self.rs.code6}*.csv"))
                candidates = sorted(company_matches)
        if not candidates:
            raise FileNotFoundError(f"缺少股价 CSV：{self.rs.code6}")
        self._price_cache = load_price_csv(candidates[0])
        return self._price_cache

    def _price_value_on_or_before(self, when: date, field: str) -> float | None:
        df = self.load_price()
        if field not in df.columns:
            return None
        sub = df[df["date"] <= when]
        if sub.empty:
            return None
        val = sub.iloc[-1][field]
        return None if pd.isna(val) else float(val)

    def _global_series_value_on_or_before(self, kind: str, symbol: str, when: date, field: str) -> float | None:
        key = (kind, symbol)
        if key not in self._global_series_cache:
            path = resolve_global_series_csv(self.ctx.data_dir, kind, symbol)
            if path is None or not path.exists():
                self._global_series_cache[key] = pd.DataFrame(columns=["date"])
            else:
                try:
                    self._global_series_cache[key] = load_global_series_csv(path)
                except Exception:
                    self._global_series_cache[key] = pd.DataFrame(columns=["date"])
        return global_series_value_on_or_before(self._global_series_cache[key], when, field)

    def price_series(self, periods: list[date], field: str = "close") -> list[float | None]:
        return [self._price_value_on_or_before(pe, field) for pe in periods]


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
    bars = flatten_bars(tpl.series)
    if not bars:
        raise RuntimeError("趋势模板缺少 bars")
    labels = [pe.strftime("%Y-%m-%d") for pe in periods]
    data = {"period": labels}
    for bar in bars:
        values = []
        for pe in periods:
            values.append(resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or guess_statement_from_expr(str(bar["expr"])))))
        data[bar["name"]] = values
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x_vals = df["period"].tolist()
    for bar in bars:
        ax.plot(x_vals, df[bar["name"]].tolist(), marker="o", label=bar["name"])
    ax.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name}")
    ax.set_xlabel(tpl.x_label or "报告期")
    ax.set_ylabel(tpl.y_label or "数值")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate(rotation=30)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="trend", company=rs.name or rs.code6)


def build_structure_chart(ctx: AppContext, tpl: Template, rs: ResolvedSymbol, pe: date, out_dir: Path) -> dict[str, Any] | None:
    resolver = CompanyDataResolver(ctx, rs)
    bars = flatten_bars(tpl.series)
    if not bars:
        raise RuntimeError("结构模板缺少 bars")
    rows = []
    for bar in bars:
        rows.append({"item": bar["name"], "value": resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or guess_statement_from_expr(str(bar["expr"]))))})
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(df["item"].tolist(), df["value"].tolist(), color="#4E79A7")
    ax.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name} · {pe.strftime('%Y-%m-%d')}")
    ax.set_xlabel(tpl.x_label or "科目")
    ax.set_ylabel(tpl.y_label or "数值")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.25)
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}_{pe.strftime('%Y%m%d')}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode="structure", company=rs.name or rs.code6)


def build_peer_chart(ctx: AppContext, tpl: Template, companies: list[ResolvedSymbol], pe: date, out_dir: Path) -> dict[str, Any] | None:
    bars = flatten_bars(tpl.series)
    if not bars:
        raise RuntimeError("同业模板缺少 bars")
    rows: list[dict[str, Any]] = []
    for comp in companies:
        resolver = CompanyDataResolver(ctx, comp)
        row = {"company": comp.name or comp.code6}
        for bar in bars:
            row[bar["name"]] = resolver.eval_expr(bar["expr"], current_pe=pe, default_statement=str(bar.get("statement") or guess_statement_from_expr(str(bar["expr"]))))
        rows.append(row)
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    if len(bars) == 1:
        ax.bar(df["company"].tolist(), df[bars[0]["name"]].tolist(), color="#4E79A7")
    else:
        base = range(len(df.index))
        width = 0.8 / max(len(bars), 1)
        for idx, bar in enumerate(bars):
            pos = [x + idx * width for x in base]
            ax.bar(pos, df[bar["name"]].tolist(), width=width, label=bar["name"])
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
    loaded = ctx._load_template_map()

    def _lookup_template(spec: str) -> Template | None:
        key = str(spec or '').strip().lower()
        if not key:
            return None
        for t in loaded.values():
            if t.name.strip().lower() == key:
                return t
            for nm in template_lookup_names(t):
                if nm.strip().lower() == key:
                    return t
        return None

    merge_defs: list[dict[str, Any]] = []
    blocks = flatten_bars(tpl.series)
    if blocks:
        for blk in blocks:
            ref_tpl = _lookup_template(str(blk['expr']))
            if ref_tpl is None:
                raise RuntimeError(f"merge 模式引用模板不存在: {blk['expr']}")
            ref_type = str(getattr(ref_tpl, 'type', '')).strip().lower()
            ref_mode = normalize_mode(getattr(ref_tpl, 'mode', None), type_=ref_type)
            if ref_type not in {'bar', 'line'} or ref_mode not in {'trend', 'price'}:
                raise RuntimeError(f"merge 仅支持引用 trend/price 的 bar/line 模板: {blk['expr']}")
            ref_blocks = flatten_bars(ref_tpl.series)
            if not ref_blocks:
                raise RuntimeError(f"被引用模板缺少 [[series]]: {blk['expr']}")
            prefix = str(blk.get('name') or '').strip()
            for item in ref_blocks:
                nm = str(item['name'])
                if prefix:
                    nm = f"{prefix}/{nm}"
                merge_defs.append({
                    'name': nm,
                    'expr': str(item['expr']),
                    'kind': ref_type,
                    'color': item.get('color'),
                })
    else:
        # legacy fallback
        bar_item = str(tpl.bar_item or '').strip() or 'is.revenue_total'
        line_expr = str(tpl.line or 'px.close').strip() or 'px.close'
        merge_defs = [
            {'name': 'financial', 'expr': bar_item, 'kind': 'bar', 'color': '#4E79A7'},
            {'name': line_expr.split('.')[-1] if '.' in line_expr else line_expr, 'expr': line_expr, 'kind': 'line', 'color': '#E15759'},
        ]

    labels = [pe.strftime('%Y-%m-%d') for pe in periods]
    rows = []
    for pe in periods:
        row = {'period': pe.strftime('%Y-%m-%d')}
        for item in merge_defs:
            row[item['name']] = resolver.eval_expr(str(item['expr']), current_pe=pe, default_statement=guess_statement_from_expr(str(item['expr'])))
        rows.append(row)
    df = pd.DataFrame(rows)
    apply_pretty_style()
    fig, ax1 = plt.subplots(figsize=(10, 4.8))
    x_pos = list(range(len(df.index)))
    bar_defs = [x for x in merge_defs if x['kind'] == 'bar']
    line_defs = [x for x in merge_defs if x['kind'] == 'line']
    if bar_defs:
        width = 0.8 / max(len(bar_defs), 1)
        start = -width * (len(bar_defs) - 1) / 2
        for idx, item in enumerate(bar_defs):
            pos = [x + start + idx * width for x in x_pos]
            ax1.bar(pos, pd.to_numeric(df[item['name']], errors='coerce').tolist(), width=width, color=item.get('color') or None, alpha=0.82, label=item['name'])
    ax1.set_ylabel(tpl.y_label or '数值')
    ax2 = ax1.twinx()
    for item in line_defs:
        ax2.plot(x_pos, pd.to_numeric(df[item['name']], errors='coerce').tolist(), color=item.get('color') or None, marker='o', label=item['name'])
    ax1.set_xticks(x_pos, labels)
    ax1.set_title(f"{rs.name or rs.code6} · {tpl.alias or tpl.name}")
    ax1.tick_params(axis='x', rotation=30)
    ax1.grid(axis='y', alpha=0.25)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    if h1 or h2:
        ax1.legend(h1 + h2, l1 + l2, loc='best')
    return save_plot_with_excel(fig, df, out_dir=out_dir, stem=f"{tpl.name}_{rs.code6}", repo_root=ctx.repo_root, title=str(tpl.alias or tpl.name), mode='merge', company=rs.name or rs.code6)


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
