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


def ask_for_string(prompt: str) -> str:
    """
    Prompts the user for a string
    """
    return input(prompt)


def ask_for_directory(prompt: str) -> str:
    """
    Prompts the user for a directory
    """
    return input(prompt)


def ask_yes_or_no(prompt: str) -> bool:
    """
    Prompts the user for a yes or no answer
    """
    return input(prompt + ' (y)es/(n)o: ').lower() in ['y', 'yes']
