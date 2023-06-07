from tilia.ui.cli.common import Subparsers


def setup_parser(subparsers: Subparsers):
    run_subp = subparsers.add_parser("run")
    run_subp.add_argument("path")
    run_subp.set_defaults(func=run_script)


def run_script(self, namespace):
    with open(namespace.path, "r") as file:
        commands = file.read().splitlines()

    for command in commands:
        self.run(command.split(" "))
