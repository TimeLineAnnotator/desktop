from typing import Callable
import argparse
from tilia.ui.cli import generate_scripts
from tilia.requests import post, Post


def setup_parser(subparsers, run_command: Callable[[str, None], None]):
    script = subparsers.add_parser("script", exit_on_error=False)
    script_subparser = script.add_subparsers(dest="script_command")
    script_runner._add_runner(run_command)

    setup_run_parser(script_subparser)
    setup_generate_parser(script_subparser)


def setup_run_parser(subparser: argparse.ArgumentParser):
    run_subp = subparser.add_parser("run")
    run_subp.add_argument("--path", type=str, nargs="+")
    run_subp.set_defaults(func=run)


def setup_generate_parser(subparser: argparse.ArgumentParser):
    generate_subp = subparser.add_parser("generate", exit_on_error=False)
    generate_subp.add_argument("--path", type=str, nargs="+")
    generate_subp.set_defaults(func=generate)


def run(namespace: argparse.Namespace):
    path = "".join(namespace.path)
    script_runner.run(path)


def generate(namespace: argparse.Namespace):
    path = "".join(namespace.path)
    if not generate_scripts.check_starting_directory(path):
        return
    saved_scripts = generate_scripts.get_scripts(path)
    if not saved_scripts:
        return
    print("\nSaved scripts:", *saved_scripts, sep="\n")
    confirm = input("\nContinue to generate files? (Y/n): ")
    if confirm.lower() not in {"", "y"}:
        return
    for script in saved_scripts:
        print(f"\nRunning script:")
        script_runner.run(script)
        post(Post.APP_CLEAR)


class ScriptRunner:
    def __init__(self):
        self.command_runner = NotImplemented

    def _add_runner(self, command_runner: Callable[[str, None], None]):
        self.command_runner = command_runner

    def run(self, path: str):
        print(path)
        with open(path, "r", encoding='utf-8') as file:
            commands = [line for line in file.read().splitlines() if line.strip()]
        for command in commands:
            print(command)
            self.command_runner(command)


script_runner = ScriptRunner()
