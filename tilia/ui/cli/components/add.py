from argparse import _SubParsersAction
import argparse

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.timelines.getters import get_timeline_by_name, get_timeline_by_ordinal


def setup_parser(subparser: _SubParsersAction):
    subp = subparser.add_parser("beat", exit_on_error=False)
    tl_group = subp.add_mutually_exclusive_group(required=True)
    tl_group.add_argument("--tl-ordinal", "-o", type=int, default=None)
    tl_group.add_argument("--tl-name", "-n", type=str, default=None)
    subp.add_argument("--time", "-t", type=float, required=True)
    subp.set_defaults(func=add)


def add(namespace):
    ord = namespace.tl_ordinal
    name = namespace.tl_name

    if ord is not None:
        tl = get_timeline_by_ordinal(ord)
    else:
        tl = get_timeline_by_name(name)

    print(f"Adding component to timeline {tl}")
