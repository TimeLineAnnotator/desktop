from __future__ import annotations
import traceback

import argparse

from tilia.ui.cli import timelines, output, run, quit


class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(exit_on_error=False)
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()

    def setup_parsers(self):
        timelines.setup_parser(self.subparsers)
        run.setup_parser(self.subparsers)
        quit.setup_parser(self.subparsers)

    def launch(self):
        """
        Launches the CLI.
        """
        print("--- TiLiA CLI v0.0 ---")
        while True:
            cmd = input(">>> ")
            self.run(cmd.split(" "))

    def run(self, cmd):
        """
        Parses the commands entered by the user.
        """
        try:
            namespace = self.parser.parse_args(cmd)
            if hasattr(namespace, "func"):
                namespace.func(namespace)
        except argparse.ArgumentError as err:
            output.print(err.message)
        except Exception:
            traceback.print_exc()



