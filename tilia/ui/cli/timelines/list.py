from tilia.requests import Get, get
from tilia.ui.cli.io import tabulate


def setup_parser(subparser):
    list_subp = subparser.add_parser(
        "list", exit_on_error=False, aliases=["ls"], help="List all timelines"
    )
    list_subp.set_defaults(func=list)


# noinspection PyShadowingBuiltins
def list(_):
    timelines = get(Get.TIMELINES)
    headers = ["ord.", "name", "kind"]
    data = [
        (
            tl.ordinal,
            tl.name,
            tl.type_name(),
        )
        for tl in timelines
    ]
    tabulate(headers, data)
