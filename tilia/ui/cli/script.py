from functools import partial
from typing import Callable

from colorama import Fore

import tilia.errors
from tilia.ui.cli import io


def setup_parser(subparsers, parse_and_run_func: Callable[[str], bool]):
    script = subparsers.add_parser("script", exit_on_error=False)
    script.add_argument("path", type=str)
    script.set_defaults(func=partial(run, parse_and_run_func))


def run(parse_and_run_func, namespace):
    with open(namespace.path, "r") as file:
        commands = [line for line in file.read().splitlines() if line.strip()]

    if not commands:
        tilia.errors.display(tilia.errors.EMPTY_CLI_SCRIPT, namespace.path)
        return

    for cmd in commands:
        io.output(cmd, Fore.GREEN)
        error = parse_and_run_func(cmd)
        if error:
            return
