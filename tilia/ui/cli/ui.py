from __future__ import annotations
import prettytable
import argparse

from tilia.requests import post, Post
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind


class CLI:
    def __init__(self):
        self.app = None
        self.parser = argparse.ArgumentParser()
        self.subparsers = self.parser.add_subparsers(dest="command")
        self.setup_parsers()

    def setup_parsers(self):
        self.setup_timeline_parser()
        self.setup_quit_parser()
        self.setup_run_parser()

    def setup_timeline_parser(self):
        tl = self.subparsers.add_parser("timeline")
        tl_subparser = tl.add_subparsers(dest="timeline_command")

        # 'add' subparser
        add = tl_subparser.add_parser("add")
        add.add_argument(
            "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
        )
        add.add_argument("--name", default="")
        add.set_defaults(func=self.add_timeline)

        # 'list' subparser
        list = tl_subparser.add_parser("list")
        list.set_defaults(func=self.list_timelines)

        # 'remove' subparser
        remove = tl_subparser.add_parser("remove")
        remove.add_mutually_exclusive_group(required=True)
        remove.add_argument("--name", "-n")
        remove.add_argument("--id")
        remove.set_defaults(func=self.remove_timeline)

    def setup_quit_parser(self):
        self.subparsers.add_parser("quit")

    def setup_run_parser(self):
        run = self.subparsers.add_parser("run")
        run.add_argument("path")
        run.set_defaults(func=self.run_script)

    def launch(self):
        print("--- TiLiA CLI v0.0 ---")
        quit = False
        while not quit:
            cmd = input(">>> ")
            quit = self.run(cmd.split(" "))

    def run(self, cmd) -> bool:
        """
        Parses the command entered by the user.
        Returns True if the user requested to quit.
        """
        try:
            namespace = self.parser.parse_args(cmd)
            if namespace.command == "quit":
                quit()
                return True
            elif hasattr(namespace, "func"):
                namespace.func(namespace)
        except SystemExit:
            pass

        return False

    def run_script(self, namespace):
        with open(namespace.path, "r") as file:
            commands = file.read().splitlines()

        for command in commands:
            self.run(command.split(" "))

    def get_timelines(self):
        return self.app.get_timelines()

    @staticmethod
    def add_timeline(namespace):
        kind = namespace.kind
        name = namespace.name

        kind_to_tlkind = {
            "hierarchy": TimelineKind.HIERARCHY_TIMELINE,
            "hrc": TimelineKind.HIERARCHY_TIMELINE,
            "marker": TimelineKind.MARKER_TIMELINE,
            "mrk": TimelineKind.MARKER_TIMELINE,
            "beat": TimelineKind.BEAT_TIMELINE,
            "bea": TimelineKind.BEAT_TIMELINE,
        }

        output(f"Adding timeline with {kind=}, {name=}")

        post(Post.REQUEST_TIMELINE_CREATE, kind_to_tlkind[kind], name)

    @staticmethod
    def remove_timeline(namespace):
        pass

    def list_timelines(self, _):
        timelines = self.get_timelines()
        headers = ["id", "name", "kind"]
        data = [
            (
                tl.id,
                tl.name,
                pprint_tlkind(tl.TIMELINE_KIND),
            )
            for tl in timelines
        ]
        tabulate(headers, data)

    def get_timeline_by_name(self, name: str) -> Timeline:
        result = [tl for tl in self.get_timelines() if tl.name == name]
        return result[0] if result else None

    def get_timeline_by_id(self, id: str) -> Timeline | None:
        result = [tl for tl in self.get_timelines() if tl.id == id]
        return result[0] if result else None


def output(message: str) -> None:
    print(message)


def tabulate(headers: list[str], data: list[tuple[str, ...]]) -> None:
    table = prettytable.PrettyTable()
    table.field_names = headers
    table.add_rows(data)
    output(str(table))


def pprint_tlkind(kind: TimelineKind) -> str:
    return kind.value.strip("_TIMELINE").capitalize()


def quit():
    print("Quitting...")
