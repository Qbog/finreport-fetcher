from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExprError(Exception):
    msg: str

    def __str__(self) -> str:  # pragma: no cover
        return self.msg


_TOKEN_RE = re.compile(
    r"\s*(?:(?P<num>(?:\d+\.\d+)|(?:\d+))|(?P<id>[A-Za-z_][A-Za-z0-9_\.]*)|(?P<op>[\+\-\*/\(\)]))"
)


def tokenize(expr: str) -> list[str]:
    s = (expr or "").strip()
    if not s:
        raise ExprError("空表达式")

    out: list[str] = []
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise ExprError(f"无法解析表达式(位置 {pos}): {s[pos:pos+20]}")
        pos = m.end()
        if m.group("num"):
            out.append(m.group("num"))
        elif m.group("id"):
            out.append(m.group("id"))
        else:
            out.append(m.group("op"))

    return out


_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


def to_rpn(tokens: list[str]) -> list[str]:
    out: list[str] = []
    stack: list[str] = []

    # handle unary +/- by rewriting to 0 +/- x
    prev: str | None = None

    def is_op(t: str) -> bool:
        return t in {"+", "-", "*", "/"}

    for t in tokens:
        if t == "(":
            stack.append(t)
        elif t == ")":
            while stack and stack[-1] != "(":
                out.append(stack.pop())
            if not stack or stack[-1] != "(":
                raise ExprError("括号不匹配")
            stack.pop()
        elif is_op(t):
            # unary
            if prev is None or prev in {"(", "+", "-", "*", "/"}:
                out.append("0")

            while stack and stack[-1] in _PRECEDENCE and _PRECEDENCE[stack[-1]] >= _PRECEDENCE[t]:
                out.append(stack.pop())
            stack.append(t)
        else:
            out.append(t)
        prev = t

    while stack:
        if stack[-1] in {"(", ")"}:
            raise ExprError("括号不匹配")
        out.append(stack.pop())

    return out


def eval_rpn(rpn: list[str], values: dict[str, float]) -> float:
    st: list[float] = []

    def pop2() -> tuple[float, float]:
        if len(st) < 2:
            raise ExprError("表达式不完整")
        b = st.pop()
        a = st.pop()
        return a, b

    for t in rpn:
        if t in {"+", "-", "*", "/"}:
            a, b = pop2()
            if t == "+":
                st.append(a + b)
            elif t == "-":
                st.append(a - b)
            elif t == "*":
                st.append(a * b)
            else:
                st.append(a / b)
            continue

        # number
        if re.fullmatch(r"\d+(?:\.\d+)?", t):
            st.append(float(t))
            continue

        # identifier
        if t not in values:
            raise ExprError(f"缺少变量: {t}")
        st.append(float(values[t]))

    if len(st) != 1:
        raise ExprError("表达式不完整")
    return float(st[0])


def eval_expr(expr: str, values: dict[str, float]) -> float:
    """Evaluate expression with identifiers like is.net_profit.

    Supported operators: + - * / and parentheses.
    """

    tokens = tokenize(expr)
    rpn = to_rpn(tokens)
    return eval_rpn(rpn, values)
