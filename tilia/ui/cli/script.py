from functools import partial
from typing import Callable

from colorama import Fore

import tilia.errors
from tilia.ui.cli import io


def setup_parser(subparsers, parse_and_run_func: Callable[[str], bool]):
    script = subparsers.add_parser(
        "script", exit_on_error=False, help="Run a CLI script from a text file"
    )
    script.add_argument("path", type=str, help="Path to the script file")
    script.add_argument(
        "--encoding", "-e", type=str, nargs="?", default="utf-8", help="File encoding"
    )
    script.set_defaults(func=partial(run, parse_and_run_func))


def split_commands(text: str) -> list[str]:
    """
    Splits text into commands, separated by newlines or by ";".
    Separators inside double quotes don't count. Empty commands and comments
    (starting with "#") are dropped.
    """
    commands = []
    current = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
        if char in ";\n" and not in_quotes:
            commands.append("".join(current))
            current = []
        else:
            current.append(char)
    commands.append("".join(current))

    commands = [cmd.strip() for cmd in commands]
    return [cmd for cmd in commands if cmd and not cmd.startswith("#")]


def run(parse_and_run_func, namespace):
    with open(namespace.path, "r", encoding=namespace.encoding) as file:
        commands = split_commands(file.read())

    if not commands:
        tilia.errors.display(tilia.errors.EMPTY_CLI_SCRIPT, namespace.path)
        return

    for cmd in commands:
        io.output(cmd, Fore.GREEN)
        error = parse_and_run_func(cmd)
        if error:
            return
