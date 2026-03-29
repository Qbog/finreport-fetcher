from __future__ import annotations

from datetime import date
from pathlib import Path

from finreport_charts.cli import CommonOpts, ExpressionEvaluator, _resolve_symbol


def test_expression_evaluator_expands_ttm_sugar_for_financial_keys():
    rs = _resolve_symbol(code='600547', name=None)
    opts = CommonOpts(
        rs=rs,
        start=date(2015, 1, 1),
        end=date.today(),
        data_dir=Path('/root/.openclaw/workspace/a_share_finreport_fetcher/output'),
        out_dir=Path('/tmp'),
        provider='auto',
        statement_type='merged',
        pdf=False,
        tushare_token=None,
    )
    ev = ExpressionEvaluator(opts)
    v1 = ev.eval('ttm(cf.net_cash_from_ops)', current_pe=date(2025, 12, 31), default_statement='现金流量表')
    v2 = ev.eval('cf.net_cash_from_ops + cf.net_cash_from_ops.prev_year.q4 - cf.net_cash_from_ops.prev_year', current_pe=date(2025, 12, 31), default_statement='现金流量表')
    assert v1 == v2
