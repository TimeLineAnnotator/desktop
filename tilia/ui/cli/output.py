from __future__ import annotations

import prettytable
import builtins


def print(message: str) -> None:
    """
    Prints message to user.
    """
    builtins.print(message)


def tabulate(headers: list[str], data: list[tuple[str, ...]]) -> None:
    """
    Outputs table to user using PrettyTable.
    """
    table = prettytable.PrettyTable()
    table.field_names = headers
    table.add_rows(data)
    print(str(table))
