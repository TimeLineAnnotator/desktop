import argparse

from tilia.ui.cli.timelines.collection import TimelineUICollection
from tilia.events import post, Event


class CLI:
    def __init__(self):
        self.timeline_ui_collection = TimelineUICollection(self)

        self.parser = argparse.ArgumentParser()
        subparsers = self.parser.add_subparsers(dest="command")

        # create parser
        create_parser = subparsers.add_parser("create")
        create_parser.add_argument("kind", choices=["hierarchy", "marker", "beat"])
        create_parser.add_argument("--name", default="")

        # delete parser
        delete_parser = subparsers.add_parser("delete")
        delete_parser.add_argument("arguments", nargs="*")

        # quit parser
        quit_parser = subparsers.add_parser("quit")

        # timeline parser
        timeline_parser = subparsers.add_parser("timeline")
        timeline_parser.add_argument("arguments", nargs="*")

    def launch(self):
        print("--- TiLiA CLI v0.0 ---")
        while True:
            cmd = input(">>> ")
            self.run(cmd.split(" "))

    def run(self, cmd):
        args = self.parser.parse_args(cmd)

        if args.command == "create":
            self.create(args.kind, args.name)
        elif args.command == "delete":
            self.delete(args.arguments)
        elif args.command == "quit":
            self.quit()
        elif args.command == "timeline":
            self.timeline(args.arguments)
        else:
            print("Invalid command. Use -h for help.")

    def create(self, kind, name):
        print(f"Creating {kind} with name: {name}")

    def delete(self, args):
        print(f"Deleting with arguments: {args}")

    def quit(self):
        print("Quitting...")

    def timeline(self, args):
        print(f"Managing timeline with arguments: {args}")

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection
