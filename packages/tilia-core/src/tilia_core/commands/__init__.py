"""The `tilia` command, a dispatcher for subcommands that other packages provide.

A package adds a subcommand by registering an entry point in the group
`tilia.commands`, in its `pyproject.toml`:

    [project.entry-points."tilia.commands"]
    gui = "tilia.__main__:main"

The entry point's name is the subcommand (`tilia gui`) and its value names a
function that takes no arguments and reads `sys.argv`, like a console script.
When the subcommand runs, `sys.argv` is `[<script path>, *<arguments after the
subcommand>]`, so the function sees the same arguments as if it had been
started on its own. Its return value is the exit code (`None` means 0).

tilia-core's own subcommands are modules in this package, such as
`tilia_core.commands.migrate`, registered in the same group.
"""

import shlex
import sys
from importlib.metadata import EntryPoint, entry_points, version

GROUP = "tilia.commands"


def _installed_commands() -> dict[str, EntryPoint]:
    return {ep.name: ep for ep in entry_points(group=GROUP)}


def _print_help(commands: dict[str, EntryPoint]) -> int:
    print("usage: tilia <command> [arguments]")
    if commands:
        print("\ninstalled commands:")
        for name in sorted(commands):
            print(f"  {name}")
    else:
        print("\nNo commands are installed.")
    if "gui" in commands:
        print("\nTo open a file in TiLiA: tilia gui piece.tla")
    return 0


def _not_a_command(argv: list[str], commands: dict[str, EntryPoint]) -> int:
    # Temporary: `tilia piece.tla` used to open the GUI; point people to `tilia gui`.
    print(f"tilia: '{argv[0]}' is not a tilia command.", file=sys.stderr)
    if "gui" in commands:
        print(f'Did you mean "tilia gui {shlex.join(argv)}"?', file=sys.stderr)
    else:
        print("See 'tilia --help' for the installed commands.", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    commands = _installed_commands()

    if not argv or argv[0] in ("-h", "--help"):
        return _print_help(commands)
    if argv[0] == "--version":
        print(f"tilia-core {version('tilia-core')}")
        return 0
    if argv[0] not in commands:
        return _not_a_command(argv, commands)

    sys.argv = [sys.argv[0], *argv[1:]]
    result = commands[argv[0]].load()()
    return 0 if result is None else result
