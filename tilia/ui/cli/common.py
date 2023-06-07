import argparse
from typing import Protocol


class Subparsers(Protocol):
    def add_parser(self, *args, **kwargs) -> argparse.ArgumentParser: ...
