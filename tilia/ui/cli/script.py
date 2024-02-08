
from functools import partial
from typing import Callable


def setup_parser(
    subparsers, run_command: Callable[[str, None], None]
):
    run_subp = subparsers.add_parser("script")
    run_subp.add_argument("path", type=str, nargs="+")
    run_subp.set_defaults(func=partial(run, run_command))


def run(run_command, namespace):
    path = "".join(namespace.path)
    print(path)

    with open(path, "r") as file:
        commands = [line for line in file.read().splitlines() if line.strip()]

    print(commands)

    for command in commands:
        print(command)
        run_command(command.split(" "))
