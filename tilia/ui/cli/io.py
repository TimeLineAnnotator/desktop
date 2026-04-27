from __future__ import annotations

import os

import prettytable
from colorama import Fore


def output(message: str, color: Fore = None) -> None:
    """
    Prints message to user.
    """
    if color is not None:
        message = color + message
    print(message + Fore.RESET)


def tabulate(headers: list[str], data: list[tuple[str, ...]], **kwargs) -> None:
    """
    Outputs table to user using PrettyTable.
    """
    try:
        table_width = min(os.get_terminal_size().columns, 88)
    except OSError:
        table_width = 88
    table = prettytable.PrettyTable(max_table_width=table_width, **kwargs)
    table.field_names = headers
    table.add_rows(data)
    output(str(table))


def warn(message: str) -> None:
    output(message, Fore.YELLOW)


def error(message: str) -> None:
    output(message, Fore.RED)


def ask_for_string(prompt: str) -> str:
    """
    Prompts the user for a string
    """
    return input(prompt)


def ask_yes_or_no(prompt: str, default: bool = True) -> bool:
    """
    Prompts the user for a yes or no answer.
    Returns `default` if answer is an empty string.
    """
    yes_no = {True: "yes", False: "no"}
    valid_answers = {x for v in yes_no.values() for x in (v, v[0])}.union({""})
    option = "/".join(
        [v.capitalize() if k == default else v for k, v in yes_no.items()]
    )
    while (ans := input(f"{prompt} [{option}]: ").lower()) not in valid_answers:
        pass
    if ans == "":
        return default
    else:
        return [k for k, v in yes_no.items() if ans[0] == v[0]][0]
