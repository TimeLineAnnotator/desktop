from tilia.requests import get, Get
from tilia.timelines.base.timeline import Timeline
from tilia.ui.cli import io
from tilia.ui.cli.timelines.utils import get_timeline_by_name, get_timeline_by_ordinal


def setup_parser(subparser):
    move_subp = subparser.add_parser("move", exit_on_error=False, aliases=["mv"])
    move_subcommands = move_subp.add_subparsers(dest="type", required=True)

    # 'move by name' subcommand
    by_name_subcommand = move_subcommands.add_parser("name", exit_on_error=False)
    by_name_subcommand.add_argument("name")
    by_name_subcommand.add_argument("new_ordinal", type=int)
    by_name_subcommand.set_defaults(func=move_timeline, by="name")

    # 'move by ordinal' subcommand
    by_ordinal_subcommand = move_subcommands.add_parser("ordinal", exit_on_error=False)
    by_ordinal_subcommand.add_argument("ordinal", type=int)
    by_ordinal_subcommand.add_argument("new_ordinal", type=int)
    by_ordinal_subcommand.set_defaults(func=move_timeline, by="ordinal")


def move(timeline: Timeline, to: int) -> bool:
    ordinal_to_timeline = {tl.get_data("ordinal"): tl for tl in get(Get.TIMELINES)}

    curr_ordinal = timeline.get_data("ordinal")
    max_ordinal = max(ordinal_to_timeline.keys())
    if to == curr_ordinal:
        return True

    if to < curr_ordinal:
        if to < 1:
            io.warn(
                "Can't move to ordinal smaller than '1'. Moving to '1' instead. ",
            )
            to = 1

        sign = -1
        steps = curr_ordinal - to
    else:
        if to > max_ordinal:
            io.warn(
                f"Can't move to '{to}' is bigger than last ordinal '{max_ordinal}'. Moving to last ordinal. ",
            )
            to = max_ordinal
        sign = 1
        steps = to - curr_ordinal

    for _ in range(steps):
        get(Get.TIMELINE_COLLECTION).permute_ordinal(
            timeline,
            ordinal_to_timeline[timeline.get_data("ordinal") + 1 * sign],
        )

    return True


def move_timeline(namespace):
    attr_value = getattr(namespace, namespace.by)

    if namespace.by == "name":
        success, tl = get_timeline_by_name(attr_value)
    else:  # ordinal
        success, tl = get_timeline_by_ordinal(attr_value)

    if not success:
        return  # error has already been printed

    success = move(tl, namespace.new_ordinal)
