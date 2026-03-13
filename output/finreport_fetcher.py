"""Shim to allow running `python -m finreport_fetcher ...` from the `output/` directory.

Why:
- Users sometimes `cd output` then run `python3 -m finreport_fetcher ...`.
- In that case, Python cannot find the package unless installed or PYTHONPATH is set.

This shim:
- Inserts repo root into sys.path (ahead of cwd)
- chdir to repo root so relative defaults behave as if run from the project root
- Delegates to the real Typer app

Note: If you have installed the package (`pip install -e .`), you don't need this.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    # output/finreport_fetcher.py -> repo_root/output/finreport_fetcher.py
    return Path(__file__).resolve().parents[1]


def main():
    root = _repo_root()

    # behave as if invoked from repo root
    os.chdir(root)

    # ensure package is importable and preferred over this shim
    sys.path.insert(0, str(root))

    from finreport_fetcher.cli import app

    app()


if __name__ == "__main__":
    main()
