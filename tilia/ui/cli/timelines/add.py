import argparse

import tilia.errors
from tilia.requests import Get, get
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.pdf.timeline import PdfTimeline
from tilia.timelines.range.timeline import RangeTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui.cli.io import output

# Every kind the user can create, with its abbreviation. SliderTimeline is
# deliberately absent: it comes with the file and can't be deleted.
KIND_STR_TO_TIMELINE_CLASS: dict[str, type[Timeline]] = {
    "audiowave": AudioWaveTimeline,
    "aud": AudioWaveTimeline,
    "beat": BeatTimeline,
    "bea": BeatTimeline,
    "harmony": HarmonyTimeline,
    "har": HarmonyTimeline,
    "hierarchy": HierarchyTimeline,
    "hrc": HierarchyTimeline,
    "marker": MarkerTimeline,
    "mrk": MarkerTimeline,
    "pdf": PdfTimeline,
    "range": RangeTimeline,
    "rng": RangeTimeline,
    "score": ScoreTimeline,
    "sco": ScoreTimeline,
}

# The creation kwargs each kind accepts. This doubles as the validation
# table: an optional argument the user passed that isn't listed for their
# kind is rejected rather than silently dropped.
TIMELINE_CLASS_TO_KWARGS_NAMES: dict[type[Timeline], list[str]] = {
    AudioWaveTimeline: ["name", "height"],
    BeatTimeline: ["name", "height", "beat_pattern"],
    # HarmonyTimeline takes no height: it derives one from level_height and
    # visible_level_count, and raises TypeError if handed one as well.
    HarmonyTimeline: ["name"],
    HierarchyTimeline: ["name", "height"],
    MarkerTimeline: ["name", "height"],
    PdfTimeline: ["name", "height", "path"],
    RangeTimeline: ["name", "height", "default_row_height"],
    ScoreTimeline: ["name", "height"],
}

# Kwargs a kind can't be constructed without.
REQUIRED_KWARGS: dict[type[Timeline], list[str]] = {PdfTimeline: ["path"]}

# Optional argument attribute -> the flag to name in error messages.
# "name" is absent because every kind accepts it.
OPTIONAL_ARG_TO_FLAG = {
    "beat_pattern": "--beat-pattern",
    "default_row_height": "--row-height",
    "height": "--height",
    "path": "--path",
}


def setup_parser(subparser):
    add_subp = subparser.add_parser(
        "add",
        exit_on_error=False,
        help="Add a new timeline",
        epilog="""
Examples:
  timelines add beat --name "Measures" --beat-pattern 4
  timelines add hierarchy --name "Form"
  timelines add marker --name "Cadences"
  timelines add harmony --name "Chords"
  timelines add pdf --name "Score" --path score.pdf
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_subp.add_argument(
        "kind",
        choices=list(KIND_STR_TO_TIMELINE_CLASS),
        help="Kind of timeline to add",
    )
    add_subp.add_argument(
        "--name", "-n", type=str, default="", help="Name of the new timeline"
    )
    add_subp.add_argument(
        "--height",
        "-e",
        type=int,
        default=None,
        help="Height of the timeline. Not valid for harmony timelines, whose "
        "height follows from their level height and visible level count.",
    )
    add_subp.add_argument(
        "--beat-pattern",
        "-b",
        type=int,
        nargs="+",
        default=None,
        help="Pattern as space-separated integers indicating beat count in a measure "
        "(beat timelines only). Pattern will be repeated. Pattern '3 4', for "
        "instance, will alternate measures of 3 and 4 beats. Defaults to [4].",
    )
    add_subp.add_argument(
        "--row-height",
        dest="default_row_height",
        type=int,
        default=None,
        help="Per-timeline default row height (range timelines only). "
        "Defaults to the global setting.",
    )
    add_subp.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Path to the PDF file (PDF timelines only). Required for those.",
    )
    add_subp.set_defaults(func=add)


def get_kwargs_by_timeline_type(namespace: argparse.Namespace, kind: type[Timeline]):
    kwargs = {}
    for attr in TIMELINE_CLASS_TO_KWARGS_NAMES[kind]:
        kwargs[attr] = getattr(namespace, attr)
    return kwargs


def add(namespace: argparse.Namespace):
    if not get(Get.MEDIA_DURATION):
        tilia.errors.display(tilia.errors.CLI_CREATE_TIMELINE_WITHOUT_DURATION)
        return
    kind = namespace.kind
    name = namespace.name

    tl_type = KIND_STR_TO_TIMELINE_CLASS[kind]
    accepted_kwargs = TIMELINE_CLASS_TO_KWARGS_NAMES[tl_type]

    for attr, flag in OPTIONAL_ARG_TO_FLAG.items():
        if getattr(namespace, attr) is not None and attr not in accepted_kwargs:
            tilia.errors.display(
                tilia.errors.CLI_ADD_TIMELINE_ARG_NOT_APPLICABLE, flag, kind
            )
            return

    for attr in REQUIRED_KWARGS.get(tl_type, []):
        if getattr(namespace, attr) is None:
            tilia.errors.display(
                tilia.errors.CLI_ADD_TIMELINE_ARG_REQUIRED,
                OPTIONAL_ARG_TO_FLAG[attr],
                kind,
            )
            return

    output(f"Adding timeline with {kind=}, {name=}")

    kwargs = get_kwargs_by_timeline_type(namespace, tl_type)

    get(Get.TIMELINE_COLLECTION).create_timeline(tl_type, **kwargs)
