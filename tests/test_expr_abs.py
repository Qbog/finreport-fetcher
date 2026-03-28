from __future__ import annotations

from finreport_charts.utils.expr import eval_expr, tokenize


def test_tokenize_supports_abs_function():
    assert tokenize("abs(px.close)") == ["abs", "(", "px.close", ")"]


def test_eval_expr_supports_abs_function():
    v = eval_expr("abs(a / b)", {"a": 10, "b": -2})
    assert v == 5.0
