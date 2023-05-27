import argparse
import sys
import prettytable

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.collection import TimelineUICollection
from tilia.events import post, Event


class CLI:
    def __init__(self):
        self.timeline_ui_collection = TimelineUICollection(self)

        self.parser = argparse.ArgumentParser()
        self.config_parser()

    def config_parser(self):
        subparsers = self.parser.add_subparsers(dest="command")

        # timeline parser
        tl = subparsers.add_parser("timeline")
        tl_subparser = tl.add_subparsers(dest="timeline_command")

        # add subparser
        add = tl_subparser.add_parser("add")
        add.add_argument(
            "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
        )
        add.add_argument("--name", default="")
        add.set_defaults(func=self.add_timeline)

        # list subparser
        list = tl_subparser.add_parser("list")
        list.set_defaults(func=self.list_timelines)

        # delete parser
        delete = subparsers.add_parser("delete")
        delete.add_argument("arguments", nargs="*")

    def launch(self):
        print("--- TiLiA CLI v0.0 ---")
        quit = False
        while not quit:
            cmd = input(">>> ")
            quit = self.run(cmd.split(" "))

    def run(self, cmd) -> bool:
        """
        Parses the command entered by the user. Return True if the user requested to quit.
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

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection

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

        post(Event.REQUEST_ADD_TIMELINE, kind_to_tlkind[kind], name)

    def list_timelines(self, _):
        timeline_uis = self.timeline_ui_collection.timeline_uis
        headers = ["id", "name", "kind"]
        data = [
            (
                str(tlui.display_position),
                str(tlui.name),
                pprint_tlkind(tlui.TIMELINE_KIND),
            )
            for tlui in timeline_uis
        ]
        tabulate(headers, data)


def output(message: str) -> None:
    print(message)


def tabulate(headers: list[str], data: list[tuple[str]]) -> None:
    table = prettytable.PrettyTable()
    table.field_names = headers
    table.add_rows(data)
    output(table)


def pprint_tlkind(kind: TimelineKind) -> str:
    return kind.value.strip("_TIMELINE").capitalize()


def quit():
    print("Quitting...")
