from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class StatementBundle:
    period_end: date
    statement_type: str  # merged|parent|unknown
    provider: str
    balance_sheet: pd.DataFrame
    income_statement: pd.DataFrame
    cashflow_statement: pd.DataFrame
    meta: dict


class Provider(Protocol):
    name: str

    def supports(self) -> bool:
        ...

    def get_bundle(self, ts_code: str, period_end: date, statement_type: str) -> StatementBundle:
        ...
