from __future__ import annotations

import prettytable
from colorama import Fore


def output(message: str, color: Fore = None) -> None:
    """
    Prints message to user.
    """
    if color is not None:
        message = color + message
    print(message + Fore.RESET)


def tabulate(headers: list[str], data: list[tuple[str, ...]]) -> None:
    """
    Outputs table to user using PrettyTable.
    """
    table = prettytable.PrettyTable()
    table.field_names = headers
    table.add_rows(data)
    output(str(table))


def ask_for_string(prompt: str) -> str:
    """
    Prompts the user for a string
    """
    return input(prompt)


def ask_yes_or_no(prompt: str) -> bool:
    """
    Prompts the user for a yes or no answer
    """
    return input(prompt + " (y)es/(n)o: ").lower() in ["y", "yes"]
