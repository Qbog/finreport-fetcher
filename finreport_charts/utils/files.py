from __future__ import annotations

import re


def safe_slug(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_\-\.]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_") or "chart"
