import argparse
import sys

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
        tl_subp = tl.add_subparsers(dest="timeline_command")

        # create parser
        create = tl_subp.add_parser("create")
        create.add_argument("kind", choices=["hierarchy", "marker", "beat"])
        create.add_argument("--name", default="")

        # delete parser
        delete = subparsers.add_parser("delete")
        delete.add_argument("arguments", nargs="*")

        # quit parser
        quit_parser = subparsers.add_parser("quit")

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
            args = self.parser.parse_args(cmd)
            if args.command == "create":
                self.create(args.kind, args.name)
            elif args.command == "delete":
                self.delete(args.arguments)
            elif args.command == "quit":
                self.quit()
                return True
            elif args.command == "timeline":
                self.timeline(args.timeline_command)
            else:
                print("Invalid command. Use -h for help.")
        except SystemExit:
            pass

        return False

    def create(self, kind, name):
        kind_to_tlkind = {
            "hierarchy": TimelineKind.HIERARCHY_TIMELINE,
            "marker": TimelineKind.MARKER_TIMELINE,
            "beat": TimelineKind.BEAT_TIMELINE,
        }

        post(Event.REQUEST_ADD_TIMELINE, kind_to_tlkind[kind], name)

    def delete(self, args):
        print(f"Deleting with arguments: {args}")

    def quit(self):
        print("Quitting...")

    def timeline(self, args):
        print(f"Managing timeline with arguments: {args}")

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection
