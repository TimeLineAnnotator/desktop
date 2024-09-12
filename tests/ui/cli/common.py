from tilia.requests import stop_listening_to_all
from tilia.ui.cli.ui import CLI


def cli_run(input):
    cli = CLI()
    args = cli.parse_command(input)
    cli.run(args)
    stop_listening_to_all(cli)
