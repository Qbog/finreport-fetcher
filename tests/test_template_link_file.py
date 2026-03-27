from __future__ import annotations

from pathlib import Path

from finreport_charts.templates.config import find_template_file, load_template_dir, load_template_file


def test_template_loader_supports_text_link_file(tmp_path: Path):
    root = tmp_path / "templates"
    root.mkdir()
    target = root / "nonfin-trend-revenue_total.toml"
    target.write_text(
        'name = "nonfin-trend-revenue_total"\nalias = "营业总收入"\ntype = "bar"\nmode = "trend"\n[[series]]\nexpr = "is.revenue_total"\n',
        encoding='utf-8',
    )
    alias = root / "非金融-趋势-营业总收入.toml"
    alias.write_text("nonfin-trend-revenue_total.toml\n", encoding='utf-8')

    tpl = load_template_file(alias, root=root)
    assert tpl.name == "nonfin-trend-revenue_total"
    assert find_template_file(root, "非金融-趋势-营业总收入.toml") == alias
    loaded = load_template_dir(root)
    assert set(loaded.keys()) == {"nonfin-trend-revenue_total"}
