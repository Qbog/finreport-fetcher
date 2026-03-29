from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExprError(Exception):
    msg: str

    def __str__(self) -> str:  # pragma: no cover
        return self.msg


_TOKEN_RE = re.compile(
    r"\s*(?:(?P<num>(?:\d+\.\d+)|(?:\d+))|(?P<id>[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\.\u4e00-\u9fff]*)|(?P<op>[\+\-\*/\(\),]))"
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
FUNCTIONS = {"abs", "max", "min", "clip_pos", "ttm", "nz"}


def to_rpn(tokens: list[str]) -> list[str]:
    out: list[str] = []
    stack: list[str] = []

    # handle unary +/- by rewriting to 0 +/- x
    prev: str | None = None

    def is_op(t: str) -> bool:
        return t in {"+", "-", "*", "/"}

    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if t in FUNCTIONS and nxt == "(":
            stack.append(t)
        elif t == ",":
            while stack and stack[-1] != "(":
                out.append(stack.pop())
            if not stack:
                raise ExprError("函数参数分隔符位置错误")
        elif t == "(":
            stack.append(t)
        elif t == ")":
            while stack and stack[-1] != "(":
                out.append(stack.pop())
            if not stack or stack[-1] != "(":
                raise ExprError("括号不匹配")
            stack.pop()
            if stack and stack[-1] in FUNCTIONS:
                out.append(stack.pop())
        elif is_op(t):
            # unary
            if prev is None or prev in {"(", ",", "+", "-", "*", "/"}:
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

        if t in FUNCTIONS:
            if t in {"abs", "clip_pos"}:
                if not st:
                    raise ExprError("函数参数不完整")
                a = st.pop()
                if t == "abs":
                    st.append(abs(a))
                    continue
                if t == "clip_pos":
                    st.append(a if a > 0 else 0.0)
                    continue
            elif t in {"max", "min", "nz"}:
                a, b = pop2()
                if t == "max":
                    st.append(max(a, b))
                elif t == "min":
                    st.append(min(a, b))
                else:
                    st.append(a if a != 0 else b)
                continue
            raise ExprError(f"不支持的函数: {t}")

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
