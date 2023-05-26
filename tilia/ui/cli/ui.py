import argparse

from tilia.ui.cli.timelines.collection import TimelineUICollection


class CLI:
    def __init__(self, parser: argparse.ArgumentParser):
        self.app = None
        self.timeline_ui_collection = TimelineUICollection(self)
        self.args = parser.parse_args()

    def create(self):
        print("Creating TiLiA file...")

    def launch(self):
        match self.args.cmd:
            case "create":
                self.create()
            case _ as cmd:
                print(f"Unrecognized command '{cmd}'")

    def get_timeline_ui_collection(self):
        return self.timeline_ui_collection
