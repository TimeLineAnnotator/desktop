from __future__ import annotations

import sys
import traceback

import argparse

from tilia.exceptions import TiliaExit
from tilia.requests.post import Post, listen
from tilia.ui.cli import (
    components,
    load_media,
    timelines,
    run,
    quit,
    save,
    io,
    metadata,
)


class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(exit_on_error=False)
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()
        self.exception = None

        listen(
            self, Post.REQUEST_DISPLAY_ERROR, self.on_request_to_display_error
        )  # ignores error title

    def setup_parsers(self):
        timelines.setup_parser(self.subparsers)
        run.setup_parser(self.subparsers)
        quit.setup_parser(self.subparsers)
        save.setup_parser(self.subparsers)
        load_media.setup_parser(self.subparsers)
        components.setup_parser(self.subparsers)
        metadata.setup_parser(self.subparsers)

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
        Return True if an uncaught exception ocurred.
        The exception is stored in self.exception.
        """
        try:
            namespace = self.parser.parse_args(cmd)
            if hasattr(namespace, "func"):
                namespace.func(namespace)
            return False
        except argparse.ArgumentError as err:
            io.print(str(err))
            self.exception = err
            return True
        except SystemExit as err:
            self.exception = err
            return True
        except TiliaExit:
            sys.exit(0)
        except Exception as err:
            self.exception = err
            traceback.print_exc()
            return True

    def on_request_to_display_error(self, _, message: str) -> None:
        """Ignores title and prints error message to output"""
        io.print(message)
