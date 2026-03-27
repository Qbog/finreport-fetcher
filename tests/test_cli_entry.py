from __future__ import annotations

from finshared.cli_entry import prepare_default_command_argv


def test_prepare_default_command_argv_inserts_default_for_option_first():
    argv = ["finchart", "-c", "600547", "-s", "2015-01-01", "-e", "2025-12-31"]
    out = prepare_default_command_argv(argv, default_command="run", known_subcommands={"merge"})
    assert out == ["finchart", "run", "-c", "600547", "-s", "2015-01-01", "-e", "2025-12-31"]


def test_prepare_default_command_argv_keeps_explicit_subcommand():
    argv = ["finprice", "commodity", "-n", "黄金", "-s", "2024-01-01", "-e", "2024-03-31"]
    out = prepare_default_command_argv(argv, default_command="fetch", known_subcommands={"commodity"})
    assert out == argv


def test_prepare_default_command_argv_keeps_no_arg_invocation():
    argv = ["finfetch"]
    out = prepare_default_command_argv(argv, default_command="fetch")
    assert out == argv
