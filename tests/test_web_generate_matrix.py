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

    monkeypatch.setattr(ctx, "_category_symbols", lambda category_key: [main_rs, other_rs] if category_key else [])
    templates = [
        Template(name="income_trend", alias="收入趋势", type="bar", mode="trend"),
        Template(name="asset_structure", alias="资产结构", type="bar", mode="structure"),
        Template(name="revenue_peer", alias="收入对比", type="bar", mode="peer"),
        Template(name="combo_view", alias="合并视图", type="combo", mode="merge"),
    ]
    monkeypatch.setattr(ctx, "_select_templates", lambda selected: templates)

    monkeypatch.setattr("finreport_web.server.build_trend_chart", lambda *args, **kwargs: {"image": "/files/trend.png", "xlsx": "/files/trend.xlsx", "title": "收入趋势"})
    monkeypatch.setattr("finreport_web.server.build_structure_chart", lambda *args, **kwargs: {"image": "/files/structure.png", "xlsx": "/files/structure.xlsx", "title": "资产结构"})
    monkeypatch.setattr("finreport_web.server.build_peer_chart", lambda *args, **kwargs: {"image": "/files/peer.png", "xlsx": "/files/peer.xlsx", "title": "收入对比"})
    monkeypatch.setattr("finreport_web.server.build_merge_chart", lambda *args, **kwargs: {"image": "/files/merge.png", "xlsx": "/files/merge.xlsx", "title": "合并视图"})

    payload = ctx.generate_reports({"category": "test", "start": "2024-01-01", "end": "2024-12-31", "templates": ["收入趋势", "资产结构", "收入对比", "合并视图"]})

    assert [x["code6"] for x in payload["sections"]["trend"]["companies"]] == ["300454", "002212"]
    assert payload["sections"]["trend"]["matrix"]["income_trend"]["300454"]["image"].endswith("trend.png")
    assert payload["sections"]["structure"]["times"] == ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]
    assert payload["sections"]["structure"]["matrix"]["asset_structure"]["002212"]["2024-06-30"]["image"].endswith("structure.png")
    assert payload["sections"]["peer"]["matrix"]["revenue_peer"]["2024-09-30"]["image"].endswith("peer.png")
    assert payload["sections"]["merge"]["matrix"]["combo_view"]["002212"]["image"].endswith("merge.png")
