from __future__ import annotations

import sys
import traceback

import argparse

from tilia.exceptions import TiliaExit
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import Get, serve
from tilia.requests.post import Post, listen, post
from tilia.ui.cli import (
    components,
    load_media,
    timelines,
    script,
    quit,
    save,
    io,
    metadata,
)
from tilia.ui.cli.player import CLIVideoPlayer, CLIYoutubePlayer


class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(exit_on_error=False)
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()
        self.setup_player()
        self.exception = None

        listen(
            self, Post.DISPLAY_ERROR, self.on_request_to_display_error
        )  # ignores error title

        serve(self, Get.PLAYER_CLASS, self.get_player_class)

    def setup_parsers(self):
        timelines.setup_parser(self.subparsers)
        quit.setup_parser(self.subparsers)
        save.setup_parser(self.subparsers)
        load_media.setup_parser(self.subparsers)
        components.setup_parser(self.subparsers)
        metadata.setup_parser(self.subparsers)
        script.setup_parser(self.subparsers, self.run_script)

    def setup_player(self):
        self.player = QtPlayer()
        post(Post.PLAYER_AVAILABLE, self.player)

    @staticmethod
    def parse_command(arg_string):
        args = []
        quoted_string = ""
        in_quotes = False
        for arg in arg_string.split(" "):
            if not in_quotes and arg.startswith('"') and arg.endswith('"'):
                args.append(arg[1:-1])
            elif not in_quotes and arg.startswith('"'):
                in_quotes = True
                quoted_string = arg[1:]
            elif in_quotes and not arg.endswith('"'):
                quoted_string += " " + arg
            elif in_quotes and arg.endswith('"'):
                in_quotes = False
                quoted_string += " " + arg[:-1]
                args.append(quoted_string)
            elif not in_quotes and arg.endswith('"'):
                return None
            else:
                args.append(arg)

        if in_quotes:
            return None
        return args

    def launch(self):
        """
        Launches the CLI.
        """
        print("--- TiLiA CLI v0.1 ---")
        while True:
            cmd = input(">>> ")
            args = self.parse_command(cmd)
            if args is None:
                post(Post.DISPLAY_ERROR, "", "Parse error: Invalid quoted arguments")
            self.run(args)

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
            io.output(str(err))
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

    def run_script(self, cmd):
        args = self.parse_command(cmd)
        if args is None:
            post(Post.DISPLAY_ERROR, "", "Parse error: Invalid quoted arguments")
        self.run(args)

    @staticmethod
    def on_request_to_display_error(_, message: str) -> None:
        """Ignores title and prints error message to output"""
        io.output(message)

    @staticmethod
    def get_player_class(media_type: str):
        return {
            "video": CLIVideoPlayer,
            "audio": QtPlayer,
            "youtube": CLIYoutubePlayer,
        }[media_type]

    @staticmethod
    def show_crash_dialog(exc_message) -> None:
        io.output(exc_message)
