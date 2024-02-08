

from tilia.requests import Get, get
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.io import tabulate


def pprint_tlkind(kind: TlKind) -> str:
    return kind.value.strip("_TIMELINE").capitalize()


def setup_parser(subparser):
    list_subp = subparser.add_parser("list", exit_on_error=False, aliases=["ls"])
    list_subp.set_defaults(func=list)


# noinspection PyShadowingBuiltins
def list(_):
    timelines = get(Get.TIMELINES)
    headers = ["ord.", "name", "kind"]
    data = [
        (
            tl.ordinal,
            tl.name,
            pprint_tlkind(tl.KIND),
        )
        for tl in timelines
    ]
    tabulate(headers, data)
