from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import Template
from finreport_fetcher.utils.symbols import ResolvedSymbol
from finreport_web.server import AppContext


def test_web_generate_reports_builds_matrix_payload(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    data_dir = repo_root / "output"
    data_dir.mkdir()
    templates_dir = repo_root / "templates"
    templates_dir.mkdir()
    category_config = repo_root / "config" / "company_categories.toml"
    category_config.parent.mkdir(parents=True, exist_ok=True)
    category_config.write_text("[categories.test]\nitems = [{ name = '深信服', code = '300454' }]\n", encoding="utf-8")

    ctx = AppContext(repo_root=repo_root, data_dir=data_dir, templates_dir=templates_dir, category_config=category_config)

    main_rs = ResolvedSymbol(code6="300454", ts_code="300454.SZ", market="SZ", name="深信服")
    other_rs = ResolvedSymbol(code6="002212", ts_code="002212.SZ", market="SZ", name="天融信")

    monkeypatch.setattr(ctx, "resolve_symbol_non_interactive", lambda company: main_rs)
    monkeypatch.setattr(ctx, "_category_symbols", lambda category_key: [main_rs, other_rs] if category_key else [])

    templates = [
        Template(name="income_trend", alias="收入趋势", type="bar", mode="trend"),
        Template(name="asset_structure", alias="资产结构", type="bar", mode="structure"),
        Template(name="revenue_peer", alias="收入对比", type="bar", mode="peer"),
    ]
    monkeypatch.setattr(ctx, "_select_templates", lambda selected: templates)

    def _fake_run(rs, tpl, *, start, end, out_dir, category_key, extra_args=None):
        time_key = None
        if extra_args and "--as-of" in extra_args:
            time_key = extra_args[extra_args.index("--as-of") + 1]
        else:
            time_key = end
        return ({
            "title": tpl.alias or tpl.name,
            "template": tpl.name,
            "label": tpl.alias or tpl.name,
            "company": rs.name,
            "code6": rs.code6,
            "image": f"/files/{tpl.name}_{rs.code6}_{time_key}.png",
            "xlsx": f"/files/{tpl.name}_{rs.code6}_{time_key}.xlsx",
            "filename": f"{tpl.name}_{rs.code6}_{time_key}.png",
            "mode": tpl.mode,
        }, None)

    monkeypatch.setattr(ctx, "_run_chart_cell", _fake_run)

    payload = ctx.generate_reports(
        {
            "company": "深信服",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "category": "test",
            "templates": ["收入趋势", "资产结构", "收入对比"],
        }
    )

    assert payload["company"]["code6"] == "300454"
    assert payload["sections"]["trend"]["templates"][0]["key"] == "income_trend"
    assert [x["code6"] for x in payload["sections"]["trend"]["companies"]] == ["300454", "002212"]
    assert payload["sections"]["trend"]["times"] == ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]
    assert payload["sections"]["trend"]["matrix"]["income_trend"]["002212"]["2024-12-31"]["image"].endswith("income_trend_002212_2024-12-31.png")
    assert payload["sections"]["structure"]["matrix"]["asset_structure"]["2024-06-30"]["image"].endswith("asset_structure_300454_2024-06-30.png")
    assert payload["sections"]["peer"]["matrix"]["revenue_peer"]["2024-09-30"]["image"].endswith("revenue_peer_300454_2024-09-30.png")
