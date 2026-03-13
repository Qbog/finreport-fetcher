from __future__ import annotations

import re


def safe_dir_component(s: str, *, max_len: int = 80) -> str:
    """Make a safe single path component.

    - Keeps Chinese/ASCII letters/numbers/underscore/dash/space
    - Replaces other chars (including / and \) with '_'
    """

    s2 = (s or "").strip()
    if not s2:
        return "unknown"

    # Replace path separators first
    s2 = s2.replace("/", "_").replace("\\", "_")

    # Remove other risky characters
    s2 = re.sub(r"[\:\*\?\"\<\>\|]", "_", s2)
    s2 = re.sub(r"\s+", " ", s2)
    s2 = re.sub(r"_+", "_", s2)

    s2 = s2.strip(" _.")
    if not s2:
        s2 = "unknown"

    if len(s2) > max_len:
        s2 = s2[:max_len].rstrip(" _.")

    return s2
