from __future__ import annotations
import sys
import traceback

import argparse

from tilia.ui.cli import timelines, output


class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(exit_on_error=False)
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()

    def setup_parsers(self):
        timelines.setup_parser(self.subparsers)
        self.setup_quit_parser()
        self.setup_run_parser()

    def setup_quit_parser(self):
        _quit = self.subparsers.add_parser("quit")
        _quit.set_defaults(func=quit)

    def setup_run_parser(self):
        run = self.subparsers.add_parser("run")
        run.add_argument("path")
        run.set_defaults(func=self.run_script)

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


    def run_script(self, namespace):
        with open(namespace.path, "r") as file:
            commands = file.read().splitlines()

        for command in commands:
            self.run(command.split(" "))


def quit(_):
    print("Quitting...")
    sys.exit()
