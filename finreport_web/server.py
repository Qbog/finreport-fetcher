from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from finreport_charts.templates.config import Template, load_template_dir, template_lookup_names
from finreport_charts.utils.files import safe_slug
from finreport_fetcher.utils.company_categories import load_company_categories
from finreport_fetcher.utils.paths import safe_dir_component
from finreport_fetcher.utils.symbols import ResolvedSymbol, fuzzy_match_name, load_a_share_name_map, parse_code


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
            mode = str(getattr(tpl, "mode", None) or "").strip().lower().replace("compare", "structure")
            if mode not in {"trend", "structure", "peer"}:
                continue
            label = str(getattr(tpl, "alias", None) or tpl.name)
            out.append(
                TemplateView(
                    key=tpl.name,
                    label=label,
                    names=template_lookup_names(tpl),
                    mode=mode,
                    type=str(tpl.type),
                )
            )
        order = {"trend": 0, "structure": 1, "peer": 2}
        out.sort(key=lambda x: (order.get(x.mode, 99), x.label))
        return out

    def bootstrap_payload(self) -> dict[str, Any]:
        config_text = self.category_config.read_text(encoding="utf-8") if self.category_config.exists() else ""
        return {
            "categories": self.load_categories_payload(),
            "templates": [
                {
                    "key": t.key,
                    "label": t.label,
                    "names": t.names,
                    "mode": t.mode,
                    "type": t.type,
                }
                for t in self.list_financial_templates()
            ],
            "configText": config_text,
            "dataDir": str(self.data_dir),
            "templatesDir": str(self.templates_dir),
        }

    def save_category_config(self, text: str) -> dict[str, Any]:
        self.category_config.parent.mkdir(parents=True, exist_ok=True)
        self.category_config.write_text(text, encoding="utf-8")
        cats = self.load_categories_payload()
        return {"ok": True, "categories": cats}

    def resolve_symbol_non_interactive(self, company: str) -> ResolvedSymbol:
        q = str(company or "").strip()
        if not q:
            raise ValueError("公司不能为空")

        rs = parse_code(q)
        if rs:
            try:
                df_map = load_a_share_name_map()
                m = df_map["code"].astype(str).str.zfill(6) == rs.code6
                if m.any():
                    nm = str(df_map[m].iloc[0]["name"])
                    return ResolvedSymbol(code6=rs.code6, ts_code=rs.ts_code, market=rs.market, name=nm)
            except Exception:
                pass
            return rs

        df_map = load_a_share_name_map()
        cand = fuzzy_match_name(df_map, q)
        if cand.empty:
            raise ValueError(f"未匹配到公司：{q}")
        c = cand.iloc[0]
        rs0 = parse_code(str(c["code"]))
        if not rs0:
            raise ValueError(f"无法解析公司代码：{c['code']}")
        return ResolvedSymbol(code6=rs0.code6, ts_code=rs0.ts_code, market=rs0.market, name=str(c["name"]))

    def build_company_root(self, rs: ResolvedSymbol) -> Path:
        return self.data_dir / safe_dir_component(f"{(rs.name or rs.code6)}_{rs.code6}")

    def _load_template_map(self) -> dict[str, Template]:
        return load_template_dir(self.templates_dir)

    def _select_templates(self, selected: list[str] | None) -> list[Template]:
        loaded = self._load_template_map()
        views = self.list_financial_templates()
        allowed = {v.key for v in views}
        if not selected:
            keys = [v.key for v in views]
            return [loaded[k] for k in keys if k in loaded]

        norm_map: dict[str, Template] = {}
        for tpl in loaded.values():
            if tpl.name not in allowed:
                continue
            for nm in template_lookup_names(tpl):
                norm_map[nm.strip().lower()] = tpl
            norm_map[tpl.name.strip().lower()] = tpl
            label = str(getattr(tpl, "alias", None) or tpl.name)
            norm_map[label.strip().lower()] = tpl

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

    def _peer_codes_from_category(self, category_key: str | None, self_code6: str) -> list[str]:
        if not category_key:
            return []
        cats = load_company_categories(self.category_config)
        cat = cats.get(category_key)
        if not cat:
            return []
        out: list[str] = []
        seen: set[str] = {self_code6}
        for it in cat.items:
            if it.code6 in seen:
                continue
            seen.add(it.code6)
            out.append(it.code6)
        return out

    def _run_chart_template(
        self,
        rs: ResolvedSymbol,
        tpl: Template,
        *,
        start: str,
        end: str,
        out_dir: Path,
        category_key: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = safe_slug(str(getattr(tpl, "alias", None) or tpl.name))

        args = [
            sys.executable,
            "-m",
            "finreport_charts",
            "run",
            "--code",
            rs.code6,
            "--start",
            start,
            "--end",
            end,
            "--data-dir",
            str(self.data_dir),
            "--templates",
            str(self.templates_dir),
            "--template",
            tpl.name,
            "--out",
            str(out_dir),
        ]

        mode = str(getattr(tpl, "mode", None) or "").strip().lower().replace("compare", "structure")
        if mode == "peer":
            for code6 in self._peer_codes_from_category(category_key, rs.code6):
                args.extend(["--peer", code6])

        env = os.environ.copy()
        py_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.repo_root) + (os.pathsep + py_path if py_path else "")

        proc = subprocess.run(
            args,
            cwd=str(self.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return [], {
                "template": tpl.name,
                "label": str(getattr(tpl, "alias", None) or tpl.name),
                "mode": mode,
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "").strip()[-2000:],
                "stdout": (proc.stdout or "").strip()[-2000:],
            }

        pngs = sorted(out_dir.glob(f"{prefix}_{rs.code6}_*.png"))
        items: list[dict[str, Any]] = []
        label = str(getattr(tpl, "alias", None) or tpl.name)
        for p in pngs:
            xlsx = p.with_suffix(".xlsx")
            items.append(
                {
                    "title": label,
                    "template": tpl.name,
                    "label": label,
                    "image": f"/files/{p.resolve().relative_to(self.repo_root.resolve()).as_posix()}",
                    "xlsx": f"/files/{xlsx.resolve().relative_to(self.repo_root.resolve()).as_posix()}" if xlsx.exists() else None,
                    "filename": p.name,
                    "mode": mode,
                }
            )
        return items, None

    def generate_reports(self, payload: dict[str, Any]) -> dict[str, Any]:
        company = str(payload.get("company") or "").strip()
        start = str(payload.get("start") or "").strip()
        end = str(payload.get("end") or "").strip()
        category_key = str(payload.get("category") or "").strip() or None
        selected_templates = payload.get("templates") if isinstance(payload.get("templates"), list) else None

        if not company:
            raise ValueError("公司不能为空")
        if not start or not end:
            raise ValueError("开始/结束日期不能为空")

        rs = self.resolve_symbol_non_interactive(company)
        templates = self._select_templates(selected_templates)
        if not templates:
            raise ValueError("未选中任何模板")

        company_root = self.build_company_root(rs)
        request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        web_out_dir = company_root / "charts" / "web" / request_id
        web_out_dir.mkdir(parents=True, exist_ok=True)

        sections: dict[str, list[dict[str, Any]]] = {"trend": [], "structure": [], "peer": []}
        errors: list[dict[str, Any]] = []

        for tpl in templates:
            items, err = self._run_chart_template(
                rs,
                tpl,
                start=start,
                end=end,
                out_dir=web_out_dir,
                category_key=category_key,
            )
            mode = str(getattr(tpl, "mode", None) or "").strip().lower().replace("compare", "structure")
            if err:
                errors.append(err)
                continue
            if not items:
                errors.append(
                    {
                        "template": tpl.name,
                        "label": str(getattr(tpl, "alias", None) or tpl.name),
                        "mode": mode,
                        "stderr": "模板执行成功，但未生成图片文件。",
                        "stdout": "",
                        "returncode": 0,
                    }
                )
                continue
            sections.setdefault(mode, []).append(
                {
                    "template": tpl.name,
                    "label": str(getattr(tpl, "alias", None) or tpl.name),
                    "items": items,
                }
            )

        return {
            "ok": True,
            "company": {"code6": rs.code6, "name": rs.name or rs.code6},
            "start": start,
            "end": end,
            "category": category_key,
            "reportDir": f"/files/{web_out_dir.resolve().relative_to(self.repo_root.resolve()).as_posix()}",
            "sections": sections,
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

    def _write_text(self, text: str, *, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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
            sys.stderr.write("[finreport-web] " + fmt % args + "\n")

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
            if path == "/api/generate":
                payload = self._read_json_body()
                result = self.server.ctx.generate_reports(payload)
                return self._write_json(result)
            if path == "/api/categories/save":
                payload = self._read_json_body()
                text = str(payload.get("text") or "")
                if not text.strip():
                    raise JsonHttpError(400, "配置内容不能为空")
                result = self.server.ctx.save_category_config(text)
                return self._write_json(result)

            raise JsonHttpError(404, f"未找到路径：{path}")

    return Handler


def serve_app(*, host: str, port: int, data_dir: Path, templates_dir: Path, category_config: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ctx = AppContext(
        repo_root=repo_root,
        data_dir=data_dir,
        templates_dir=templates_dir,
        category_config=category_config,
    )

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
