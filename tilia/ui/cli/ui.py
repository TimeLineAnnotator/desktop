from __future__ import annotations

import argparse
import os
import sys
import traceback

from colorama import Fore

import tilia.constants
from tilia.media.player.qtplayer import QtPlayer
from tilia.requests import Get, serve
from tilia.requests.post import Post, listen, post
from tilia.settings import settings
from tilia.ui.cli import (
    clear,
    components,
    export,
    generate_scripts,
    io,
    load_media,
    metadata,
    open,
    quit,
    save,
    script,
    timelines,
)
from tilia.ui.cli.io import ask_yes_or_no, error, tabulate
from tilia.ui.cli.player import CLIVideoPlayer, CLIYoutubePlayer


class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            exit_on_error=False, prog=tilia.constants.APP_NAME
        )
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()
        self.exception = None
        self._save_verbosity()
        listen(
            self, Post.DISPLAY_ERROR, self.on_request_to_display_error
        )  # ignores error title

        SERVES = {
            (Get.PLAYER_CLASS, self.get_player_class),
            (Get.FROM_USER_YES_OR_NO, on_ask_yes_or_no),
            (Get.FROM_USER_SHOULD_SAVE_CHANGES, on_ask_should_save_changes),
            (Get.FROM_USER_RETRY_MEDIA_PATH, on_ask_retry_media_file),
            (Get.FROM_USER_RETRY_PDF_PATH, on_ask_retry_pdf_file),
            (Get.FROM_USER_MEDIA_PATH, on_ask_media_path),
        }
        for request, callback in SERVES:
            serve(self, request, callback)

    def _save_verbosity(self):
        self._initial_verbosity = settings.get("dev", "log_requests")
        _set_verbosity(False)

    def setup_parsers(self):
        clear.setup_parser(self.subparsers)
        components.setup_parser(self.subparsers)
        export.setup_parser(self.subparsers)
        generate_scripts.setup_parser(self.subparsers, self.parse_and_run)
        load_media.setup_parser(self.subparsers, self.parse_and_run)
        metadata.setup_parser(self.subparsers)
        open.setup_parser(self.subparsers)
        quit.setup_parser(self.subparsers, self.exit)
        save.setup_parser(self.subparsers)
        script.setup_parser(self.subparsers, self.parse_and_run)
        timelines.setup_parser(self.subparsers)
        self.subparsers.add_parser("about", help="About TiLiA").set_defaults(func=about)

    @staticmethod
    def parse_command(arg_string):
        arg_string = arg_string.strip()
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
        tabulate(
            [f"--- {tilia.constants.APP_NAME} v{tilia.constants.VERSION} CLI ---"],
            [[tilia.constants.NOTICE]],
            align="l",
            border=False,
        )
        while True:
            try:
                cmd = input(">>> ")
                self.parse_and_run(cmd)
            except EOFError:
                self.exit(1)

    def parse_and_run(self, cmd):
        """Returns True if command was unsuccessful, False otherwise"""
        args = self.parse_command(cmd)
        if args is None:
            post(
                Post.DISPLAY_ERROR,
                "Parse error",
                "Parse error: Invalid quoted arguments",
            )
            return True
        return self.run(args)

    def run(self, cmd: str) -> bool:
        """
        Parses the commands entered by the user.
        Return True if an uncaught exception occurred.
        The exception is stored in self.exception.
        """
        try:
            namespace = self.parser.parse_args(cmd)
            if hasattr(namespace, "func"):
                namespace.func(namespace)
            return False
        except argparse.ArgumentError as err:
            post(Post.DISPLAY_ERROR, "Argument error", str(err))
            self.exception = err
            return True
        except SystemExit as err:
            self.exception = err
            return True
        except Exception as err:
            self.exception = err
            post(Post.DISPLAY_ERROR, "CLI error", traceback.format_exc())
            return True

    @staticmethod
    def on_request_to_display_error(_, message: str) -> None:
        """Ignores title and prints error message to output"""
        io.output(message, color=Fore.RED)

    @staticmethod
    def get_player_class(media_type: str):
        return {
            "video": CLIVideoPlayer,
            "audio": QtPlayer,
            "youtube": CLIYoutubePlayer,
        }[media_type]

    @staticmethod
    def show_crash_dialog(exc_message) -> None:
        post(Post.DISPLAY_ERROR, "CLI has crashed", "Error: " + exc_message)

    def exit(self, code: int, *_):
        _set_verbosity(self._initial_verbosity)
        io.output("Quitting...")
        sys.exit(code)


def about(_):
    tabulate(
        ["where", "link"],
        [
            ["Website", tilia.constants.WEBSITE_URL],
            ["GitHub", tilia.constants.GITHUB_URL],
            ["Contact us", tilia.constants.EMAIL],
        ],
        header=False,
        title=f"{tilia.constants.APP_NAME} v{tilia.constants.VERSION}",
    )


def _set_verbosity(verbose):
    settings.set("dev", "log_requests", verbose)
    post(Post.SETTINGS_UPDATED, [*{"dev": {"log_requests", verbose}}])


def on_ask_yes_or_no(title: str, prompt: str) -> bool:
    return ask_yes_or_no(f"{title}: {prompt}")


def on_ask_should_save_changes() -> tuple[bool, bool]:
    return True, ask_yes_or_no("Save changes to current file?")


def on_ask_retry_media_file() -> bool:
    return on_ask_yes_or_no(
        "Invalid media path", "Would you like to load another media file?"
    )


def on_ask_retry_pdf_file() -> bool:
    return on_ask_yes_or_no("Invalid PDF", "Would you like to load another PDF file?")


def on_ask_media_path() -> tuple[bool, str]:
    while True:
        ans = input("Media file path [leave empty to cancel]: ").strip()
        if not ans:
            return False, ""
        if os.path.exists(ans):
            return True, ans
        error(f"Path not found: {ans}")
