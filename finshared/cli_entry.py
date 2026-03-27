from __future__ import annotations

import sys
from collections.abc import Iterable


def prepare_default_command_argv(
    argv: list[str] | tuple[str, ...],
    *,
    default_command: str,
    known_subcommands: Iterable[str] = (),
) -> list[str]:
    out = list(argv)
    if len(out) <= 1:
        return out

    first = str(out[1] or '').strip()
    if not first:
        return out

    known = {str(x).strip() for x in known_subcommands if str(x).strip()}
    known.add(str(default_command).strip())

    if first in known:
        return out

    if first.startswith('-'):
        return [out[0], default_command, *out[1:]]

    return out


def run_typer_app_with_default_command(
    app,
    *,
    default_command: str,
    known_subcommands: Iterable[str] = (),
) -> None:
    sys.argv[:] = prepare_default_command_argv(
        sys.argv,
        default_command=default_command,
        known_subcommands=known_subcommands,
    )
    app()
