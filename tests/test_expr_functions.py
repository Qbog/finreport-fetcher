from __future__ import annotations

from finreport_charts.utils.expr import eval_expr


def test_eval_expr_supports_max_min_clip_pos():
    assert eval_expr("max(a, b)", {"a": 1, "b": 2}) == 2.0
    assert eval_expr("min(a, b)", {"a": 1, "b": 2}) == 1.0
    assert eval_expr("clip_pos(x)", {"x": -3}) == 0.0
    assert eval_expr("clip_pos(x)", {"x": 4}) == 4.0
